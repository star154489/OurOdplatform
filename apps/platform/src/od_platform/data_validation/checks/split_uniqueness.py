#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : split_uniqueness.py
# @Function  : 跨划分泄露检查 — 消费 snapshot.images_per_split
"""检查 train/val/test 之间是否有图像泄漏 — 硬性 ERROR, 零额外 IO。"""
from __future__ import annotations

from od_platform.data_validation.registry import (
    check, CheckContext, CheckResult, CheckSeverity,
)

DETAILS_PREVIEW_LIMIT = 20


@check("split_uniqueness")
def validate_split_uniqueness(ctx: CheckContext) -> CheckResult:
    snap = ctx.snapshot
    stems = {s: {p.stem for p in imgs} for s, imgs in snap.images_per_split.items()}

    overlaps = []
    splits = sorted(stems)
    for i in range(len(splits)):
        for j in range(i + 1, len(splits)):
            common = stems[splits[i]] & stems[splits[j]]
            if common:
                overlaps.append({
                    "split_a": splits[i], "split_b": splits[j],
                    "count": len(common),
                    "preview": sorted(common)[:DETAILS_PREVIEW_LIMIT],
                })

    if not overlaps:
        sizes = {k: len(v) for k, v in stems.items() if v}
        return CheckResult(
            name="split_uniqueness",
            severity=CheckSeverity.PASS,
            summary=f"子集无交叉泄漏 ({', '.join(f'{k}={v}' for k, v in sizes.items())})",
            details={"split_sizes": sizes},
        )

    summary_parts = [f"{o['split_a']} ∩ {o['split_b']} = {o['count']} 张" for o in overlaps]
    return CheckResult(
        name="split_uniqueness",
        severity=CheckSeverity.ERROR,
        summary=f"子集交叉泄漏: {'; '.join(summary_parts)}",
        details={"overlaps": overlaps},
    )
