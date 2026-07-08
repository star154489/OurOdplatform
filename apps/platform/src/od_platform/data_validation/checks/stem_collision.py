"""stem_collision check — 检测同一 stem 多扩展名冲突。

事故形态: 同一目录里 a.jpg 和 a.png 共存 → 映射到同一个 a.txt。
判定规则: 任何冲突 → WARNING + 交人工裁决。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from od_platform.data_validation.registry import (
    check, CheckContext, CheckResult, CheckSeverity,
)


@check("stem_collision")
def validate_stem_collision(ctx: CheckContext) -> CheckResult:
    snap = ctx.snapshot

    collisions: List[Dict[str, Any]] = []
    total_collisions = 0

    for split, images in snap.images_per_split.items():
        by_stem: Dict[str, List[str]] = defaultdict(list)
        for img in images:
            by_stem[img.stem].append(img.name)
        collided = [
            {"stem": s, "files": sorted(n)}
            for s, n in by_stem.items() if len(n) > 1
        ]
        if collided:
            collisions.append({
                "split":      split,
                "collisions": collided,
            })
            total_collisions += sum(len(c["files"]) - 1 for c in collided)

    if total_collisions == 0:
        return CheckResult(
            name="stem_collision",
            severity=CheckSeverity.PASS,
            summary="无 stem 冲突",
            details={},
        )

    return CheckResult(
        name="stem_collision",
        severity=CheckSeverity.WARNING,
        summary=f"发现 {total_collisions} 处 stem 冲突 (同名异扩展名) — 需人工裁决保留哪张",
        details={
            "total_collisions": total_collisions,
            "per_split":        collisions,
        },
    )
