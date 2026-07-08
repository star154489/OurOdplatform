#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : pair_existence.py
# @Function  : 图像-标签成对检查 — 消费 snapshot.images_per_split / labels_per_split
"""验证每张图都有对应的 .txt 标签文件。按比例分级 severity, 零额外 IO。"""
from __future__ import annotations

from typing import Any, Dict, List

from od_platform.common.constants import (
    PAIR_MISSING_ERROR_RATIO,
    PAIR_MISSING_WARN_RATIO,
)
from od_platform.data_validation.registry import (
    check, CheckContext, CheckResult, CheckSeverity,
)

DETAILS_PREVIEW_LIMIT = 20


@check("pair_existence")
def validate_pair_existence(ctx: CheckContext) -> CheckResult:
    snap = ctx.snapshot

    if not snap.images_per_split:
        return CheckResult(
            name="pair_existence",
            severity=CheckSeverity.INFO,
            summary="无任何 split 可检查 (snapshot 为空)",
            details={"reason": "empty_snapshot"},
        )

    orphan_per_split: Dict[str, List[str]] = {}
    total_images = 0
    total_missing = 0

    for split, images in snap.images_per_split.items():
        labels = snap.labels_per_split.get(split, ())
        missing_in_split: List[str] = []
        for img, lbl in zip(images, labels):
            total_images += 1
            if not lbl.exists():
                total_missing += 1
                missing_in_split.append(str(img))
        if missing_in_split:
            orphan_per_split[split] = missing_in_split

    missing_ratio = total_missing / max(total_images, 1)

    if total_missing == 0:
        severity = CheckSeverity.PASS
        summary = f"全部 {total_images} 张图像都有对应标签"
    elif missing_ratio >= PAIR_MISSING_ERROR_RATIO:
        severity = CheckSeverity.ERROR
        summary = (
            f"缺标签比例 {missing_ratio:.1%} >= {PAIR_MISSING_ERROR_RATIO:.0%} "
            f"({total_missing}/{total_images} 张图无标签)"
        )
    elif missing_ratio >= PAIR_MISSING_WARN_RATIO:
        severity = CheckSeverity.WARNING
        summary = (
            f"缺标签比例 {missing_ratio:.1%} >= {PAIR_MISSING_WARN_RATIO:.0%} "
            f"({total_missing}/{total_images} 张图无标签)"
        )
    else:
        severity = CheckSeverity.INFO
        summary = f"少量标签缺失 ({total_missing}/{total_images} = {missing_ratio:.2%})"

    details: Dict[str, Any] = {
        "total_images": total_images, "total_missing": total_missing,
        "missing_ratio": round(missing_ratio, 4),
        "thresholds": {"error_at": PAIR_MISSING_ERROR_RATIO, "warn_at": PAIR_MISSING_WARN_RATIO},
        "missing_per_split": {s: len(o) for s, o in orphan_per_split.items()},
    }
    if orphan_per_split:
        details["missing_examples"] = {
            s: o[:DETAILS_PREVIEW_LIMIT] for s, o in orphan_per_split.items()
        }

    return CheckResult(name="pair_existence", severity=severity, summary=summary, details=details)
