"""BeautifyVisualizer 测试：加载模型 → 推理 → 美化绘制。"""
from __future__ import annotations
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from od_platform.visualization import BeautifyVisualizer, Detection, DrawStyle

# ── 配置 ──────────────────────────────────────────────────
MODEL_PATH = Path("models/trained/train3-20250704-165500-yolo11n-best.pt")
IMG_PATH   = Path("data/raw/VOC_SHWD/images/000000.jpg")
# 模型类别名（VOC_SHWD 是 hat/person 两类）
LABELS     = ["hat", "person"]

# ── 1. 加载模型 ──────────────────────────────────────────
model = YOLO(str(MODEL_PATH))
print(f"模型已加载: {MODEL_PATH.name}")

# ── 2. 初始化美化可视化器 ────────────────────────────────
viz = BeautifyVisualizer(
    labels=LABELS,
    label_mapping={"hat": "安全帽", "person": "人员"},
    color_mapping={"hat": (0, 255, 255), "person": (0, 255, 0)},
)

# ── 3. 读取图像 ──────────────────────────────────────────
img = cv2.imread(str(IMG_PATH))
if img is None:
    raise FileNotFoundError(f"无法读取图片: {IMG_PATH}")
print(f"图像尺寸: {img.shape[1]}x{img.shape[0]}")

# ── 4. 推理 ──────────────────────────────────────────────
results = model(img, verbose=False)[0]
boxes   = results.boxes.xyxy.cpu().numpy() if results.boxes is not None else np.empty((0, 4))
confs   = results.boxes.conf.cpu().numpy()  if results.boxes is not None else np.empty((0,))
cls_ids = results.boxes.cls.int().cpu().numpy() if results.boxes is not None else np.empty((0,), dtype=int)
names   = [results.names[int(c)] for c in cls_ids]

detections = [
    Detection(
        box=(int(b[0]), int(b[1]), int(b[2]), int(b[3])),
        confidence=float(c),
        label=n,
    )
    for b, c, n in zip(boxes, confs, names)
]
print(f"检测到 {len(detections)} 个目标")

# ── 5. 美化绘制 ──────────────────────────────────────────
style = DrawStyle.from_image_size(img.shape[0], img.shape[1], font_scale=0.8)
result = viz.draw(img, detections, style=style, use_label_mapping=True)

# ── 6. 保存结果 ──────────────────────────────────────────
out_path = "tests/test_result.jpg"
cv2.imwrite(out_path, result)
print(f"结果已保存: {out_path}")

# ── 统计信息 ─────────────────────────────────────────────
from collections import Counter
counts = Counter(n for _, _, _, n in zip(boxes, confs, names, names))
print("\n检测统计:")
for label, cnt in counts.most_common():
    print(f"  {label}: {cnt} 个")
