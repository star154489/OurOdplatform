"""class_presence check — 检测类别出现性问题。

检查项:
    1. 类别在 val/test 有实例但 train 为 0 → WARNING (模型无法学习)
    2. 类别在 train 有实例但 val 为 0 → WARNING (无法评估)
    3. yaml 声明的类别在全部划分中为 0 → INFO (死类别)
"""
from __future__ import annotations

from typing import Any, Dict, List

from od_platform.data_validation.registry import (
    check, CheckContext, CheckResult, CheckSeverity,
)


def _count_in_split(snap, split: str, cls_id: int) -> int:
    st = snap.stats_per_split.get(split)
    if st is None:
        return 0
    return st.class_instances.get(cls_id, 0)


@check("class_presence")
def validate_class_presence(ctx: CheckContext) -> CheckResult:
    snap = ctx.snapshot
    if not snap.class_names or snap.nc is None:
        return CheckResult(
            name="class_presence",
            severity=CheckSeverity.INFO,
            summary="class_names 不可用, 无法检查类别出现性",
            details={"reason": "class_names_unavailable"},
        )

    findings: List[Dict[str, Any]] = []
    has_train = "train" in snap.splits
    has_val   = "val" in snap.splits

    for cls_id in range(snap.nc):
        name = snap.class_names[cls_id] if cls_id < len(snap.class_names) else f"id_{cls_id}"
        in_train = _count_in_split(snap, "train", cls_id)
        in_val   = _count_in_split(snap, "val", cls_id)
        in_test  = _count_in_split(snap, "test", cls_id)
        total    = in_train + in_val + in_test

        if total == 0:
            findings.append({
                "kind":     "declared_unused",
                "class_id": cls_id,
                "class_name": name,
                "severity": CheckSeverity.INFO,
                "message": f"类别 '{name}' (id={cls_id}) 在 yaml 中声明但全划分 0 实例 — 死类别",
            })
        elif has_train and in_train == 0 and (in_val + in_test) > 0:
            findings.append({
                "kind":     "missing_in_train",
                "class_id": cls_id,
                "class_name": name,
                "severity": CheckSeverity.WARNING,
                "message": (
                    f"类别 '{name}' (id={cls_id}) 在 val/test 出现 {in_val + in_test} 次但 train 为 0 "
                    f"— 模型无法学习, 评估必然失真"
                ),
            })
        elif has_train and has_val and in_train > 0 and in_val == 0:
            findings.append({
                "kind":     "missing_in_val",
                "class_id": cls_id,
                "class_name": name,
                "severity": CheckSeverity.WARNING,
                "message": f"类别 '{name}' (id={cls_id}) train 有 {in_train} 实例但 val 为 0 — 无法评估",
            })

    if not findings:
        return CheckResult(
            name="class_presence",
            severity=CheckSeverity.PASS,
            summary=f"全部 {snap.nc} 个类别在 train 中正常出现",
            details={"nc": snap.nc},
        )

    severity = max((f["severity"] for f in findings), key=CheckSeverity.rank)
    return CheckResult(
        name="class_presence",
        severity=severity,
        summary=f"{len(findings)} 个类别出现性问题",
        details={
            "nc":       snap.nc,
            "findings": findings,
        },
    )
