#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : data_types.py
# @Author    : 雨霓同学
# @Project   : visualization
# @Function  : 核心数据类型 — Detection / DrawStyle / LabelPosition / LabelLayout
"""核心数据类型。

设计纪律(对齐 frame_source):
    - 配置类(DrawStyle)用 Pydantic v2 + 字段约束,拼错/越界立刻 ValidationError
    - 运行时数据(Detection / LabelLayout)用 dataclass,创建成本低、不做验证
    - 配置层不绑 logger,验证失败直接 raise(由调用方决定如何处理)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── 运行时数据:dataclass ──────────────────────────────────────
@dataclass
class Detection:
    """单个检测结果(运行时数据,每帧高频创建)。

    按 YOLO 任务类型使用不同字段组合:

    - detect:  ``box`` + ``confidence`` + ``label``
    - segment: ``box`` + ``mask`` (Nx2 多边形点集)
    - pose:    ``box`` + ``keypoints`` (Kx3: x,y,conf)
    - obb:     ``obb`` (cx,cy,w,h,angle 或 4 角点)
    - classify:``probs`` (top-K 类别+置信度列表), ``box`` 为 None
    """
    box: Optional[Tuple[int, int, int, int]] = None  # (x1, y1, x2, y2), classify 时为 None
    confidence: float = 0.0
    label: str = ""
    color: Tuple[int, int, int] = (0, 255, 0)  # BGR
    # 按任务类型只填其一:
    mask: Optional[Any] = None           # np.ndarray — 分割多边形点集 (N,2)
    keypoints: Optional[Any] = None      # np.ndarray — 姿态关键点 (K,3): x,y,conf
    obb: Optional[Any] = None            # np.ndarray — OBB 4角点 (4,2) 或 (cx,cy,w,h,angle)
    probs: Optional[List[Tuple[str, float]]] = None  # 分类 top-K


class LabelPosition(Enum):
    """标签相对检测框的位置。"""
    ABOVE = auto()
    INSIDE_TOP = auto()
    BELOW = auto()


@dataclass
class LabelLayout:
    """标签布局信息(LayoutCalculator 的内部计算结果)。"""
    box: Tuple[int, int, int, int]
    text_pos: Tuple[int, int]
    position: LabelPosition
    align_right: bool = False
    label_wider: bool = False


# ── 配置类:Pydantic v2 ───────────────────────────────────────
class DrawStyle(BaseModel):
    """绘制样式配置。

    字段约束:
      - font_path=None 表示用模块内置字体(visualization/assets/LXGWWenKai-Bold.ttf)
      - 数值字段全部带上下界,防止用户写出负 padding / 巨型字号
      - text_color 是 BGR 三元组,每个分量 0-255
      - extra="forbid":字段名拼错(如 padding_X)当场 raise,不静默丢弃
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        frozen=False,
        arbitrary_types_allowed=False,
    )

    font_path: Optional[str] = Field(
        default=None,
        description="字体绝对路径;None 时由 TextSizeCache 解析为模块内置字体",
    )
    font_size: int = Field(default=26, gt=0, le=500, description="字号(像素)")
    line_width: int = Field(default=1, gt=0, le=50, description="检测框边框宽度")
    padding_x: int = Field(default=6, ge=0, le=500, description="标签内左右内边距")
    padding_y: int = Field(default=10, ge=0, le=500, description="标签内上下内边距")
    radius: int = Field(default=3, ge=0, le=500, description="圆角半径")
    text_color: Tuple[int, int, int] = Field(
        default=(0, 0, 0),
        description="文本 BGR 颜色",
    )

    # -- 任务特定样式 --
    mask_alpha: float = Field(default=0.4, ge=0.0, le=1.0, description="分割掩码透明度")
    keypoint_radius: int = Field(default=4, ge=1, le=20, description="姿态关键点半径")
    skeleton_thickness: int = Field(default=2, ge=1, le=10, description="姿态骨架线宽")

    @field_validator("text_color")
    @classmethod
    def _validate_color(cls, v: Tuple[int, int, int]) -> Tuple[int, int, int]:
        for c in v:
            if not isinstance(c, int) or not (0 <= c <= 255):
                raise ValueError(
                    f"text_color 每个分量必须是 0-255 之间的整数,得到 {v}"
                )
        return v

    @classmethod
    def from_image_size(
            cls,
            height: int,
            width: int,
            ref_dim: int = 720,
            base_font_size: int = 26,
            base_line_width: int = 2,
            base_padding_x: int = 10,
            base_padding_y: int = 10,
            base_radius: int = 8,
            font_scale: float = 1.0,
            **kwargs,
    ) -> "DrawStyle":
        """根据图像尺寸自适应计算样式参数。

        Args:
            font_scale: 字号缩放因子, pipeline_config 把 text_scale 映射到此参数,
                        例如 text_scale=0.6 → font_size = 计算值 × 0.6。
            其余 **kwargs 直接透传给 cls() (如 font_path / text_color / line_width 等)。

        计算流程: 自适应计算值 → ×font_scale → kwargs 覆盖 (YAML 硬值优先)。
        """
        scale = min(height, width) / max(ref_dim, 1)
        params = {
            "font_size": max(10, int(base_font_size * scale * font_scale)),
            "line_width": max(1, int(base_line_width * scale)),
            "padding_x": max(5, int(base_padding_x * scale)),
            "padding_y": max(5, int(base_padding_y * scale)),
            "radius": max(3, int(base_radius * scale)),
        }
        params.update(kwargs)  # 直接覆盖 (如 box_thickness→line_width 等绝对值)
        return cls(**params)
