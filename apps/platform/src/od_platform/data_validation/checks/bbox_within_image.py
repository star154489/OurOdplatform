"""bbox_within_image check — 检测"四个坐标各自合法、但框体伸出图像"的框。

盲区成因: label_format 验证 cx/cy/w/h 各自 ∈ [0,1], 但框边缘是组合量。
Severity 分级:
    无出图框                          → PASS
    出图框占比 <  BBOX_OUT_ERROR_RATIO → WARNING
    出图框占比 >= BBOX_OUT_ERROR_RATIO → ERROR
segment 任务直接 PASS (顶点坐标已由 label_format 覆盖)。
"""
from __future__ import annotations

from typing import Any, Dict, List

from od_platform.common.constants import (
    BBOX_EDGE_TOLERANCE,
    BBOX_OUT_ERROR_RATIO,
    Task,
)
from od_platform.data_validation.registry import (
    check, CheckContext, CheckResult, CheckSeverity,
)

PREVIEW_LIMIT = 20


def _overflow_amount(coords: List[float]) -> float:
    """coords = [cx, cy, w, h]。返回框边缘越出 [0,1] 的最大量 (0.0 = 未越界)。"""
    cx, cy, w, h = coords
    left, right  = cx - w / 2.0, cx + w / 2.0
    top, bottom  = cy - h / 2.0, cy + h / 2.0
    overflow = max(
        0.0 - left,
        right - 1.0,
        0.0 - top,
        bottom - 1.0,
    )
    return overflow if overflow > BBOX_EDGE_TOLERANCE else 0.0


@check("bbox_within_image")
def validate_bbox_within_image(ctx: CheckContext) -> CheckResult:
    snap = ctx.snapshot

    if snap.task_type != Task.DETECT:
        return CheckResult(
            name="bbox_within_image",
            severity=CheckSeverity.PASS,
            summary=f"task={snap.task_type}, 顶点坐标已由 label_format 覆盖, 本检查不适用",
            details={"reason": "task_not_applicable", "task_type": snap.task_type},
        )

    out_boxes: List[Dict[str, Any]] = []
    total_boxes = 0
    total_out   = 0
    max_overflow = 0.0

    for split, labels in snap.labels_per_split.items():
        for lbl in labels:
            if not lbl.exists():
                continue
            try:
                content = lbl.read_text(encoding="utf-8")
            except OSError:
                continue
            for line_no, line in enumerate(content.splitlines(), 1):
                parts = line.strip().split()
                if len(parts) != 5:
                    continue
                try:
                    coords = [float(x) for x in parts[1:5]]
                except ValueError:
                    continue
                total_boxes += 1
                overflow = _overflow_amount(coords)
                if overflow > 0.0:
                    total_out += 1
                    max_overflow = max(max_overflow, overflow)
                    if len(out_boxes) < PREVIEW_LIMIT:
                        out_boxes.append({
                            "split":    split,
                            "label":    str(lbl),
                            "line_no":  line_no,
                            "overflow": round(overflow, 6),
                        })

    if total_out == 0:
        return CheckResult(
            name="bbox_within_image",
            severity=CheckSeverity.PASS,
            summary=f"全部 {total_boxes} 个框完整落在图像内",
            details={"total_boxes": total_boxes},
        )

    out_ratio = total_out / max(total_boxes, 1)
    severity = (
        CheckSeverity.ERROR
        if out_ratio >= BBOX_OUT_ERROR_RATIO
        else CheckSeverity.WARNING
    )
    return CheckResult(
        name="bbox_within_image",
        severity=severity,
        summary=(
            f"{total_out}/{total_boxes} ({out_ratio:.1%}) 个框伸出图像边界 "
            f"(最大越界量 {max_overflow:.4f}) — 加载器会静默 clip, 建议修正标注"
        ),
        details={
            "total_boxes":  total_boxes,
            "total_out":    total_out,
            "out_ratio":    round(out_ratio, 4),
            "max_overflow": round(max_overflow, 6),
            "thresholds": {
                "edge_tolerance": BBOX_EDGE_TOLERANCE,
                "error_at_ratio": BBOX_OUT_ERROR_RATIO,
            },
            "out_boxes_preview": out_boxes,
        },
    )
