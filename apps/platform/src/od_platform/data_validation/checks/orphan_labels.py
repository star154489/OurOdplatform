"""orphan_labels check — 检测"有标签文件但无对应图像"的孤儿标签。

镜像检查: pair_existence 查"有图无标签"方向, orphan_labels 查"有标签无图"方向。
判定规则: 占比 >=10% → WARNING; 有但 <10% → INFO; 无 → PASS。
"""
from __future__ import annotations

from typing import Any, Dict, List

from od_platform.data_validation.registry import (
    check, CheckContext, CheckResult, CheckSeverity,
)

DETAILS_PREVIEW_LIMIT = 20


@check("orphan_labels")
def validate_orphan_labels(ctx: CheckContext) -> CheckResult:
    snap = ctx.snapshot

    total_orphans = 0
    total_labels  = 0
    per_split: Dict[str, List[str]] = {}

    for split, label_files in snap.label_files_per_split.items():
        image_stems = {img.stem for img in snap.images_per_split.get(split, ())}
        orphans = [str(lbl) for lbl in label_files if lbl.stem not in image_stems]
        total_labels += len(label_files)
        if orphans:
            per_split[split] = orphans[:DETAILS_PREVIEW_LIMIT]
            total_orphans += len(orphans)

    if total_labels == 0:
        return CheckResult(
            name="orphan_labels",
            severity=CheckSeverity.INFO,
            summary="无标签文件可检查",
            details={"reason": "no_labels"},
        )

    orphan_ratio = total_orphans / max(total_labels, 1)

    if total_orphans == 0:
        severity = CheckSeverity.PASS
        summary  = f"全部 {total_labels} 个标签文件都有对应图像"
    elif orphan_ratio >= 0.10:
        severity = CheckSeverity.WARNING
        summary  = (
            f"{total_orphans}/{total_labels} ({orphan_ratio:.1%}) 个标签文件没有对应图像 "
            f"— 成片残留, 排查数据同步脚本"
        )
    else:
        severity = CheckSeverity.INFO
        summary  = (
            f"{total_orphans}/{total_labels} ({orphan_ratio:.2%}) 个标签文件没有对应图像 "
            f"— 数据管理残留, 建议清理"
        )

    return CheckResult(
        name="orphan_labels",
        severity=severity,
        summary=summary,
        details={
            "total_labels":  total_labels,
            "total_orphans": total_orphans,
            "orphan_ratio":  round(orphan_ratio, 4),
            "per_split":     per_split,
        },
    )
