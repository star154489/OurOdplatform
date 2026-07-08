"""duplicate_annotations check — 检测重复标注。

两项检测:
    1. 完全重复行: 同一文件里完全相同的两行
    2. 近重复框: 同图同类 IoU >= DUPLICATE_BOX_IOU_THRESHOLD (0.95)

任何重复 → WARNING (可训但必须清理)。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple

from od_platform.common.constants import DUPLICATE_BOX_IOU_THRESHOLD, Task
from od_platform.data_validation.registry import (
    check, CheckContext, CheckResult, CheckSeverity,
)

PREVIEW_LIMIT = 20


def _iou_xywh(a: Tuple[float, ...], b: Tuple[float, ...]) -> float:
    """两个 (cx, cy, w, h) 归一化框的 IoU。"""
    ax1, ay1 = a[0] - a[2] / 2, a[1] - a[3] / 2
    ax2, ay2 = a[0] + a[2] / 2, a[1] + a[3] / 2
    bx1, by1 = b[0] - b[2] / 2, b[1] - b[3] / 2
    bx2, by2 = b[0] + b[2] / 2, b[1] + b[3] / 2
    inter_w = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    inter_h = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = inter_w * inter_h
    if inter <= 0.0:
        return 0.0
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


@check("duplicate_annotations")
def validate_duplicate_annotations(ctx: CheckContext) -> CheckResult:
    snap = ctx.snapshot

    exact_dup_count = 0
    near_dup_count  = 0
    exact_examples: List[Dict[str, Any]] = []
    near_examples:  List[Dict[str, Any]] = []
    total_lines = 0

    for split, labels in snap.labels_per_split.items():
        for lbl in labels:
            if not lbl.exists():
                continue
            try:
                content = lbl.read_text(encoding="utf-8")
            except OSError:
                continue
            lines = [l.strip() for l in content.splitlines() if l.strip()]
            if not lines:
                continue

            # 1. 完全重复: Counter 统计
            counter = Counter(lines)
            for line_text, count in counter.items():
                total_lines += count
                if count > 1:
                    exact_dup_count += count - 1
                    if len(exact_examples) < PREVIEW_LIMIT:
                        exact_examples.append({
                            "split":         split,
                            "label":         str(lbl),
                            "line":          line_text,
                            "repetitions":   count,
                        })

            # 2. 近重复 (仅 detect): 按图+类分组, IoU 两两比较
            if snap.task_type == Task.DETECT:
                by_class: Dict[int, List[Tuple[int, Tuple[float, ...], str]]] = defaultdict(list)
                for idx, line_text in enumerate(lines):
                    parts = line_text.split()
                    if len(parts) != 5:
                        continue
                    try:
                        cls_id = int(parts[0])
                        coords = tuple(float(x) for x in parts[1:5])
                    except ValueError:
                        continue
                    by_class[cls_id].append((idx, coords, line_text))

                for cls_id, items in by_class.items():
                    for i in range(len(items)):
                        for j in range(i + 1, len(items)):
                            idx_i, coords_i, text_i = items[i]
                            idx_j, coords_j, text_j = items[j]
                            # 完全重复行已被计数, 跳过
                            if text_i == text_j:
                                continue
                            iou = _iou_xywh(coords_i, coords_j)
                            if iou >= DUPLICATE_BOX_IOU_THRESHOLD:
                                near_dup_count += 1
                                if len(near_examples) < PREVIEW_LIMIT:
                                    near_examples.append({
                                        "split":    split,
                                        "label":    str(lbl),
                                        "line_a":   idx_i + 1,
                                        "line_b":   idx_j + 1,
                                        "class_id": cls_id,
                                        "iou":      round(iou, 4),
                                    })

    total_dup = exact_dup_count + near_dup_count
    if total_dup == 0:
        return CheckResult(
            name="duplicate_annotations",
            severity=CheckSeverity.PASS,
            summary=f"无重复标注 (完全重复={exact_dup_count}, 近重复={near_dup_count})",
            details={"total_lines": total_lines},
        )

    return CheckResult(
        name="duplicate_annotations",
        severity=CheckSeverity.WARNING,
        summary=f"发现 {total_dup} 处重复标注 (完全重复 {exact_dup_count}, 近重复 {near_dup_count})",
        details={
            "total_lines":        total_lines,
            "exact_dup_count":    exact_dup_count,
            "near_dup_count":     near_dup_count,
            "exact_dup_preview":  exact_examples,
            "near_dup_preview":   near_examples,
            "thresholds": {
                "iou_threshold": DUPLICATE_BOX_IOU_THRESHOLD,
            },
        },
    )
