"""class_balance check — 检测各划分内类别实例数失衡情况。

判定规则:
    - 失衡比 = max(实例数) / min(非零类实例数)
    - >= IMBALANCE_ERROR_RATIO (50x) → WARNING
    - >= IMBALANCE_WARN_RATIO (20x)  → INFO
    零实例类不进比值 (归 class_presence 的案子)。
"""
from __future__ import annotations

from typing import Any, Dict, List

from od_platform.common.constants import IMBALANCE_ERROR_RATIO, IMBALANCE_WARN_RATIO
from od_platform.data_validation.registry import (
    check, CheckContext, CheckResult, CheckSeverity,
)


@check("class_balance")
def validate_class_balance(ctx: CheckContext) -> CheckResult:
    snap = ctx.snapshot

    per_split: List[Dict[str, Any]] = []
    overall_max_ratio = 0.0

    for split in snap.splits:
        st = snap.stats_per_split.get(split)
        if st is None:
            continue
        nonzero = {c: n for c, n in st.class_instances.items() if n > 0}
        if len(nonzero) < 2:
            continue
        max_cls = max(nonzero, key=nonzero.get)
        min_cls = min(nonzero, key=nonzero.get)
        ratio = nonzero[max_cls] / nonzero[min_cls]
        overall_max_ratio = max(overall_max_ratio, ratio)

        max_name = snap.class_names[max_cls] if max_cls < len(snap.class_names) else f"id_{max_cls}"
        min_name = snap.class_names[min_cls] if min_cls < len(snap.class_names) else f"id_{min_cls}"
        per_split.append({
            "split":       split,
            "ratio":       round(ratio, 2),
            "max_class":   {"id": max_cls, "name": max_name, "count": nonzero[max_cls]},
            "min_class":   {"id": min_cls, "name": min_name, "count": nonzero[min_cls]},
            "zero_classes": [c for c, n in st.class_instances.items() if n == 0],
        })

    if overall_max_ratio == 0.0:
        return CheckResult(
            name="class_balance",
            severity=CheckSeverity.PASS,
            summary="失衡比无可计算 (不足 2 个非零类)",
            details={},
        )

    if overall_max_ratio >= IMBALANCE_ERROR_RATIO:
        severity = CheckSeverity.WARNING
        summary  = f"最大失衡比 {overall_max_ratio:.1f}x (>= {IMBALANCE_ERROR_RATIO}x) — 显著失衡, 建议重采样/class_weights"
    elif overall_max_ratio >= IMBALANCE_WARN_RATIO:
        severity = CheckSeverity.INFO
        summary  = f"最大失衡比 {overall_max_ratio:.1f}x (>= {IMBALANCE_WARN_RATIO}x) — 长尾提醒, 训练时建议关注 class_weights / 重采样"
    else:
        severity = CheckSeverity.PASS
        summary  = f"类别失衡在可接受范围 (最大失衡比 {overall_max_ratio:.1f}x)"

    return CheckResult(
        name="class_balance",
        severity=severity,
        summary=summary,
        details={
            "max_ratio": round(overall_max_ratio, 2),
            "per_split": per_split,
            "thresholds": {
                "error_at": IMBALANCE_ERROR_RATIO,
                "warn_at":  IMBALANCE_WARN_RATIO,
            },
        },
    )
