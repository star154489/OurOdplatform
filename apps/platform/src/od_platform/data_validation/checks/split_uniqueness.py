"""split_uniqueness check — 检测跨划分 stem 重复 (数据泄露)。

事故形态: 同一 stem 的图像出现在两个划分 (视频抽帧/增强副本/手工拷贝)。
判定规则: 任何跨划分 stem 重复 → 硬性 ERROR, 不按比例分级。
"""
from __future__ import annotations

from typing import Any, Dict, List

from od_platform.data_validation.registry import (
    check, CheckContext, CheckResult, CheckSeverity,
)

DETAILS_PREVIEW_LIMIT = 20


@check("split_uniqueness")
def validate_split_uniqueness(ctx: CheckContext) -> CheckResult:
    snap = ctx.snapshot
    stems = {s: {p.stem for p in imgs} for s, imgs in snap.images_per_split.items()}

    overlaps: List[Dict[str, Any]] = []
    splits = list(stems)
    for i in range(len(splits)):
        for j in range(i + 1, len(splits)):
            common = stems[splits[i]] & stems[splits[j]]
            if common:
                overlaps.append({
                    "split_a": splits[i],
                    "split_b": splits[j],
                    "count":   len(common),
                    "preview": sorted(common)[:DETAILS_PREVIEW_LIMIT],
                })

    if not overlaps:
        return CheckResult(
            name="split_uniqueness",
            severity=CheckSeverity.PASS,
            summary="无跨划分 stem 重复",
            details={"total_stems": {s: len(st) for s, st in stems.items()}},
        )

    total_overlap = sum(o["count"] for o in overlaps)
    return CheckResult(
        name="split_uniqueness",
        severity=CheckSeverity.ERROR,
        summary=f"发现 {total_overlap} 个跨划分重复 stem — 数据泄露, 必须修复",
        details={
            "overlaps":      overlaps,
            "total_overlap": total_overlap,
        },
    )
