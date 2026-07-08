"""annotation_coverage check — 成品端"无有效标注图"占比。

零额外 I/O: 直接消费 snapshot.stats_per_split 里已经算好的
image_count / annotated_count — 这是 snapshot"顺手统计"红利的兑现处。

Severity 分级:
    ratio >= UNLABELED_WARN_RATIO (30%) → WARNING
    ratio >= UNLABELED_INFO_RATIO (5%)  → INFO
    其余                                 → PASS
"""
from __future__ import annotations

from typing import Any, Dict

from od_platform.common.constants import UNLABELED_INFO_RATIO, UNLABELED_WARN_RATIO
from od_platform.data_validation.registry import (
    check, CheckContext, CheckResult, CheckSeverity,
)


@check("annotation_coverage")
def validate_annotation_coverage(ctx: CheckContext) -> CheckResult:
    snap = ctx.snapshot

    total_images    = 0
    total_unlabeled = 0
    per_split: Dict[str, Dict[str, int]] = {}

    for split, st in snap.stats_per_split.items():
        unlabeled = st.image_count - st.annotated_count
        per_split[split] = {"images": st.image_count, "unlabeled": unlabeled}
        total_images    += st.image_count
        total_unlabeled += unlabeled

    if total_images == 0:
        return CheckResult(
            name="annotation_coverage",
            severity=CheckSeverity.INFO,
            summary="无图像可统计",
            details={"reason": "no_images"},
        )

    ratio = total_unlabeled / total_images
    details: Dict[str, Any] = {
        "total_images":    total_images,
        "total_unlabeled": total_unlabeled,
        "unlabeled_ratio": round(ratio, 4),
        "per_split":       per_split,
        "thresholds": {
            "warn_at": UNLABELED_WARN_RATIO,
            "info_at": UNLABELED_INFO_RATIO,
        },
    }

    if ratio >= UNLABELED_WARN_RATIO:
        severity = CheckSeverity.WARNING
        summary  = (
            f"无有效标注图占比 {ratio:.1%} >= {UNLABELED_WARN_RATIO:.0%} "
            f"({total_unlabeled}/{total_images}) — 建议 review 数据来源"
        )
    elif ratio >= UNLABELED_INFO_RATIO:
        severity = CheckSeverity.INFO
        summary  = (
            f"无有效标注图占比 {ratio:.1%} "
            f"({total_unlabeled}/{total_images}) — 若为有意保留的背景图可忽略"
        )
    else:
        severity = CheckSeverity.PASS
        summary  = f"标注覆盖正常 (无标注图 {total_unlabeled}/{total_images} = {ratio:.2%})"

    return CheckResult(
        name="annotation_coverage",
        severity=severity,
        summary=summary,
        details=details,
    )
