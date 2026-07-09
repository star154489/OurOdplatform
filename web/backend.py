#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ODPlatform 目标检测 Web API — FastAPI 后端
============================================
整合现有 od_platform 推理逻辑，提供图片识别 HTTP 接口。
支持单张图片和批量图片上传识别。

启动方式:
    cd <项目根目录>
    python web/backend.py

API 接口:
    GET  /              前端页面
    POST /api/detect     上传图片进行目标检测
    GET  /api/models     获取可用模型列表
    GET  /api/health     健康检查
"""

from __future__ import annotations

import base64
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ═══════════════════════════════════════════════════════════════════════════════
# 路径初始化：自动查找 workspace 根目录（通过 .odp-workspace 标记文件）
# ═══════════════════════════════════════════════════════════════════════════════


def _find_workspace_root() -> Path:
    """根据 .odp-workspace 标记文件向上查找项目根目录。"""
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / ".odp-workspace").exists():
            return parent
    # 兜底：从当前工作目录查找
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".odp-workspace").exists():
            return parent
    raise FileNotFoundError(
        "找不到 .odp-workspace 标记文件，请确保在 ODPlatform 项目根目录下运行。"
        f"当前后端文件路径: {Path(__file__).resolve()}"
    )


ROOT = _find_workspace_root()
SRC = ROOT / "apps" / "platform" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# ═══════════════════════════════════════════════════════════════════════════════
# 导入 od_platform 模块
# ═══════════════════════════════════════════════════════════════════════════════
from ultralytics import YOLO

from od_platform.common.model_path import resolve_model_path
from od_platform.visualization import BeautifyVisualizer, Detection

# ═══════════════════════════════════════════════════════════════════════════════
# 日志 & 常量
# ═══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("odp-web")

MAX_IMAGE_DIM = 1920       # 图片最大尺寸（像素），超出等比例缩小
JPEG_QUALITY = 85           # JPEG 编码质量 (1-100)
DEFAULT_MODEL_NAME = "best.pt"
DEFAULT_CONF = 0.25

# 模型搜索目录（按优先级）
MODEL_SEARCH_DIRS: List[Path] = [
    ROOT,                                  # 项目根 (yolo11n.pt, yolo26n.pt)
    ROOT / "models" / "pretrained",        # 预训练模型
    ROOT / "models" / "trained",           # 训练归档模型
    ROOT / "epoch",                        # epoch 训练产出
]

# ═══════════════════════════════════════════════════════════════════════════════
# FastAPI 应用初始化
# ═══════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="ODPlatform 目标检测 Web API",
    version="1.0.0",
    description="基于 YOLO 的通用目标检测 Web 服务接口",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件：前端页面
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# ═══════════════════════════════════════════════════════════════════════════════
# 全局模型 & 可视化器（懒加载）
# ═══════════════════════════════════════════════════════════════════════════════

_yolo_model: Optional[YOLO] = None
_visualizer: Optional[BeautifyVisualizer] = None
_class_names: List[str] = []
_model_name_loaded: str = ""
_device: str = "cpu"


def _get_device() -> str:
    """检测可用设备 (CUDA > MPS > CPU)。"""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda:0"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def load_model(model_name: str = DEFAULT_MODEL_NAME) -> Dict[str, Any]:
    """加载 YOLO 模型 + BeautifyVisualizer。

    Returns:
        dict: {"status": "ok" | "error", "model_name": ..., "device": ..., "classes": [...]}
    """
    global _yolo_model, _visualizer, _class_names, _model_name_loaded, _device

    try:
        _device = _get_device()
        model_path = resolve_model_path(model_name, search_dirs=MODEL_SEARCH_DIRS)
        model_path_str = str(model_path)

        logger.info(f"正在加载模型: {model_path_str}, 设备: {_device}")

        _yolo_model = YOLO(model_path_str)
        if _device != "cpu":
            try:
                _yolo_model.to(_device)
            except Exception:
                logger.warning(f"模型切换 {_device} 失败，退回 CPU")

        _class_names = list(_yolo_model.names.values())
        _model_name_loaded = model_name

        # 初始化美化可视化器
        _visualizer = BeautifyVisualizer(labels=_class_names)

        logger.info(f"模型加载完成: {model_path_str}, 类别数: {len(_class_names)}")
        return {
            "status": "ok",
            "model_name": model_name,
            "model_path": model_path_str,
            "device": _device,
            "classes": _class_names,
            "num_classes": len(_class_names),
        }
    except Exception as e:
        logger.error(f"模型加载失败: {e}")
        return {"status": "error", "message": str(e)}


def _ensure_model(model_name: Optional[str] = None) -> Dict[str, Any]:
    """确保模型已加载；若未加载或名称不同则重新加载。"""
    name = model_name or DEFAULT_MODEL_NAME
    if _yolo_model is None or _model_name_loaded != name:
        return load_model(name)
    return {"status": "ok", "model_name": _model_name_loaded, "device": _device}


def _resize_image(img: np.ndarray, max_dim: int = MAX_IMAGE_DIM) -> np.ndarray:
    """等比例缩小图片，保持长边不超过 max_dim。"""
    h, w = img.shape[:2]
    if max(h, w) <= max_dim:
        return img
    scale = max_dim / max(h, w)
    new_w, new_h = int(w * scale), int(h * scale)
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)


def _img_to_base64(img: np.ndarray) -> str:
    """将 BGR numpy 图片编码为 base64 data URI 字符串。"""
    # OpenCV 直接编码为 JPEG
    _, jpg_bytes = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    b64 = base64.b64encode(jpg_bytes.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _infer_single(image_bgr: np.ndarray, conf: float) -> Dict[str, Any]:
    """对单张 BGR 图片执行推理，返回检测结果。

    Returns:
        dict: {
            "detections": [{"label": str, "confidence": float, "box": [x1,y1,x2,y2]}, ...],
            "count": int,
            "annotated_bgr": np.ndarray
        }
    """
    results = _yolo_model(image_bgr, conf=conf, verbose=False)
    result = results[0]
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return {"detections": [], "count": 0, "annotated_bgr": image_bgr.copy()}

    n = len(boxes)
    xyxy = boxes.xyxy.cpu().numpy()
    confs = boxes.conf.cpu().numpy()
    cls_ids = boxes.cls.int().cpu().tolist()

    labels = [_class_names[i] for i in cls_ids]
    detections_list = [
        {
            "label": lbl,
            "confidence": round(float(c), 4),
            "box": [int(x) for x in xyxy[i]],
        }
        for i, (lbl, c) in enumerate(zip(labels, confs))
    ]

    # 美化绘制
    if _visualizer is not None:
        dets = BeautifyVisualizer.from_yolo_results(
            boxes=xyxy, confidences=confs, labels=labels,
        )
        annotated = _visualizer.draw(image_bgr, dets)
    else:
        annotated = result.plot()

    return {
        "detections": detections_list,
        "count": n,
        "annotated_bgr": annotated,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# API 路由
# ═══════════════════════════════════════════════════════════════════════════════


@app.get("/", response_class=HTMLResponse)
async def index():
    """返回前端页面。"""
    html_path = FRONTEND_DIR / "index.html"
    if not html_path.exists():
        return HTMLResponse(
            "<h2>前端页面未找到</h2><p>请将 index.html 放置于 web/frontend/ 目录下。</p>",
            status_code=404,
        )
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/api/health")
async def health():
    """健康检查接口。"""
    return {
        "status": "ok",
        "model_loaded": _yolo_model is not None,
        "model_name": _model_name_loaded or "(未加载)",
        "device": _device,
    }


@app.get("/api/models")
async def list_models():
    """列出可用模型文件。"""
    models: List[Dict[str, Any]] = []
    seen = set()
    for d in MODEL_SEARCH_DIRS:
        if not d.exists():
            continue
        for f in sorted(d.iterdir()):
            if f.suffix.lower() in (".pt", ".pth") and f.name not in seen:
                seen.add(f.name)
                size_mb = round(f.stat().st_size / (1024 * 1024), 1)
                models.append({
                    "name": f.name,
                    "path": str(f.relative_to(ROOT)),
                    "size_mb": size_mb,
                })
    models.sort(key=lambda m: m["name"])
    return {"models": models, "default": DEFAULT_MODEL_NAME}


@app.post("/api/detect")
async def detect(
    files: List[UploadFile] = File(..., description="图片文件 (可多选)"),
    model: Optional[str] = Form(None, description="模型文件名"),
    conf: Optional[float] = Form(None, ge=0.0, le=1.0, description="置信度阈值"),
    custom_hint: Optional[str] = Form("", description="自定义提示文字"),
):
    """图片目标检测接口。

    支持:
      - 单张图片上传
      - 多张图片批量上传（等价于文件夹上传）

    返回每张图片的:
      - 原始图片 (base64)
      - 检测框效果图 (base64)
      - 检测目标列表（类别、置信度、坐标框）
      - 系统提示文字
    """
    # ── 参数处理 ──
    conf_value = conf if conf is not None else DEFAULT_CONF
    hint = custom_hint or ""

    # ── 确保模型已加载 ──
    model_result = _ensure_model(model)
    if model_result.get("status") == "error":
        return JSONResponse(
            {"success": False, "error": f"模型加载失败: {model_result['message']}"},
            status_code=500,
        )

    if _yolo_model is None:
        return JSONResponse(
            {"success": False, "error": "模型未加载，请先调用 /api/health 确认状态"},
            status_code=500,
        )

    # ── 逐张推理 ──
    results: List[Dict[str, Any]] = []
    total_detections = 0

    for f in files:
        try:
            contents = await f.read()
            # OpenCV 解码
            nparr = np.frombuffer(contents, np.uint8)
            img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img_bgr is None:
                results.append({
                    "filename": f.filename or "unknown",
                    "error": "无法解码图片，请确认文件格式正确",
                    "original": None,
                    "annotated": None,
                    "detections": [],
                    "count": 0,
                    "hint": hint,
                })
                continue

            # 大图缩放到合理尺寸
            img_bgr = _resize_image(img_bgr)

            # 执行推理
            infer_result = _infer_single(img_bgr, conf_value)
            annotated_bgr = infer_result.pop("annotated_bgr")

            # 编码为 base64
            original_b64 = _img_to_base64(img_bgr)
            annotated_b64 = _img_to_base64(annotated_bgr)

            count = infer_result["count"]
            total_detections += count

            # 自动生成系统提示
            auto_hint = _build_hint(count, infer_result["detections"], hint)

            results.append({
                "filename": f.filename or "unknown",
                "original": original_b64,
                "annotated": annotated_b64,
                "detections": infer_result["detections"],
                "count": count,
                "hint": auto_hint,
                "width": img_bgr.shape[1],
                "height": img_bgr.shape[0],
            })

        except Exception as e:
            logger.error(f"处理图片 '{f.filename}' 失败: {e}")
            results.append({
                "filename": f.filename or "unknown",
                "error": str(e),
                "original": None,
                "annotated": None,
                "detections": [],
                "count": 0,
                "hint": hint,
            })

    return {
        "success": True,
        "results": results,
        "total": len(results),
        "total_detections": total_detections,
        "model_used": _model_name_loaded,
        "conf_threshold": conf_value,
    }


def _build_hint(count: int, detections: List[Dict[str, Any]], user_hint: str) -> str:
    """根据检测结果生成系统提示文字。"""
    parts = []
    if user_hint:
        parts.append(user_hint)
    if count == 0:
        parts.append("系统提示: 未检测到任何目标对象，请尝试调整置信度阈值或更换图片。")
    else:
        # 统计各类别数量
        cls_counter: Dict[str, int] = {}
        for d in detections:
            lbl = d["label"]
            cls_counter[lbl] = cls_counter.get(lbl, 0) + 1
        summary = "，".join(f"{lbl}×{c}" for lbl, c in sorted(cls_counter.items()))
        parts.append(f"系统提示: 共检测到 {count} 个目标 ({summary})。")
    return " ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import threading
    import uvicorn
    import webbrowser

    logger.info(f"项目根目录: {ROOT}")
    logger.info(f"前端目录:   {FRONTEND_DIR}")
    logger.info(f"源文件路径: {SRC}")

    # 启动时预加载默认模型（可选，失败不阻塞服务启动）
    try:
        r = load_model(DEFAULT_MODEL_NAME)
        if r["status"] == "ok":
            logger.info(f"默认模型已就绪: {r['model_name']} on {r['device']}, {r['num_classes']} 类")
        else:
            logger.warning(f"默认模型未加载: {r.get('message', '未知')} — 首次请求时自动加载")
    except Exception as e:
        logger.warning(f"启动时模型预加载失败: {e} — 首次请求时自动加载")

    # 服务启动后自动打开浏览器
    def _open_browser():
        import time
        time.sleep(1.2)
        webbrowser.open("http://localhost:8000")

    threading.Thread(target=_open_browser, daemon=True).start()

    logger.info("启动 Web 服务: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
