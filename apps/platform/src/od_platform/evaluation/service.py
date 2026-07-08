#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : service.py
# @Project   : ODPlatform
# @Function  : ValService —— 编排 D5 配置 + D3 解析 + D2 日志 + ultralytics 评估
"""评估编排器。不发明、不归档、不 import training;只编排、防御、审计、兜底。"""
from __future__ import annotations

import json
import logging
from argparse import Namespace
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from od_platform.common.config_log import log_effective_config, log_override_chains
from od_platform.common.log_rename import rename_log_to_save_dir
from od_platform.common.refs import resolve_trained_model, resolve_yaml
from od_platform.common.result import TrainMetrics, log_train_metrics
from od_platform.common.system_utils import log_device_info
from od_platform.runtime_config import build_val_config

logger = logging.getLogger(__name__)

# 语义别名:物理 SSoT 仍在 common.result
ValMetrics = TrainMetrics


@dataclass(frozen=True)
class ValResult:
    """一次评估的结果事实(不可变载体)。"""
    success: bool
    save_dir: Optional[Path]
    metrics: Optional[ValMetrics]
    error: Optional[str] = None
    # 注意:没有 best_weight —— 评估不产权重(撞墙②)


class ValService:
    """评估编排器:不发明、不归档、永不抛异常。"""

    def evaluate(
        self, config_path: str, model: str, data: str, *,
        cli_overrides: Optional[dict] = None, rename_log: bool = True,
    ) -> ValResult:
        try:
            return self._evaluate(config_path, model, data,
                                  cli_overrides=cli_overrides, rename_log=rename_log)
        except Exception as e:
            logger.error(f"评估失败:{e}", exc_info=True)
            return ValResult(False, None, None, error=str(e))

    def _evaluate(self, config_path, model, data, *, cli_overrides, rename_log) -> ValResult:
        # 1) 配置(走 D5 build_val_config)
        cli_ns = Namespace(**cli_overrides) if cli_overrides else None
        config, merger = build_val_config(config_path, cli_ns)
        log_effective_config(config, merger, logger=logger)
        log_override_chains(config, merger, logger=logger)

        # 2) 模型解析 + fail-fast(走 D3 refs)
        weight = resolve_trained_model(model)
        if not weight.exists():
            return ValResult(False, None, None,
                error=f"找不到已训练权重:{weight}。请确认名字正确、且已被 D6 归档到 models/trained/。")

        # 3) 数据集 yaml(走 D3 refs)
        data_yaml = resolve_yaml(data)

        # 4) 环境快照(走 D2)
        log_device_info(target_logger=logger)

        # 5) 评估(@time_it 计时)
        results = self._run_eval(str(weight), config, data_yaml)

        # 6) 提取产物
        save_dir = self._extract_save_dir(results)
        metrics = self._extract_metrics(results, config.task)
        log_train_metrics(metrics, logger=logger)

        # 7) 训练后整理:只对齐日志名 —— 【没有 archive】(撞墙②)
        if rename_log and save_dir is not None:
            rename_log_to_save_dir(save_dir, weight.stem)

        # 8) 审计(kind=val,区别于 train)
        self._write_audit(save_dir, config, metrics)

        return ValResult(True, save_dir, metrics)

    @staticmethod
    def _run_eval(weight: str, config, data_yaml):
        from ultralytics import YOLO
        model = YOLO(weight)
        return model.val(data=str(data_yaml), **config.to_ultralytics_kwargs())

    @staticmethod
    def _extract_save_dir(results) -> Optional[Path]:
        sd = getattr(results, "save_dir", None)
        if sd is None:
            sd = getattr(getattr(results, "speed", None), "save_dir", None)
        return Path(sd) if sd else None

    @staticmethod
    def _extract_metrics(results, task: str) -> ValMetrics:
        box = getattr(results, "box", None)
        rd = getattr(results, "results_dict", {}) or {}
        g = lambda a, k: float(getattr(box, a, None) or rd.get(k, 0.0)) if box else float(rd.get(k, 0.0))
        return ValMetrics(
            task=task,
            fitness=float(getattr(results, "fitness", 0.0) or rd.get("fitness", 0.0)),
            map50=g("map50", "metrics/mAP50(B)"),
            map50_95=g("map", "metrics/mAP50-95(B)"),
            precision=g("mp", "metrics/precision(B)"),
            recall=g("mr", "metrics/recall(B)"),
        )

    @staticmethod
    def _write_audit(save_dir, config, metrics) -> None:
        if save_dir is None:
            return
        audit = {
            "kind": "val",
            "utc": datetime.now(timezone.utc).isoformat(),
            "config": config.to_audit_snapshot(),
            "metrics": {
                "fitness": metrics.fitness, "map50": metrics.map50,
                "map50_95": metrics.map50_95, "precision": metrics.precision, "recall": metrics.recall,
            },
            "save_dir": str(save_dir),
        }
        out = Path(save_dir) / "odp_audit.json"
        out.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"审计快照已写入:{out}")


def evaluate_yolo(
    config_path: str, model: str, data: str, *,
    cli_overrides: Optional[dict] = None, rename_log: bool = True,
) -> ValResult:
    """便捷函数:内部就是 ValService().evaluate(...)。"""
    return ValService().evaluate(
        config_path, model, data, cli_overrides=cli_overrides, rename_log=rename_log,
    )
