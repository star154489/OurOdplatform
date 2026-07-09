#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :service.py
# @Time      :2026/7/8 14:43:45
# @Author    :雨霓同学
# @Project   :ODPlatform
# @Function  :
#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : service.py
# @Project   : ODPlatform
# @Function  : InferService — 编排 D5 配置 + 帧源捕获 + ultralytics 推理 + 美化绘制
"""推理服务编排器.

★ 核心纪律 (跟 D6 TrainService 完全同构): 不重新发明 D5 / 帧源 / 美化已有的轮子.

★ 接缝 (向后 100% 兼容):
  - predict() 3 个新参数: output_sink / hooks / cancel_token, 全部 keyword-only Optional[None]
  - 不传 = CLI 默认行为 (LocalFileSink / 空 hooks / 无 cancel)
  - 传了 = 桌面 / Web / Celery 业务方能完全定制输出 + 事件 + 取消

★ 跟训练的两点关键差异:
  1. 推理不调 model.predict(source=...) —— 而是 frame_source 逐帧喂 + 自己画
  2. 逐帧 model() 只传 predict 计算参数白名单, 不盲传 to_ultralytics_kwargs()
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator
from argparse import Namespace

import numpy as np

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None  # type: ignore[assignment]

from od_platform.common.log_rename import rename_log_to_save_dir
from od_platform.common.model_path import resolve_model_path
from od_platform.common.paths import TRAINED_MODELS_DIR, PRETRAINED_MODELS_DIR, RUNS_DIR
from od_platform.common.system_utils import log_device_info
from od_platform.common.config_log import log_effective_config, log_override_chains
from od_platform.runtime_config import build_infer_config

from od_platform.frame_source import create_frame_source, SourceType, IMAGE_EXTENSIONS
from od_platform.visualization import BeautifyVisualizer, DrawStyle

from .cancel import CancelToken
from .hooks import InferHooks
from .pipeline_config import PipelineConfig, load_pipeline_config
from .sinks import LocalFileSink, NullSink, OutputSink

logger = logging.getLogger(__name__)


# ============================================================================
# 逐帧 model() 的 predict 计算参数白名单
# ----------------------------------------------------------------------------
# 为什么不盲传 config.to_ultralytics_kwargs()? YOLOInferConfig 继承 BaseConfig,
# 带进来一堆训练向字段 (batch/workers/cache/rect/amp/seed/...), 这些传给逐帧
# model() 要么报错要么被忽略. 显式列出真正影响"单帧检测计算"的参数, 只传这些.
# ============================================================================
_PREDICT_KEYS: tuple[str, ...] = (
    "conf", "iou", "imgsz", "max_det", "classes",
    "agnostic_nms", "augment", "device", "retina_masks",
)


def _find_project_log_path() -> Path | None:
    """从 D2 'odp_platform' 根 logger 找 FileHandler 的实际文件路径 (只读, 给 audit 用)."""
    root = logging.getLogger("od_platform")
    for h in root.handlers:
        if isinstance(h, logging.FileHandler):
            return Path(h.baseFilename)
    return None


def _resolve_output_dir(base: Path, name: str, *, exist_ok: bool) -> Path:
    """自建推理输出目录 (跟 ultralytics 行为对齐: 重名自增 name2/name3...)."""
    base.mkdir(parents=True, exist_ok=True)
    candidate = base / name
    if exist_ok or not candidate.exists():
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate
    i = 2
    while (base / f"{name}{i}").exists():
        i += 1
    out = base / f"{name}{i}"
    out.mkdir(parents=True, exist_ok=True)
    return out


# ============================================================================
# 推理统计 —— 推理侧没有 mAP, 取而代之的是 帧数/检测数/每类计数/FPS
# ============================================================================
@dataclass
class InferStats:
    """一次推理跑完的统计快照."""
    frames: int = 0
    detections: int = 0
    per_class: dict[str, int] = field(default_factory=dict)
    infer_time_sec: float = 0.0

    # 多维帧率 (引擎跑完填入)
    capture_fps: float = 0.0
    infer_fps: float = 0.0
    render_fps: float = 0.0
    loop_fps: float = 0.0
    current_fps: float = 0.0
    speed_ms: dict[str, float] = field(default_factory=dict)

    @property
    def avg_fps(self) -> float:
        return self.frames / self.infer_time_sec if self.infer_time_sec > 0 else 0.0

    @property
    def avg_latency_ms(self) -> float:
        return (self.infer_time_sec / self.frames * 1000.0) if self.frames else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "frames": self.frames,
            "detections": self.detections,
            "per_class": dict(self.per_class),
            "infer_time_sec": round(self.infer_time_sec, 4),
            "avg_fps": round(self.avg_fps, 2),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "fps": {
                "capture": self.capture_fps,
                "infer": self.infer_fps,
                "render": self.render_fps,
                "loop": self.loop_fps,
                "current": self.current_fps,
            },
            "speed_ms": dict(self.speed_ms),
        }


def log_infer_stats(stats: InferStats, *, logger: logging.Logger = logger) -> None:
    """漂亮打印推理统计 (含多维帧率)."""
    logger.info(f"处理帧数:   {stats.frames}")
    logger.info(f"检测总数:   {stats.detections}")
    logger.info(f"平均延迟:   {stats.avg_latency_ms:.2f} ms/帧")
    logger.info("帧率(FPS):  捕获 %.1f | 推理 %.1f | 渲染 %.1f | loop %.1f | 当前 %.1f" % (
        stats.capture_fps, stats.infer_fps, stats.render_fps,
        stats.loop_fps, stats.current_fps,
    ))
    if stats.speed_ms:
        logger.info("模型 speed(ms): 预处理 %.2f | 推理 %.2f | 后处理 %.2f" % (
            stats.speed_ms.get("preprocess", 0.0),
            stats.speed_ms.get("inference", 0.0),
            stats.speed_ms.get("postprocess", 0.0),
        ))
    if stats.per_class:
        logger.info("各类别检测数:")
        for name, cnt in sorted(stats.per_class.items(), key=lambda kv: -kv[1]):
            logger.info(f"    {name:<20} {cnt}")


@dataclass(frozen=True)
class InferResult:
    """推理结果一次性快照 (跟 TrainResult 平行)."""
    success:    bool
    output_dir: Path
    stats:      dict[str, Any] = field(default_factory=dict)
    infer_time: float | None = None
    saved:      bool = False
    error:      str | None = None
    audit_path: Path | None = None
    log_path:   Path | None = None


# ============================================================================
# InferService 主类
# ============================================================================
class InferService:
    """YOLO 推理流程编排."""

    def __init__(self) -> None:
        """__init__ 不接任何参数 —— 配置都通过 predict() 传."""
        pass

    def predict(
        self,
        yaml_path: str | Path | None = None,
        pipeline_yaml: str | Path | None = None,
        cli_args: dict[str, Any] | None = None,
        *,
        # ---- CLI 默认行为参数 (传统) ----
        beautify: bool = True,
        rename_log: bool = True,
        threaded: bool = False,
        warmup_frames: int = 0,
        stride: int | None = None,
        window_name: str = "odp-infer",
        show_info: bool = True,
        # ---- ★ 接缝参数 (业务定制), keyword-only + 默认 None 让 CLI 行为不变 ----
        output_sink: OutputSink | None = None,
        hooks: InferHooks | None = None,
        cancel_token: CancelToken | None = None,
    ) -> InferResult:
        """跑一次完整推理.

        Args:
            yaml_path:     D5 infer.yaml 路径. None 走默认.
            pipeline_yaml: 帧源+美化 infer_pipeline.yaml 路径. None 走默认.
            cli_args:      CLI 覆盖字段 (source/conf/show/save/...), 交给 D5 merger.
            beautify:      是否美化. False → 退回 YOLO 原生 plot().
            rename_log:    是否把日志名改成跟 output_dir 对齐.
            threaded:      已弃用 — pipeline 内置 4 线程, 此参数无效果.
            warmup_frames: 启动丢弃前 N 帧 (摄像头帧率不稳).
            stride:       帧间隔(每 N 帧取 1), None 则用 pipeline yaml 的值.
            window_name:   显示窗口标题 (--show 时).
            show_info:     是否画 HUD 信息面板.
            output_sink:   自定义输出适配器 (默认根据 want_save 选 LocalFileSink / NullSink).
            hooks:         生命周期回调 (默认全空回调, 零开销).
            cancel_token:  程序化取消信号 (默认 None, 只能等帧源耗尽).

        Returns:
            InferResult. ★ 永不抛 —— 任何异常打包进 InferResult.error.
        """
        # ★ hooks 兜底空回调 (内部 fire 时 short-circuit, 零开销)
        if hooks is None:
            hooks = InferHooks()

        if threaded:
            logger.warning(
                "threaded 参数已弃用 — pipeline 内置 4 线程架构, "
                "此参数无效果, 将在未来版本移除."
            )

        start = datetime.now()
        output_dir: Path | None = None

        try:
            # 阶段 1-2: 配置加载 + 上下文日志
            config, merger, pipe = self._load_configs(yaml_path, pipeline_yaml, cli_args)

            # 阶段 3: 源 + 模型解析
            raw_source, model_path = self._resolve_model_and_source(config)

            # 阶段 4: 加载模型 + 美化器 + 输出目录 + sink
            setup = self._setup_inference(
                config, pipe, model_path, beautify, output_sink, raw_source,
            )
            model = setup["model"]
            output_dir = setup["output_dir"]
            output_sink = setup["output_sink"]
            do_beautify = setup["do_beautify"]
            visualizer = setup["visualizer"]
            predict_kwargs = setup["predict_kwargs"]
            want_save = setup["want_save"]
            want_show = setup["want_show"]

            # 阶段 5: 执行推理流水线
            stats, interrupted = self._run_pipeline(
                config=config,
                pipe=pipe,
                model=model,
                output_dir=output_dir,
                output_sink=output_sink,
                do_beautify=do_beautify,
                visualizer=visualizer,
                predict_kwargs=predict_kwargs,
                want_save=want_save,
                want_show=want_show,
                show_info=show_info,
                window_name=window_name,
                warmup_frames=warmup_frames,
                stride=stride,
                hooks=hooks,
                cancel_token=cancel_token,
            )

            if interrupted:
                logger.warning("推理被用户提前结束.")

            # 阶段 6-8: 统计 + 输出整理 + 审计
            result = self._finalize(
                stats=stats,
                config=config,
                merger=merger,
                pipe=pipe,
                output_dir=output_dir,
                raw_model=config.model or "yolo11n.pt",
                want_save=want_save,
                do_beautify=do_beautify,
                rename_log=rename_log,
                start=start,
            )
            hooks.fire_complete(result)
            return result

        except Exception as e:
            logger.error(f"推理失败: {e}", exc_info=True)
            infer_time = (datetime.now() - start).total_seconds()
            hooks.fire_error(e)
            return InferResult(
                success=False,
                output_dir=output_dir or Path("unknown"),
                stats={},
                infer_time=infer_time,
                error=str(e),
                log_path=_find_project_log_path(),
            )

    # ── 私有方法: 阶段分解 ─────────────────────────────────────────

    @staticmethod
    def _load_configs(
        yaml_path: str | Path | None,
        pipeline_yaml: str | Path | None,
        cli_args: dict[str, Any] | None,
    ) -> tuple[Any, Any, PipelineConfig]:
        """阶段 1-2: 加载 D5 config + pipeline config + 上下文日志."""
        config, merger = build_infer_config(
            yaml_path=yaml_path or "infer.yaml",
            cli_args=cli_args if isinstance(cli_args, Namespace) else Namespace(**cli_args) if cli_args else None,
        )
        pipe: PipelineConfig = load_pipeline_config(pipeline_yaml)

        logger.info("=" * 60)
        logger.info(f"开始 YOLO 推理 (task={config.task})".center(60))
        logger.info("=" * 60)

        raw_model = config.model or "yolo11n.pt"
        raw_source = config.source
        logger.info(f"任务类型:    {config.task}")
        logger.info(f"输入源(声明): {raw_source!r}")
        logger.info(f"模型(声明):  {raw_model}")

        log_effective_config(config, merger, logger=logger)
        log_override_chains(config, merger, logger=logger)

        return config, merger, pipe

    @staticmethod
    def _resolve_model_and_source(config) -> tuple[str, Path]:
        """阶段 3: 验证 source + 解析 model 路径."""
        raw_source = config.source
        if raw_source is None:
            raise RuntimeError(
                "未指定推理输入源. 请在 infer.yaml 写 source, 或用 "
                "`odp-infer --source <图/视频/目录/摄像头号>` 传入."
            )

        model_path = resolve_model_path(
            config.model or "yolo11n.pt",
            search_dirs=[TRAINED_MODELS_DIR, PRETRAINED_MODELS_DIR],
        )
        logger.info(f"模型(解析):  {model_path}")
        return raw_source, model_path

    @staticmethod
    def _setup_inference(
        config, pipe: PipelineConfig, model_path: Path,
        beautify: bool, output_sink: OutputSink | None, raw_source: str,
    ) -> dict[str, Any]:
        """阶段 4: 加载模型 + 建美化器 + 建输出目录 + 决定 sink."""
        if YOLO is None:
            raise ImportError("ultralytics is required for inference. Install with: pip install ultralytics")
        model = YOLO(str(model_path))
        class_names: list[str] = list(model.names.values())

        do_beautify = beautify and pipe.viz_enabled
        visualizer: BeautifyVisualizer | None = None
        if do_beautify:
            visualizer = BeautifyVisualizer(
                labels=class_names,
                label_mapping=pipe.label_mapping or None,
                color_mapping=pipe.color_mapping or None,
                default_color=pipe.default_color,
                font_path=pipe.font_path,
            )
        else:
            logger.info("美化已关闭, 使用 YOLO 原生 plot() 绘制.")

        run_name = config.experiment_name or "predict"
        _output_dir = _resolve_output_dir(
            RUNS_DIR / f"{config.task}_infer",
            run_name,
            exist_ok=bool(getattr(config, "exist_ok", False)),
        )
        logger.info(f"输出目录:    {_output_dir}")

        predict_kwargs = {
            k: getattr(config, k)
            for k in _PREDICT_KEYS
            if getattr(config, k, None) is not None
        }
        predict_kwargs["verbose"] = False

        want_save = bool(getattr(config, "save", True))
        want_show = bool(getattr(config, "show", False))

        if output_sink is None:
            output_sink = LocalFileSink() if want_save else NullSink()
        else:
            logger.info(f"使用调用方提供的 sink: {output_sink.__class__.__name__}")

        return {
            "model": model,
            "output_dir": _output_dir,
            "output_sink": output_sink,
            "do_beautify": do_beautify,
            "visualizer": visualizer,
            "predict_kwargs": predict_kwargs,
            "want_save": want_save,
            "want_show": want_show,
        }

    @staticmethod
    def _run_pipeline(
        *, config, pipe, model, output_dir, output_sink,
        do_beautify, visualizer, predict_kwargs,
        want_save, want_show, show_info, window_name,
        warmup_frames, stride, hooks, cancel_token,
    ) -> tuple[InferStats, bool]:
        """阶段 5: 创建 _FrameProcessor + ThreadedPipeline, 执行推理."""
        logger.info("=" * 60)
        logger.info("启动推理".center(60))
        logger.info("=" * 60)

        stats = InferStats()
        camera_cfg = pipe.build_camera_config()
        processor = _FrameProcessor(
            model=model,
            predict_kwargs=predict_kwargs,
            do_beautify=do_beautify,
            visualizer=visualizer,
            use_label_mapping=pipe.use_label_mapping,
            style_overrides=pipe.style_overrides,
            names=model.names,
        )

        raw_batch = getattr(config, "batch", 16)
        batch_size = raw_batch if isinstance(raw_batch, int) and raw_batch >= 1 else 16

        from .pipeline import ThreadedPipeline
        logger.info(f"执行引擎: 多线程流水线 (batch={batch_size}, 显示与主循环解耦)")
        pipeline = ThreadedPipeline(
            processor=processor,
            source=str(config.source),
            camera_config=camera_cfg,
            output_dir=output_dir,
            output_sink=output_sink,
            batch_size=batch_size,
            save=want_save,
            show=want_show,
            show_info=show_info,
            window_name=window_name,
            warmup_frames=warmup_frames,
            stride=stride if stride is not None else pipe.frame_stride,
            hooks=hooks,
            cancel_token=cancel_token,
        )
        interrupted = pipeline.run(stats)
        return stats, interrupted

    @staticmethod
    def _finalize(
        *, stats: InferStats, config, merger, pipe: PipelineConfig,
        output_dir: Path, raw_model: str, want_save: bool,
        do_beautify: bool, rename_log: bool, start,
    ) -> InferResult:
        """阶段 6-8: 统计 + 输出整理 + 审计快照 + 返回 InferResult."""
        logger.info("=" * 60)
        logger.info("推理完成".center(60))
        logger.info("=" * 60)
        log_infer_stats(stats, logger=logger)

        model_stem = Path(raw_model).stem
        if rename_log:
            rename_log_to_save_dir(output_dir, model_stem)

        audit_path: Path | None = output_dir / "odp_audit.json"
        log_path = _find_project_log_path()
        try:
            audit_payload = {
                "mode": "infer",
                "config": config.to_audit_snapshot(),
                "merger": merger.to_audit_log(),
                "pipeline": pipe.to_audit(),
                "stats": stats.to_dict(),
                "result_summary": {
                    "output_dir": str(output_dir),
                    "saved": want_save,
                    "beautified": do_beautify,
                    "infer_time_sec": (datetime.now() - start).total_seconds(),
                    "log_path": str(log_path) if log_path else None,
                },
            }
            audit_path.write_text(
                json.dumps(audit_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(f"审计快照:   {audit_path}")
        except OSError as e:
            logger.warning(f"写审计快照失败 (不影响推理结果): {e}")
            audit_path = None

        infer_time = (datetime.now() - start).total_seconds()
        logger.info("=" * 60)
        logger.info(f"推理总耗时: {infer_time:.2f} 秒")
        logger.info(f"输出目录:   {output_dir}")
        if want_save:
            logger.info(f"结果已保存到上面的目录.")
        if log_path:
            logger.info(f"本次日志:   {log_path}")
        logger.info("=" * 60)

        return InferResult(
            success=True,
            output_dir=output_dir,
            stats=stats.to_dict(),
            infer_time=infer_time,
            saved=want_save,
            audit_path=audit_path,
            log_path=log_path,
        )


# ============================================================================
# 帧处理器 —— 把"推理"和"绘制"拆成两半, pipeline 共用
# ============================================================================
@dataclass
class _FrameProcessor:
    model: Any
    predict_kwargs: dict[str, Any]
    do_beautify: bool
    visualizer: BeautifyVisualizer | None
    use_label_mapping: bool
    style_overrides: dict[str, Any]
    names: dict[int, str]
    _style: DrawStyle | None = None

    def infer_batch(self, images: list):
        """主线程: 批量推理. 返回 (results, labels_list, n_list, batch_dt)."""
        t0 = time.perf_counter()
        results = self.model(images, **self.predict_kwargs)
        batch_dt = time.perf_counter() - t0
        labels_list: list[list[str]] = []
        n_list: list[int] = []
        for result in results:
            boxes = result.boxes
            n = 0 if boxes is None else len(boxes)
            n_list.append(n)
            labels_list.append(
                [self.names[i] for i in boxes.cls.int().cpu().tolist()] if n else []
            )
        return results, labels_list, n_list, batch_dt

    def draw(self, image, result, labels, n):
        """绘制单帧 → annotated(BGR). 美化关时退回 YOLO 原生 plot().

        按 YOLO 模型的 task 类型提取对应数据:
          - detect  → boxes
          - segment → boxes + masks
          - pose    → boxes + keypoints
          - obb     → obb corners
          - classify→ probs
        """
        if self.do_beautify and self.visualizer is not None:
            if self._style is None:
                h, w = image.shape[:2]
                self._style = DrawStyle.from_image_size(h, w, **self.style_overrides)

            task_type = _get_task_type(self.model)

            if task_type == "classify":
                probs = result.probs
                if probs is not None:
                    top5_labels = [self.names.get(i, f"cls_{i}") for i in probs.top5]
                    top5_confs = probs.top5conf.tolist()
                    dets = BeautifyVisualizer.from_yolo_results(
                        boxes=_empty_boxes(),
                        confidences=np.array(top5_confs),
                        labels=top5_labels,
                        task_type="classify",
                        probs=list(zip(top5_labels, top5_confs)),
                    )
                else:
                    dets = []
                return self.visualizer.draw(
                    image, dets, style=self._style, use_label_mapping=self.use_label_mapping,
                )

            boxes = result.boxes
            kwargs: dict = {}
            if task_type == "segment":
                if hasattr(result, "masks") and result.masks is not None:
                    kwargs["masks"] = result.masks.xy if hasattr(result.masks, "xy") else None
                kwargs["task_type"] = "segment"
            elif task_type == "pose":
                if hasattr(result, "keypoints") and result.keypoints is not None:
                    kwargs["keypoints"] = result.keypoints.data.cpu().numpy()
                kwargs["task_type"] = "pose"
            elif task_type == "obb":
                if hasattr(result, "obb") and result.obb is not None:
                    kwargs["obb"] = result.obb.xyxyxyxy.cpu().numpy() if n else None
                kwargs["task_type"] = "obb"
            else:
                kwargs["task_type"] = "detect"

            dets = BeautifyVisualizer.from_yolo_results(
                boxes=(boxes.xyxy.cpu().numpy() if n else _empty_boxes()),
                confidences=(boxes.conf.cpu().numpy() if n else _empty_conf()),
                labels=labels,
                **kwargs,
            )
            return self.visualizer.draw(
                image, dets, style=self._style, use_label_mapping=self.use_label_mapping,
            )
        return result.plot()


def _empty_boxes():
    return np.zeros((0, 4), dtype=float)


def _empty_conf():
    return np.zeros((0,), dtype=float)


def _get_task_type(model) -> str:
    """Extract task type from a loaded YOLO model.

    Returns one of: "detect", "segment", "pose", "classify", "obb".
    """
    overrides = getattr(model, "overrides", {}) or {}
    task = overrides.get("task", "") or getattr(model, "task", "") or "detect"
    return str(task)


def infer_yolo(
    yaml_path: str | Path | None = None,
    pipeline_yaml: str | Path | None = None,
    cli_args: dict[str, Any] | None = None,
    *,
    beautify: bool = True,
    rename_log: bool = True,
    threaded: bool = False,
    warmup_frames: int = 0,
    stride: int | None = None,
    window_name: str = "odp-infer",
    show_info: bool = True,
    output_sink: OutputSink | None = None,
    hooks: InferHooks | None = None,
    cancel_token: CancelToken | None = None,
) -> InferResult:
    """一行启动推理 —— 风格跟 D5 build_infer_config / D6 train_yolo 一致."""
    service = InferService()
    return service.predict(
        yaml_path=yaml_path,
        pipeline_yaml=pipeline_yaml,
        cli_args=cli_args if isinstance(cli_args, Namespace) else Namespace(**cli_args) if cli_args else None,
        beautify=beautify,
        rename_log=rename_log,
        threaded=threaded,
        warmup_frames=warmup_frames,
        stride=stride,
        window_name=window_name,
        show_info=show_info,
        output_sink=output_sink,
        hooks=hooks,
        cancel_token=cancel_token,
    )


async def infer_yolo_async(
    source: str,
    model_path: str | Path,
    *,
    yaml_path: str | Path | None = None,
    pipeline_yaml: str | Path | None = None,
    conf: float = 0.25,
    iou: float = 0.7,
    imgsz: int = 640,
    device: str | None = None,
    stride: int = 1,
    show: bool = False,
) -> AsyncIterator[dict[str, Any]]:
    """异步逐帧推理 — 适合 FastAPI / web 场景.

    Yields per-frame dicts: ``{"frame_idx": int, "detections": list[dict], ...}``

    Example::

        async for result in infer_yolo_async("0", "yolo11n.pt"):
            print(result["frame_idx"], len(result["detections"]))
    """
    if YOLO is None:
        raise ImportError("ultralytics is required for inference. Install with: pip install ultralytics")

    from od_platform.frame_source import create_async_source

    model = YOLO(str(model_path))
    class_names: list[str] = list(model.names.values())

    predict_kwargs: dict[str, Any] = {
        "conf": conf, "iou": iou, "imgsz": imgsz,
        "verbose": False,
    }
    if device:
        predict_kwargs["device"] = device

    async_source = create_async_source(source)
    await async_source.open()
    async_source.set_stride(stride)

    frame_idx = 0
    try:
        async for frame in async_source:
            results = await asyncio.to_thread(
                model, frame.image, **predict_kwargs
            )
            result = results[0]
            boxes = result.boxes
            n = 0 if boxes is None else len(boxes)

            detections = []
            if n:
                xyxy = boxes.xyxy.cpu().numpy()
                confs = boxes.conf.cpu().numpy()
                cls_ids = boxes.cls.int().cpu().tolist()
                for i in range(n):
                    detections.append({
                        "box": [float(x) for x in xyxy[i]],
                        "confidence": float(confs[i]),
                        "label": class_names[cls_ids[i]],
                    })

            yield {
                "frame_idx": frame_idx,
                "detections": detections,
                "n_detections": n,
                "speed": getattr(result, "speed", None),
            }
            frame_idx += 1
    finally:
        await async_source.close()
