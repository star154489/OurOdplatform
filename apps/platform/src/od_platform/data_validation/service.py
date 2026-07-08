#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : service.py
# @Function  : data_validation 调度层 — run_all_checks 聚合承诺
"""run_all_checks — 聚合模式核心承诺: 任何 check 抛异常都不能阻断其他 check。

D4 跟 D3 最大的区别: D3 service.convert 失败立刻抛, D4 service.run_all_checks 失败也继续。
唯一一处宽泛 except Exception 在此 —— 因为 check 是开闭扩展点, 无法预知新型异常。
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from od_platform.data_validation.registry import (
    CheckContext, CheckEntry, CheckResult, CheckSeverity, ValidationOptions,
    get_all_checks,
)
from od_platform.data_validation.report import ValidationReport
from od_platform.data_validation.snapshot import build_snapshot
from od_platform.common.paths import validation_run_dir
from od_platform.common.performance_utils import time_it
from od_platform._version import version as _tool_version

logger = logging.getLogger(__name__)

_VALIDATE_LOG_SETUP = False


def _setup_validate_log() -> None:
    """首次调用时在 LOGGING_DIR 下创建 validate_<timestamp>.log。"""
    global _VALIDATE_LOG_SETUP
    if _VALIDATE_LOG_SETUP:
        return
    _VALIDATE_LOG_SETUP = True

    from od_platform.common.paths import LOGGING_DIR
    from datetime import datetime

    log_dir = LOGGING_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"validate_{ts}.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log_path, encoding="utf-8", mode="w")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(fh)
    logger.info("验证日志: %s", log_path)


@time_it(name="所有检测耗时总计", logger_instance=logger, iterations=1)
def run_all_checks(ctx: CheckContext) -> List[CheckResult]:
    """跑全部注册的 check, 收集结果。

    聚合模式承诺: 任何 check 自身抛异常都被本函数接住, 包装成 ERROR 级 CheckResult,
    不阻断其他 check。
    """
    _setup_validate_log()
    entries = get_all_checks()
    logger.info("开始执行 %d 个 checks", len(entries))

    results: List[CheckResult] = []
    for entry in entries:
        result = _safe_run_one(entry, ctx)
        _log_check_result(result)
        results.append(result)

    _log_summary(results)
    return results


@time_it(name=lambda entry, ctx: f"检查:【{entry.name}】", logger_instance=logger, iterations=1)
def _safe_run_one(entry: CheckEntry, ctx: CheckContext) -> CheckResult:
    """跑单个 check, 异常包装成 ERROR — 聚合承诺的兑现处。

    整个 D4 子系统仅此一处用 Exception — 因为 check 是开闭扩展点,
    调度层无法预知第 N 个 check 会抛什么。
    """
    try:
        return entry.func(ctx)
    except Exception as e:
        logger.exception("check '%s' 抛异常, 已捕获为 ERROR 级结果", entry.name)
        return CheckResult(
            name=entry.name,
            severity=CheckSeverity.ERROR,
            summary=f"check 内部异常: {type(e).__name__}: {e}",
            details={"exception_type": type(e).__name__, "exception_msg": str(e)},
        )


def _log_check_result(r: CheckResult) -> None:
    log_method = {
        CheckSeverity.ERROR:   logger.error,
        CheckSeverity.WARNING: logger.warning,
        CheckSeverity.INFO:    logger.info,
        CheckSeverity.PASS:    logger.info,    # 终端展示,默认可见
    }.get(r.severity, logger.info)
    log_method("[%-7s] %s: %s", r.severity, r.name, r.summary)


def _log_summary(results: List[CheckResult]) -> None:
    counts: dict = {}
    for r in results:
        counts[r.severity] = counts.get(r.severity, 0) + 1
    parts = [f"{n} {s}" for s, n in sorted(counts.items())]
    logger.info("check 执行完毕: %s", " / ".join(parts))


# ============================================================
# 端到端: validate_dataset
# ============================================================

def _collect_environment() -> dict:
    """采集运行环境元数据。"""
    import platform as _platform
    import socket
    try:
        hostname = socket.gethostname()
    except OSError:
        hostname = "unknown"
    return {
        "platform": _platform.platform(),
        "python":   f"Python {_platform.python_version()}",
        "hostname": hostname,
    }


def _default_operator() -> Optional[str]:
    try:
        import getpass
        return getpass.getuser()
    except Exception:
        return None


def validate_dataset(
    yaml_path:    Path,
    task_type:    Optional[str] = None,
    run_id:       Optional[str] = None,
    run_dir:      Optional[Path] = None,
    write_report: bool = True,
    options:      Optional[ValidationOptions] = None,
    operator:     Optional[str] = None,
) -> ValidationReport:
    """端到端验证: snapshot → check → report → 写盘 (JSON)。

    Returns:
        ValidationReport (含 run_dir / report_path)
    """
    resolved_run_id  = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    resolved_options = options or ValidationOptions()
    resolved_run_dir = run_dir or (validation_run_dir(resolved_run_id) if write_report else None)

    if write_report and resolved_run_dir is not None:
        resolved_run_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    started_iso = datetime.now(timezone.utc).isoformat()

    snapshot = build_snapshot(yaml_path=yaml_path, task_type=task_type)
    ctx = CheckContext(yaml_path=yaml_path, snapshot=snapshot, options=resolved_options)
    results = run_all_checks(ctx)

    duration = time.perf_counter() - t0

    report = ValidationReport(
        run_id=resolved_run_id,
        yaml_path=yaml_path,
        snapshot=snapshot,
        results=results,
        duration_seconds=duration,
        started_at_iso=started_iso,
        run_dir=resolved_run_dir,
        operator=operator or _default_operator(),
        tool_version=_tool_version,
        environment=_collect_environment(),
    )

    if write_report and resolved_run_dir is not None:
        rp = resolved_run_dir / "report.json"
        rp.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("报告已写入: %s", rp)

    return report
