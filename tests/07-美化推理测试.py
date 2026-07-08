#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :07-美化推理测试.py
# @Time      :2026/7/8
# @Author    :雨霓同学
# @Project   :ODPlatform
# @Function  :加载 YOLO 模型做推理 + BeautifyVisualizer 美化绘制
from __future__ import annotations

import cv2
from ultralytics import YOLO

from od_platform.frame_source import create_frame_source, CameraConfig
from od_platform.visualization import BeautifyVisualizer, Detection

# ── 模型 & 输入源 ──────────────────────────────────────────
MODEL_PATH = "train3-20250704-165500-yolo11n-best.pt"
SOURCE = "0"

# ── 标签映射 ───────────────────────────────────────────────
LABEL_MAPPING = {
    "person":          "人员",
    "safety_helmet":   "安全帽",
    "reflective_vest": "反光衣",
    "head":            "未佩戴安全帽",
    "ordinary_clothes": "未穿戴反光衣"
}

# ── BGR 颜色 (B=G) ─────────────────────────────────────────
COLOR_MAPPING = {
    "person":          (0, 0, 255),     # 红
    "safety_helmet":   (255, 255, 0),   # 青
    "reflective_vest": (128, 128, 255), # 粉
    "head":            (0, 0, 160),     # 深红
    "ordinary_clothes": (207, 74, 52),
}

if __name__ == "__main__":
    # 1. 加载模型
    model = YOLO(MODEL_PATH)
    names = model.names or {}
    labels = [names[i] for i in sorted(names.keys())]

    # 2. 构造美化器
    viz = BeautifyVisualizer(
        labels=labels,
        label_mapping=LABEL_MAPPING,
        color_mapping=COLOR_MAPPING,
        default_color=(200, 200, 200),
    )

    # 3. 打开摄像头 (MSMF + 90FPS) + 逐帧推理
    with create_frame_source(SOURCE, camera_config=CameraConfig(
        camera_id=0, backend="msmf", codec="MJPG", fps=90,
    )) as src:
        for frame in src:
            results = model(frame.image, conf=0.25, verbose=False)
            boxes = results[0].boxes

            if boxes is not None:
                detections = [
                    Detection(
                        box=(int(b[0]), int(b[1]), int(b[2]), int(b[3])),
                        confidence=float(b[4]),
                        label=names.get(int(b[5]), f"cls_{int(b[5])}"),
                    )
                    for b in boxes.data.cpu().numpy()
                ]
            else:
                detections = []

            annotated = viz.draw(frame.image, detections, use_label_mapping=True)

            cv2.imshow("美化推理", annotated)
            if cv2.pollKey() & 0xFF == ord('q'):
                break
    cv2.destroyAllWindows()
