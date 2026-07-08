#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : yolo_labels.py
# @Function  : YOLO 标注合法性检查 — 消费 snapshot.labels_per_split (零 IO)
"""检查 YOLO 标注的 class_id / 坐标合法性 — 直接读 snapshot 路径, 不重复 glob。"""
from __future__ import annotations

from od_platform.data_validation.registry import (
    check, CheckContext, CheckResult, CheckSeverity,
)


@check("yolo_labels")
def check_yolo_labels(ctx: CheckContext) -> CheckResult:
    snap = ctx.snapshot
    nc = snap.nc or 0
    total_files = 0
    total_boxes = 0
    bad_ids: list[tuple[str, int, int]] = []
    bad_coords: list[tuple[str, str]] = []
    parse_fails: list[tuple[str, str]] = []

    for split_name, labels in snap.labels_per_split.items():
        for lbl in labels:
            if not lbl.exists():
                continue
            total_files += 1
            try:
                content = lbl.read_text(encoding="utf-8")
            except OSError:
                continue
            for line_no, line in enumerate(content.splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) != 5:
                    parse_fails.append((f"{split_name}/{lbl.name}", f"L{line_no}: 字段数={len(parts)}"))
                    continue
                try:
                    cls_id = int(parts[0])
                    vals = [float(x) for x in parts[1:]]
                except ValueError:
                    parse_fails.append((f"{split_name}/{lbl.name}", f"L{line_no}: 解析失败"))
                    continue

                total_boxes += 1
                if nc > 0 and not (0 <= cls_id < nc):
                    bad_ids.append((f"{split_name}/{lbl.name}", cls_id, nc))
                for label, val in [("cx", vals[0]), ("cy", vals[1]), ("w", vals[2]), ("h", vals[3])]:
                    if not (0.0 <= val <= 1.0):
                        bad_coords.append((f"{split_name}/{lbl.name}", f"L{line_no}: {label}={val:.6f}"))
                if vals[2] <= 0 or vals[3] <= 0:
                    bad_coords.append((f"{split_name}/{lbl.name}", f"L{line_no}: w={vals[2]} h={vals[3]}"))

    problems = []
    if parse_fails:
        problems.append(f"{len(parse_fails)} 个文件解析失败")
    if bad_ids:
        problems.append(f"{len(bad_ids)} 处 class_id 越界(nc={nc})")
    if bad_coords:
        problems.append(f"{len(bad_coords)} 处坐标异常")

    if not problems:
        return CheckResult(
            name="yolo_labels",
            severity=CheckSeverity.PASS,
            summary=f"YOLO 标注合法 ({total_files} 文件, {total_boxes} 框)",
            details={"total_files": total_files, "total_boxes": total_boxes},
        )

    return CheckResult(
        name="yolo_labels",
        severity=CheckSeverity.ERROR,
        summary=f"YOLO 标注问题: {'; '.join(problems)}",
        details={
            "total_files": total_files, "total_boxes": total_boxes,
            "parse_fails": parse_fails[:20], "bad_ids": bad_ids[:20], "bad_coords": bad_coords[:20],
        },
    )
