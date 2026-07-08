"""data_validation 子系统 —— YOLO 数据集质量验证。

提供 14 项检查 + 报告生成 + 画像 + 指纹，
通过 odp-validate CLI 以 0/1/2/3 退出码接入 CI 质量闸门。
"""
from od_platform.data_validation.registry import (
    CheckResult as CheckResult,
    CheckSeverity as CheckSeverity,
    CheckContext as CheckContext,
    ValidationOptions as ValidationOptions,
    check as check,
    get_all_checks as get_all_checks,
    list_check_names as list_check_names,
)
from od_platform.data_validation.report import (
    ValidationReport as ValidationReport,
)
from od_platform.data_validation.service import (
    validate_dataset as validate_dataset,
)

__all__ = [
    "CheckResult", "CheckSeverity", "CheckContext", "ValidationOptions",
    "check", "get_all_checks", "list_check_names",
    "ValidationReport",
    "validate_dataset",
]
