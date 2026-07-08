"""split_presence check — 验证 yaml 声明的 split 是否可用、有无数据。

兑付阶段 4 scan_warnings 的欠条。
判定规则 (取最严):
    - train 缺失 → ERROR (无训练数据)
    - 任何 scan_warning → WARNING
    - val 未声明 → WARNING (训练盲飞)
    - test 未声明 → INFO
"""
from __future__ import annotations

from typing import Any, Dict, List

from od_platform.data_validation.registry import (
    check, CheckContext, CheckResult, CheckSeverity,
)

SPLIT_MIN_IMAGES = 30


@check("split_presence")
def validate_split_presence(ctx: CheckContext) -> CheckResult:
    snap = ctx.snapshot
    findings: List[Dict[str, str]] = []

    present_splits = set(snap.splits)
    declared_splits = [s for s in ("train", "val", "test") if s in snap.yaml_data]

    # ---- 兑付 scan_warnings ----
    for w in snap.scan_warnings:
        if "split" in w.lower():
            findings.append({"severity": CheckSeverity.WARNING, "message": w})

    # ---- train 缺失 ----
    if "train" not in present_splits:
        findings.append({
            "severity": CheckSeverity.ERROR,
            "message": "train 划分不可用 — 无训练数据, 流程必须终止",
        })

    # ---- val 未声明 ----
    if "val" not in declared_splits:
        findings.append({
            "severity": CheckSeverity.WARNING,
            "message": "val 划分未在 yaml 中声明 — 训练将无验证集 (盲飞)",
        })

    # ---- test 未声明 ----
    if "test" not in declared_splits:
        findings.append({
            "severity": CheckSeverity.INFO,
            "message": "test 划分未在 yaml 中声明 — 验收时将无独立测试集",
        })

    # ---- 极小划分提示 ----
    for split in present_splits:
        n = len(snap.images_per_split.get(split, ()))
        if n < SPLIT_MIN_IMAGES:
            findings.append({
                "severity": CheckSeverity.INFO,
                "message": f"split '{split}' 仅有 {n} 张图像 (< {SPLIT_MIN_IMAGES}), 统计意义有限",
            })

    if not findings:
        return CheckResult(
            name="split_presence",
            severity=CheckSeverity.PASS,
            summary=f"所有声明划分可用 (train/val/test)",
            details={"present_splits": list(present_splits)},
        )

    # 取最严重级别
    severity = max((f["severity"] for f in findings), key=CheckSeverity.rank)
    return CheckResult(
        name="split_presence",
        severity=severity,
        summary=f"划分存在性: {len(findings)} 项发现",
        details={
            "findings":       findings,
            "present_splits": list(present_splits),
            "declared_splits": declared_splits,
        },
    )
