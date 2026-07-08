#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : yaml_schema.py
# @Function  : yaml_schema check —— 通过预扫描的 ctx.yaml_data 验证字段一致性
"""验证 dataset.yaml 的字段完整性和一致性(只读预扫描数据,不重复 open/parse)。"""
from __future__ import annotations

from typing import Any, List, Tuple

from od_platform.validate_dateset.registry import (
    CheckContext, CheckResult, CheckSeverity, check,
)


@check("yaml_schema")
def validate_yaml_schema(ctx: CheckContext) -> CheckResult:
    # 优先用 scanner 预解析的数据; 没有则降级自己 open
    yaml_data = ctx.yaml_data
    if yaml_data is None:
        if not ctx.yaml_path.exists():
            return CheckResult(
                name="yaml_schema",
                severity=CheckSeverity.ERROR,
                summary=f"yaml 文件不存在: {ctx.yaml_path}",
                details={"reason": "file_not_found"},
            )
        import yaml
        try:
            with open(ctx.yaml_path, "r", encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f)
        except Exception as e:
            return CheckResult(
                name="yaml_schema",
                severity=CheckSeverity.ERROR,
                summary=f"yaml 解析失败: {e}",
                details={"reason": "parse_error"},
            )

    if yaml_data is None:
        return CheckResult(
            name="yaml_schema",
            severity=CheckSeverity.ERROR,
            summary="yaml 解析结果为空",
            details={"reason": "empty_yaml"},
        )

    if not isinstance(yaml_data, dict):
        return CheckResult(
            name="yaml_schema",
            severity=CheckSeverity.ERROR,
            summary=f"yaml 顶层不是字典: {type(yaml_data).__name__}",
            details={"reason": "not_dict"},
        )

    # nc / names 校验
    problems: List[str] = []

    nc = yaml_data.get("nc")
    if not isinstance(nc, int) or nc <= 0:
        problems.append(f"nc 字段不存在或不是正整数: {nc}")
        nc = None

    names_raw = yaml_data.get("names")
    names_count, names_problem = _validate_names(names_raw)
    if names_problem:
        problems.append(names_problem)

    if nc is not None and names_count is not None and nc != names_count:
        problems.append(f"nc ({nc}) 与 names 元素个数 ({names_count}) 不一致")

    if problems:
        return CheckResult(
            name="yaml_schema",
            severity=CheckSeverity.ERROR,
            summary=f"yaml 字段不一致: {len(problems)} 处问题",
            details={"reason": "field_inconsistency", "problems": problems,
                     "nc": nc, "names_count": names_count},
        )

    return CheckResult(
        name="yaml_schema",
        severity=CheckSeverity.INFO,
        summary=f"yaml schema 通过 (nc={nc}, names_count={names_count})",
        details={"nc": nc, "names_count": names_count},
    )


def _validate_names(names_raw: Any) -> Tuple[int | None, str]:
    """校验 names 字段,返回 (元素个数, 错误信息)。"""
    if isinstance(names_raw, list):
        if not names_raw:
            return None, "names 是空列表"
        if not all(isinstance(n, str) and n for n in names_raw):
            return None, "names 列表中包含非字符串元素"
        return len(names_raw), ""

    if isinstance(names_raw, dict):
        if not names_raw:
            return None, "names 是空字典"
        if not all(isinstance(k, int) for k in names_raw.keys()):
            return None, "names 字典的键必须是 int 类型"
        if not all(isinstance(v, str) and v for v in names_raw.values()):
            return None, "names 字典的值必须是非空字符串"
        return len(names_raw), ""

    return None, f"names 不是合法的 list 或 dict: {type(names_raw).__name__}"
