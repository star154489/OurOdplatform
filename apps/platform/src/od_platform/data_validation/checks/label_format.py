#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : label_format.py
# @Function  : 标签行格式校验 — 消费 snapshot.labels_per_split
"""逐行验证 YOLO 标注格式 — 零额外 IO, 直接从 snapshot 读标签文件。"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

from od_platform.common.constants import Task
from od_platform.data_validation.registry import (
    check, CheckContext, CheckResult, CheckSeverity,
)

PREVIEW_LIMIT = 20

KIND_FIELD_COUNT = "field_count_mismatch"
KIND_PARSE_ERROR  = "parse_error"
KIND_CLASS_ID_OOR = "class_id_out_of_range"
KIND_COORD_OOR    = "coord_out_of_range"


def _validate_one_line(parts: List[str], task_type: str, nc: int, skip_class: bool = False):
    """返回 (kind, detail) 或 None(合法)。纯函数 — 单测在这层打。"""
    if task_type == Task.DETECT:
        if len(parts) != 5:
            return KIND_FIELD_COUNT, f"detect 要求 5 字段, 实际 {len(parts)}"
        try:
            cls_id = int(parts[0])
            coords = [float(x) for x in parts[1:5]]
        except ValueError as e:
            return KIND_PARSE_ERROR, f"字段类型错: {e}"
        if not skip_class and not (0 <= cls_id < nc):
            return KIND_CLASS_ID_OOR, f"cls_id={cls_id} 不在 [0,{nc}) 内"
        bad = [c for c in coords if not (0.0 <= c <= 1.0)]
        if bad:
            return KIND_COORD_OOR, f"坐标越界 [0,1]: {bad}"
        return None
    # segment: 1+2N 字段 — 留扩展
    return None


@check("label_format")
def validate_label_format(ctx: CheckContext) -> CheckResult:
    snap = ctx.snapshot
    nc = snap.nc or 0
    skip_class_check = snap.nc is None  # nc 未知时跳过 class_id 校验,不误报

    errors: List[Dict[str, Any]] = []
    error_kinds: Counter = Counter()
    total_files = 0
    total_lines = 0

    for split, labels in snap.labels_per_split.items():
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
                total_lines += 1
                issue = _validate_one_line(line.split(), snap.task_type, nc, skip_class_check)
                if issue is not None:
                    kind, detail = issue
                    error_kinds[kind] += 1
                    if len(errors) < PREVIEW_LIMIT:
                        errors.append({
                            "split": split, "label": str(lbl), "line_no": line_no,
                            "kind": kind, "detail": detail,
                        })

    if not error_kinds:
        return CheckResult(
            name="label_format",
            severity=CheckSeverity.PASS,
            summary=f"标注格式正常 ({total_files} 文件, {total_lines} 行)",
            details={"total_files": total_files, "total_lines": total_lines},
        )

    total_issues = sum(error_kinds.values())
    return CheckResult(
        name="label_format",
        severity=CheckSeverity.ERROR,
        summary=f"标注格式问题: {total_issues} 处 — {'; '.join(f'{n} {k}' for k, n in error_kinds.items())}",
        details={
            "total_files": total_files, "total_lines": total_lines,
            "total_issues": total_issues, "error_kinds": dict(error_kinds),
            "errors_preview": errors,
        },
    )
