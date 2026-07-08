#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : coverage.py
# @Function  : 覆盖率检查 — 消费 snapshot.stats_per_split (零 IO, 顺手统计红利)
"""检查图像-标注配对覆盖率 — snapshot"顺手统计"红利的兑现处。"""
from __future__ import annotations

from od_platform.data_validation.registry import (
    check, CheckContext, CheckResult, CheckSeverity,
)


@check("coverage")
def check_coverage(ctx: CheckContext) -> CheckResult:
    snap = ctx.snapshot
    problems = []
    details = {}

    for split_name in ("train", "val", "test"):
        scan = snap.images_per_split.get(split_name)
        if not scan:
            continue
        stat = snap.stats_per_split.get(split_name)
        if stat is None:
            continue

        n_img = stat.image_count
        n_paired = stat.annotated_count
        n_lbl = len(snap.labels_per_split.get(split_name, ()))

        coverage_pct = (n_paired / n_img * 100) if n_img else 100.0
        details[split_name] = {
            "images": n_img, "labels": n_lbl, "paired": n_paired,
            "coverage_pct": round(coverage_pct, 1),
        }

        if n_lbl < n_img:
            missing = n_img - n_lbl
            problems.append(f"{split_name}: {missing} 张图缺标注 (覆盖率 {coverage_pct:.1f}%)")

    if problems:
        has_low_coverage = any(d.get("coverage_pct", 100) < 90 for d in details.values())
        return CheckResult(
            name="coverage",
            severity=CheckSeverity.ERROR if has_low_coverage else CheckSeverity.WARNING,
            summary=f"覆盖率问题: {'; '.join(problems)}",
            details=details,
        )

    return CheckResult(
        name="coverage",
        severity=CheckSeverity.PASS,
        summary="所有子集图像-标注覆盖率正常",
        details=details,
    )
