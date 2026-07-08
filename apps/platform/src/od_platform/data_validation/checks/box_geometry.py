"""box_geometry check — 检测"坐标合法但几何退化/形态异常"的框。

检测项:
    1. 退化框: w≈0 / h≈0 / 面积≈0
    2. 极端宽高比: w/h 或 h/w > STATS_MAX_ASPECT_RATIO

只对 detect task 检查。有问题框 → WARNING。
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from od_platform.common.constants import (
    DEGENERATE_BOX_MIN_SIZE,
    STATS_MAX_ASPECT_RATIO,
    Task,
)
from od_platform.data_validation.registry import (
    check, CheckContext, CheckResult, CheckSeverity,
)

PREVIEW_LIMIT = 20

KIND_ZERO_WIDTH   = "zero_width"
KIND_ZERO_HEIGHT  = "zero_height"
KIND_TINY_AREA    = "tiny_area"
KIND_EXTREME_AR   = "extreme_aspect_ratio"


def _geometry_issue(coords: List[float]) -> Optional[Tuple[str, str]]:
    """coords = [cx, cy, w, h]。返回 (kind, detail) 或 None。"""
    _cx, _cy, w, h = coords
    if w < DEGENERATE_BOX_MIN_SIZE:
        return KIND_ZERO_WIDTH, f"w={w:.6f}"
    if h < DEGENERATE_BOX_MIN_SIZE:
        return KIND_ZERO_HEIGHT, f"h={h:.6f}"
    if w * h < DEGENERATE_BOX_MIN_SIZE ** 2:
        return KIND_TINY_AREA, f"area={w * h:.8f}"
    ar = w / h
    if ar > STATS_MAX_ASPECT_RATIO or ar < 1.0 / STATS_MAX_ASPECT_RATIO:
        return KIND_EXTREME_AR, f"w/h={ar:.3f} (阈值 {STATS_MAX_ASPECT_RATIO:g}x)"
    return None


@check("box_geometry")
def validate_box_geometry(ctx: CheckContext) -> CheckResult:
    snap = ctx.snapshot

    if snap.task_type != Task.DETECT:
        return CheckResult(
            name="box_geometry",
            severity=CheckSeverity.PASS,
            summary=f"task={snap.task_type}, 退化几何检查暂仅支持 detect (留扩展)",
            details={"reason": "task_not_applicable", "task_type": snap.task_type},
        )

    issues: List[Dict[str, Any]] = []
    issue_kinds: Counter = Counter()
    total_boxes = 0

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
                issue = _geometry_issue(coords)
                if issue is not None:
                    kind, detail = issue
                    issue_kinds[kind] += 1
                    if len(issues) < PREVIEW_LIMIT:
                        issues.append({
                            "split":   split,
                            "label":   str(lbl),
                            "line_no": line_no,
                            "kind":    kind,
                            "detail":  detail,
                        })

    if not issue_kinds:
        return CheckResult(
            name="box_geometry",
            severity=CheckSeverity.PASS,
            summary=f"全部 {total_boxes} 个框几何正常 (无退化框/极端宽高比)",
            details={"total_boxes": total_boxes},
        )

    total_issues = sum(issue_kinds.values())
    return CheckResult(
        name="box_geometry",
        severity=CheckSeverity.WARNING,
        summary=(
            f"{total_issues}/{total_boxes} 个框几何异常 "
            f"(退化框/极端宽高比) — 训练前建议清理"
        ),
        details={
            "total_boxes":    total_boxes,
            "total_issues":   total_issues,
            "issue_kinds":    dict(issue_kinds),
            "issues_preview": issues,
            "thresholds": {
                "degenerate_min_size": DEGENERATE_BOX_MIN_SIZE,
                "max_aspect_ratio":    STATS_MAX_ASPECT_RATIO,
            },
        },
    )
