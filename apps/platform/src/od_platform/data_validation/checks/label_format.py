"""label_format check — 验证标签文件的行格式。

检查项 (任何坏行 → ERROR):
    1. 字段数: detect 要求 5 字段, segment 要求 1+2N、N>=3
    2. 字段类型: class_id 必须是 int, 坐标必须是 float
    3. class_id ∈ [0, nc)
    4. 坐标值 ∈ [0, 1]
    5. segment 多边形的点数 N >= 3 (至少一个三角形)
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from od_platform.common.constants import Task
from od_platform.data_validation.registry import (
    check, CheckContext, CheckResult, CheckSeverity,
)


DETAILS_PREVIEW_LIMIT = 20

KIND_FIELD_COUNT_MISMATCH  = "field_count_mismatch"
KIND_PARSE_ERROR           = "parse_error"
KIND_CLASS_ID_OUT_OF_RANGE = "class_id_out_of_range"
KIND_COORD_OUT_OF_RANGE    = "coord_out_of_range"
KIND_POLYGON_TOO_FEW       = "polygon_too_few_points"


def _validate_one_line(line: str, task_type: str, nc: int) -> Optional[Tuple[str, str]]:
    """纯函数: 校验单行标签。返回 (kind, detail) 或 None (合法)。"""
    parts = line.split()
    if not parts:
        return None

    if task_type == Task.DETECT:
        if len(parts) != 5:
            return KIND_FIELD_COUNT_MISMATCH, f"detect 任务要求 5 字段, 实际 {len(parts)}"
        try:
            cls_id = int(parts[0])
            coords = [float(x) for x in parts[1:5]]
        except ValueError as e:
            return KIND_PARSE_ERROR, f"字段类型错: {e}"
        if not (0 <= cls_id < nc):
            return KIND_CLASS_ID_OUT_OF_RANGE, f"cls_id={cls_id} 不在 [0,{nc}) 内"
        bad = [c for c in coords if not (0.0 <= c <= 1.0)]
        if bad:
            return KIND_COORD_OUT_OF_RANGE, f"坐标越界 [0,1]: {bad}"
        return None

    if task_type == Task.SEGMENT:
        if len(parts) < 7 or (len(parts) - 1) % 2 != 0:
            return KIND_FIELD_COUNT_MISMATCH, f"segment 字段数异常: {len(parts)}"
        try:
            cls_id = int(parts[0])
            coords = [float(x) for x in parts[1:]]
        except ValueError as e:
            return KIND_PARSE_ERROR, f"字段类型错: {e}"
        if not (0 <= cls_id < nc):
            return KIND_CLASS_ID_OUT_OF_RANGE, f"cls_id={cls_id} 不在 [0,{nc}) 内"
        bad = [c for c in coords if not (0.0 <= c <= 1.0)]
        if bad:
            return KIND_COORD_OUT_OF_RANGE, f"坐标越界 [0,1]: {bad}"
        n_points = len(coords) // 2
        if n_points < 3:
            return KIND_POLYGON_TOO_FEW, f"多边形只有 {n_points} 个点, 至少需要 3"
        return None

    return KIND_PARSE_ERROR, f"未知 task_type: {task_type}"


@check("label_format")
def validate_label_format(ctx: CheckContext) -> CheckResult:
    snap = ctx.snapshot
    nc = snap.nc or 0

    errors: List[Dict[str, Any]] = []
    error_kinds: Counter = Counter()
    total_lines = 0
    bad_lines   = 0

    for split, labels in snap.labels_per_split.items():
        for lbl in labels:
            if not lbl.exists():
                continue
            try:
                content = lbl.read_text(encoding="utf-8")
            except OSError:
                continue
            for line_no, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if not stripped:
                    continue
                total_lines += 1
                result = _validate_one_line(stripped, snap.task_type, nc)
                if result is not None:
                    kind, detail = result
                    bad_lines += 1
                    error_kinds[kind] += 1
                    if len(errors) < DETAILS_PREVIEW_LIMIT:
                        errors.append({
                            "split":   split,
                            "label":   str(lbl),
                            "line_no": line_no,
                            "kind":    kind,
                            "detail":  detail,
                        })

    if bad_lines == 0:
        return CheckResult(
            name="label_format",
            severity=CheckSeverity.PASS,
            summary=f"全部 {total_lines} 行标签格式合规 ({snap.task_type})",
            details={"total_lines": total_lines, "task_type": snap.task_type},
        )

    return CheckResult(
        name="label_format",
        severity=CheckSeverity.ERROR,
        summary=f"{bad_lines}/{total_lines} 行标签格式错误 — 结构性问题, 必须修复",
        details={
            "total_lines":    total_lines,
            "bad_lines":      bad_lines,
            "error_kinds":    dict(error_kinds),
            "errors_preview": errors,
            "task_type":      snap.task_type,
            "nc":             nc,
        },
    )
