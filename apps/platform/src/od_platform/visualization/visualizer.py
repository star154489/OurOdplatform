#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : visualizer.py
# @Author    : 雨霓同学
# @Project   : visualization
# @Function  : 美化可视化器 — cv2 画框 + Pillow 画文本, 支持 detect/segment/pose/obb/classify
"""美化可视化器。

职责: 美化绘制 YOLO 检测/分割/姿态/OBB/分类结果(支持中英文)。
适用: 需要圆角框 / 自定义字体 / 中文标签 / 标签映射的场景。
不适用: 朴素 YOLO 绘制(直接 results[0].plot() 更简单)。

特点:
  - cv2 绘制智能圆角框(角落自适应:标签贴上方/下方/内嵌时圆角动态切换)
  - Pillow 绘制文本(无 BGR<->RGB 转换开销)
  - 文本尺寸启动期预计算,运行期 O(1) 查表
  - 按 Detection 中非 None 字段自动选择绘制路径 (detect/segment/pose/obb/classify)
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from .core.data_types import Detection, DrawStyle
from .core.draw_utils import LayoutCalculator, RoundedRect
from .core.renderers import PillowTextRenderer
from .core.text_cache import TextSizeCache

# ── COCO 姿态骨架连接定义 ──────────────────────────────────────────
# 17 个关键点的 COCO 格式骨架
COCO_SKELETON: List[Tuple[int, int]] = [
    (0, 1), (0, 2), (1, 3), (2, 4),          # 头 → 肩 → 肘
    (5, 6),                                    # 肩之间
    (5, 7), (7, 9), (6, 8), (8, 10),          # 左臂 + 右臂
    (5, 11), (6, 12), (11, 12),               # 肩 → 髋
    (11, 13), (13, 15), (12, 14), (14, 16),   # 腿
]

_COCO_PAIR_COLORS: List[Tuple[int, int, int]] = [
    (255, 102, 102), (255, 102, 102), (102, 255, 102), (102, 255, 102),
    (255, 153, 51),
    (255, 102, 255), (255, 102, 255), (102, 255, 255), (102, 255, 255),
    (255, 178, 102), (255, 178, 102), (255, 178, 102),
    (153, 102, 255), (153, 102, 255), (255, 255, 102), (255, 255, 102),
]


class BeautifyVisualizer:
    """YOLO 检测结果美化可视化器。

    使用场景:
      - 需要美化效果(圆角框、自定义字体)
      - 需要中文标签显示
      - 需要标签映射(如 person -> 人员)

    若不需要美化,请直接用 YOLO 原生 ``results[0].plot()``。
    """

    def __init__(
            self,
            labels: List[str],
            label_mapping: Optional[Dict[str, str]] = None,
            color_mapping: Optional[Dict[str, Tuple[int, int, int]]] = None,
            default_color: Tuple[int, int, int] = (0, 255, 0),
            font_path: Optional[str] = None,
            font_sizes: Optional[Tuple[int, ...]] = None,
    ):
        """初始化美化可视化器。

        Args:
            labels: 标签列表(英文原始标签,如 YOLO 模型的 names)
            label_mapping: 标签映射字典(例如:{"person": "人员", "car": "汽车"})
            color_mapping: 颜色映射字典,键为原始标签,值为 BGR 颜色
            default_color: 默认颜色 (BGR)
            font_path: 字体绝对路径;None 时使用模块内置字体
                       (visualization/assets/LXGWWenKai-Bold.ttf)
            font_sizes: 预计算的字号范围
        """
        self.label_mapping = label_mapping or {}
        self.color_mapping = color_mapping or {}
        self.default_color = default_color

        # 文本尺寸缓存(font_path=None 时由 TextSizeCache 内部解析模块内置字体)
        self._size_cache = TextSizeCache(
            labels=labels,
            label_mapping=label_mapping,
            font_path=font_path,
            font_sizes=font_sizes,
        )

        # Pillow 文本渲染器
        self._renderer = PillowTextRenderer(size_cache=self._size_cache)

    # ── 主入口 ─────────────────────────────────────────────────────

    def draw(
            self,
            image: np.ndarray,
            detections: List[Detection],
            style: Optional[DrawStyle] = None,
            use_label_mapping: bool = False,
    ) -> np.ndarray:
        """美化绘制检测结果 — 按 Detection 中非 None 字段自动选择路径。

        Args:
            image: 输入图像 (BGR)
            detections: 检测结果列表
            style: 绘制样式(None 则根据图像尺寸自动生成)
            use_label_mapping: 是否使用标签映射

        Returns:
            绘制后的图像 (BGR)
        """
        if not detections:
            return image.copy()

        h, w = image.shape[:2]
        style = style or DrawStyle.from_image_size(h, w)

        result = image.copy()

        # ── 检测任务类型(sample first detection) ──
        first = detections[0]

        # classify: 无 box, 有 probs → 右上角条形图
        if first.probs is not None:
            result = self._draw_classify(result, detections, style, use_label_mapping)
            return result

        # segment: 先在原图上叠加 mask, 再画框
        has_masks = any(d.mask is not None for d in detections)
        if has_masks:
            result = self._draw_masks(result, detections, style)

        # pose: 先画骨架线 + 关键点
        has_keypoints = any(d.keypoints is not None for d in detections)
        if has_keypoints:
            result = self._draw_pose(result, detections, style)

        # obb: 旋转框
        has_obb = any(d.obb is not None for d in detections)
        if has_obb:
            result = self._draw_obb(result, detections, style)

        # ── 通用: 画 box + label ──
        texts: List[Tuple[str, Tuple[int, int], Tuple[int, int, int]]] = []

        for det in detections:
            if det.box is None:
                continue
            x1, y1, x2, y2 = det.box
            color = self.color_mapping.get(det.label, det.color or self.default_color)

            display_label = (
                self.label_mapping.get(det.label, det.label)
                if use_label_mapping
                else det.label
            )
            label_text = f"{display_label} {det.confidence * 100:.1f}%"

            text_size = self._size_cache.get_size(display_label, style.font_size)

            layout = LayoutCalculator.compute(det.box, text_size, (h, w), style)

            det_corners = LayoutCalculator.get_corners(layout, for_detection=True)
            label_corners = LayoutCalculator.get_corners(layout, for_detection=False)

            # 1. 检测框(圆角边框)
            RoundedRect.bordered(
                result, (x1, y1), (x2, y2),
                color, style.line_width, style.radius, det_corners,
            )

            # 2. 标签背景(圆角填充)
            lx1, ly1, lx2, ly2 = layout.box
            RoundedRect.filled(
                result, (lx1, ly1), (lx2, ly2),
                color, style.radius, label_corners,
            )

            # 3. 收集文本
            texts.append((label_text, layout.text_pos, style.text_color))

        # 4. Pillow 批量渲染文本
        if texts:
            result = self._renderer.render_batch(result, texts, style)

        return result

    # ── 任务特定绘制 ────────────────────────────────────────────────

    def _draw_masks(
        self, image: np.ndarray, detections: List[Detection], style: DrawStyle
    ) -> np.ndarray:
        """叠加分割掩码(半透明填充 + 轮廓)."""
        overlay = image.copy()
        for det in detections:
            if det.mask is None:
                continue
            color = self.color_mapping.get(det.label, det.color or self.default_color)
            mask = np.asarray(det.mask, dtype=np.int32)
            if mask.ndim == 2 and mask.shape[1] >= 3:
                # Polygon format (N, 2)
                cv2.fillPoly(overlay, [mask.reshape(-1, 1, 2)], color)
                cv2.polylines(overlay, [mask.reshape(-1, 1, 2)], True, color, 2, cv2.LINE_AA)
        cv2.addWeighted(overlay, style.mask_alpha, image, 1 - style.mask_alpha, 0, image)
        return image

    def _draw_pose(
        self, image: np.ndarray, detections: List[Detection], style: DrawStyle
    ) -> np.ndarray:
        """绘制骨架连线 + 关键点."""
        for det in detections:
            if det.keypoints is None:
                continue
            kpts = np.asarray(det.keypoints, dtype=np.float32)
            if kpts.ndim != 2 or kpts.shape[1] < 3:
                continue
            # Draw skeleton
            for idx, (i, j) in enumerate(COCO_SKELETON):
                if i >= len(kpts) or j >= len(kpts):
                    continue
                if kpts[i][2] > 0.5 and kpts[j][2] > 0.5:
                    color = _COCO_PAIR_COLORS[idx % len(_COCO_PAIR_COLORS)]
                    pt1 = (int(kpts[i][0]), int(kpts[i][1]))
                    pt2 = (int(kpts[j][0]), int(kpts[j][1]))
                    cv2.line(image, pt1, pt2, color, style.skeleton_thickness, cv2.LINE_AA)
            # Draw keypoints
            for kp in kpts:
                if kp[2] > 0.5:
                    cx, cy = int(kp[0]), int(kp[1])
                    cv2.circle(image, (cx, cy), style.keypoint_radius, (0, 255, 255), -1, cv2.LINE_AA)
                    cv2.circle(image, (cx, cy), style.keypoint_radius, (0, 0, 0), 1, cv2.LINE_AA)
        return image

    def _draw_obb(
        self, image: np.ndarray, detections: List[Detection], style: DrawStyle
    ) -> np.ndarray:
        """绘制旋转边界框(OBB)."""
        for det in detections:
            if det.obb is None:
                continue
            color = self.color_mapping.get(det.label, det.color or self.default_color)
            obb = np.asarray(det.obb, dtype=np.float32)
            if obb.ndim == 1 and len(obb) == 5:
                # (cx, cy, w, h, angle_rad) → 4 corner points
                rect = ((obb[0], obb[1]), (obb[2], obb[3]), obb[4] * 180.0 / np.pi)
                pts = cv2.boxPoints(rect)
            elif obb.ndim == 2 and obb.shape == (4, 2):
                pts = obb
            else:
                continue
            pts = pts.astype(np.int32)
            cv2.drawContours(image, [pts], 0, color, style.line_width, cv2.LINE_AA)
        return image

    def _draw_classify(
        self,
        image: np.ndarray,
        detections: List[Detection],
        style: DrawStyle,
        use_label_mapping: bool,
    ) -> np.ndarray:
        """绘制分类结果 — 右上角 top-K 条形图."""
        h, w = image.shape[:2]
        det = detections[0]  # classification has single "detection" with probs
        if det.probs is None:
            return image

        # Panel in top-right corner
        bar_w = min(220, w // 3)
        bar_h_per = 28
        panel_h = len(det.probs) * bar_h_per + 20
        x0, y0 = w - bar_w - 20, 20

        # Semi-transparent background
        overlay = image.copy()
        cv2.rectangle(overlay, (x0, y0), (x0 + bar_w, y0 + panel_h), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.55, image, 0.45, 0, image)

        font = cv2.FONT_HERSHEY_SIMPLEX
        fs = 0.5

        for idx, (cls_name, prob) in enumerate(det.probs):
            y = y0 + 16 + idx * bar_h_per
            color = self.color_mapping.get(cls_name, self.default_color)

            # Label
            display = (
                self.label_mapping.get(cls_name, cls_name)
                if use_label_mapping
                else cls_name
            )
            cv2.putText(image, f"{display}", (x0 + 8, y), font, fs, (220, 220, 220), 1, cv2.LINE_AA)

            # Confidence bar
            bar_start = x0 + 100
            bar_len = int((bar_w - 112) * prob)
            cv2.rectangle(image, (bar_start, y - 11), (bar_start + bar_len, y + 5), color, -1)

            # Percentage text
            pct_text = f"{prob * 100:.1f}%"
            cv2.putText(image, pct_text, (bar_start + bar_len + 4, y), font, 0.45, (200, 200, 200), 1, cv2.LINE_AA)

        return image

    # ── YOLO 结果 → Detection ──────────────────────────────────────

    @staticmethod
    def from_yolo_results(
            boxes: np.ndarray,
            confidences: np.ndarray,
            labels: List[str],
            color_mapping: Optional[Dict[str, Tuple[int, int, int]]] = None,
            *,
            task_type: str = "detect",
            masks: Optional[np.ndarray] = None,
            keypoints: Optional[np.ndarray] = None,
            obb: Optional[np.ndarray] = None,
            probs: Optional[List[Tuple[str, float]]] = None,
    ) -> List[Detection]:
        """从 YOLO 推理结果创建 Detection 列表。

        Args:
            boxes: (N,4) xyxy 数组 (classify 时为空)
            confidences: (N,) 置信度数组
            labels: 标签名列表
            color_mapping: 可选的颜色映射
            task_type: "detect" / "segment" / "pose" / "obb" / "classify"
            masks: 分割掩码 (segment)
            keypoints: 姿态关键点 (pose)
            obb: 旋转框 (obb)
            probs: 分类 top-K (classify)
        """
        color_mapping = color_mapping or {}
        n = len(confidences)

        if task_type == "classify":
            return [
                Detection(
                    box=None,
                    confidence=confidences[0] if len(confidences) > 0 else 0.0,
                    label=labels[0] if labels else "",
                    color=color_mapping.get(labels[0] if labels else "", (0, 255, 0)),
                    probs=probs,
                )
            ]

        detections: List[Detection] = []
        for i in range(n):
            det = Detection(
                box=(
                    int(boxes[i][0]), int(boxes[i][1]),
                    int(boxes[i][2]), int(boxes[i][3]),
                ),
                confidence=float(confidences[i]),
                label=labels[i],
                color=color_mapping.get(labels[i], (0, 255, 0)),
            )
            if task_type == "segment" and masks is not None and i < len(masks):
                det.mask = masks[i]
            if task_type == "pose" and keypoints is not None and i < len(keypoints):
                det.keypoints = keypoints[i]
            if task_type == "obb" and obb is not None and i < len(obb):
                det.obb = obb[i]
            detections.append(det)

        return detections
