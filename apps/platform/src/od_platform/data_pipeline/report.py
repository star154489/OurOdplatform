"""类别平衡报告 —— 只读、不修改、只提醒。

在划分之前打印一份类别平衡报告,让用户看到每类的图数/框数/占比,
以及"哪个类样本太少可能训不好",但绝不替用户删数据。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from od_platform.common.constants import (
    CLASS_MIN_BOX_SHARE,
    CLASS_MIN_BOXES_WARN,
    CLASS_MIN_IMAGES_HARD,
)
from od_platform.common.string_utils import (
    format_table_row,
    format_table_separator,
    get_display_width,
    pad_to_width,
)

logger = logging.getLogger(__name__)


@dataclass
class ClassStat:
    """一个类别的统计。"""
    name: str
    image_count: int
    box_count: int
    image_pct: float
    box_pct: float
    status: str  # "ok" / "warn" / "critical"


@dataclass
class ClassBalanceReport:
    """完整的类别平衡报告。"""
    stats: List[ClassStat]
    total_images: int
    total_boxes: int
    usefulness_img_floor: float  # 图像级有用性下限

    def to_table(self) -> List[str]:
        """返回格式化的表格行列表。"""
        lines: List[str] = []
        lines.append("类别平衡报告".center(60, "="))
        widths = [20, 10, 10, 10, 10, 10]
        aligns = ["left", "right", "right", "right", "right", "left"]
        lines.append(format_table_row(
            ["类别", "图数", "框数", "图%", "框%", "状态"], widths, aligns,
        ))
        lines.append(format_table_separator(widths))
        for s in self.stats:
            status_symbol = {"ok": "✓", "warn": "⚠", "critical": "✗"}.get(s.status, "?")
            lines.append(format_table_row([
                s.name, str(s.image_count), str(s.box_count),
                f"{s.image_pct:.1f}", f"{s.box_pct:.1f}", status_symbol,
            ], widths, aligns))
        lines.append(format_table_separator(widths))
        lines.append(f"共 {self.total_images} 张图, {self.total_boxes} 个框")
        lines.append(f"图像级有用性下限: {self.usefulness_img_floor:.2%}")
        return lines

    def print(self) -> None:
        for line in self.to_table():
            logger.info(line)

    def has_critical(self) -> bool:
        return any(s.status == "critical" for s in self.stats)


def analyze_class_balance(
    labels_per_image: Dict[str, List[str]],
    total_images: int,
    total_labels: int,
) -> ClassBalanceReport:
    """分析类别平衡情况。

    Args:
        labels_per_image: {图路径: [类别名]}。
        total_images: 参与分析的总图数。
        total_labels: 参与分析的总标注文件数。

    Returns:
        完整的类别平衡报告。
    """
    class_counts: Dict[str, Tuple[int, int]] = {}
    for img_path, names in labels_per_image.items():
        seen = set()
        for n in names:
            if n not in class_counts:
                class_counts[n] = [0, 0]
            class_counts[n][0] += 1  # image_count
            class_counts[n][1] += 1  # box_count
            seen.add(n)
        for n in seen:
            pass  # box_count already counted above

    # Re-do for correct counts
    class_img_count: Dict[str, int] = {}
    class_box_count: Dict[str, int] = {}
    for img_path, names in labels_per_image.items():
        seen_classes = set(names)
        for n in seen_classes:
            class_img_count[n] = class_img_count.get(n, 0) + 1
        for n in names:
            class_box_count[n] = class_box_count.get(n, 0) + 1

    stats: List[ClassStat] = []
    all_classes = sorted(class_img_count.keys())
    for name in all_classes:
        ic = class_img_count[name]
        bc = class_box_count[name]
        ip = ic / total_images * 100 if total_images else 0.0
        bp = bc / total_labels * 100 if total_labels else 0.0

        if ic < CLASS_MIN_IMAGES_HARD:
            status = "critical"
        elif bc < CLASS_MIN_BOXES_WARN:
            status = "warn"
        elif bp < CLASS_MIN_BOX_SHARE * 100:
            status = "warn"
        else:
            status = "ok"

        stats.append(ClassStat(
            name=name, image_count=ic, box_count=bc,
            image_pct=ip, box_pct=bp, status=status,
        ))

    usefulness = min((s.image_pct / 100.0 for s in stats), default=0.0)
    return ClassBalanceReport(
        stats=stats, total_images=total_images, total_boxes=total_labels,
        usefulness_img_floor=usefulness,
    )
