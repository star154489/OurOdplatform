"""data_validation 调度层 — run_all_checks + validate_dataset。

聚合模式核心承诺: 任何 check 抛异常都不能阻断其他 check。
这条承诺通过 _safe_run_one 里的 try/except Exception 兑现。
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from od_platform._version import __version__
from od_platform.common.paths import validation_run_dir
from od_platform.common.performance_utils import time_it
from od_platform.common.system_utils import log_device_info
from od_platform.data_validation.fingerprint import compute_fingerprint
from od_platform.data_validation.profiler import run_profile
from od_platform.data_validation.registry import (
    CheckContext,
    CheckEntry,
    CheckResult,
    CheckSeverity,
    ValidationOptions,
    get_all_checks,
)
from od_platform.data_validation.render_markdown import render_markdown
from od_platform.data_validation.report import ValidationReport
from od_platform.data_validation.snapshot import build_snapshot

logger = logging.getLogger(__name__)


@time_it(name="所有检测耗时总计", logger_instance=logger, iterations=1)
def run_all_checks(ctx: CheckContext) -> List[CheckResult]:
    """跑全部注册的 check, 收集结果。

    聚合模式承诺:
        任何 check 自身抛异常都被本函数接住, 包装成 ERROR 级 CheckResult,
        不阻断其他 check。
    """
    entries = get_all_checks()
    logger.info(f"开始执行 {len(entries)} 个 check")

    results: List[CheckResult] = []
    for entry in entries:
        result = _safe_run_one(entry, ctx)
        _log_check_result(result)
        results.append(result)

    _log_summary(results)
    return results


@time_it(name=lambda entry, ctx: f"检查:【{entry.name}】", logger_instance=logger, iterations=1)
def _safe_run_one(entry: CheckEntry, ctx: CheckContext) -> CheckResult:
    """跑单个 check, 异常包装成 ERROR — 聚合模式承诺的兑现处。"""
    try:
        return entry.func(ctx)
    except Exception as e:
        logger.exception(f"check '{entry.name}' 抛异常, 已捕获为 ERROR 级结果")
        return CheckResult(
            name=entry.name,
            severity=CheckSeverity.ERROR,
            summary=f"check 内部异常: {type(e).__name__}: {e}",
            details={
                "exception_type": type(e).__name__,
                "exception_msg":  str(e),
            },
        )


def _log_check_result(r: CheckResult) -> None:
    """单个 check 跑完即时打一条日志。

    Severity → log level 映射:
        ERROR   → logger.error
        WARNING → logger.warning
        INFO    → logger.info
        PASS    → logger.debug
    """
    log_method = {
        CheckSeverity.ERROR:   logger.error,
        CheckSeverity.WARNING: logger.warning,
        CheckSeverity.INFO:    logger.info,
        CheckSeverity.PASS:    logger.debug,
    }.get(r.severity, logger.info)
    log_method(f"[{r.severity:7s}] {r.name}: {r.summary}")


def _log_summary(results: List[CheckResult]) -> None:
    """所有 check 跑完后, 打一行总览。"""
    counts = {}
    for r in results:
        counts[r.severity] = counts.get(r.severity, 0) + 1
    parts = [f"{n} {s}" for s, n in counts.items()]
    logger.info(f"check 执行完毕: {' / '.join(parts)}")


def _collect_environment() -> dict:
    """采集运行环境元数据 — 报告可追溯性。"""
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
    """默认操作人 = 系统用户名 (审计字段)。"""
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
    """端到端验证: snapshot → check → 指纹 → 画像 → report → 写盘。

    容错承诺:
        指纹 / 画像 / Markdown 是辅助产物, 任何一步抛异常只记日志降级,
        绝不阻断验证主流程 — exit_code 永远只由 check 结果决定。

    Args:
        yaml_path:    数据集 yaml 文件路径
        task_type:    'detect' / 'segment' / None (读 yaml.task, 再不行 detect)
        run_id:       手动指定运行 ID; None 表示自动用时间戳
        run_dir:      手动指定运行目录; None 表示用 validation_run_dir(run_id)
        write_report: 是否写报告产物 (report.json / report.md / *.csv)
        options:      运行开关 (None = 全默认)
        operator:     操作人 (None = 系统用户名)

    Returns:
        ValidationReport
    """
    # ---- 解析 run_id / run_dir / options ----
    resolved_run_id  = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    resolved_run_dir = run_dir or (validation_run_dir(resolved_run_id) if write_report else None)
    resolved_options = options or ValidationOptions()

    if write_report and resolved_run_dir is not None:
        resolved_run_dir.mkdir(parents=True, exist_ok=True)

    # ---- 跑核心流程 ----
    t0 = time.perf_counter()
    started_iso = datetime.now(timezone.utc).isoformat()

    log_device_info(logger)
    snapshot = build_snapshot(yaml_path=yaml_path, task_type=task_type)
    ctx = CheckContext(
        yaml_path=yaml_path, snapshot=snapshot, options=resolved_options,
    )
    results = run_all_checks(ctx)

    # ---- 辅助产物 1: 数据指纹 ----
    fingerprint = None
    try:
        fingerprint = compute_fingerprint(snapshot)
    except Exception:
        logger.exception("数据指纹计算失败 — 降级为 None, 不阻断验证")

    # ---- 辅助产物 2: 画像 + 明细 CSV ----
    profile = None
    if resolved_options.profile:
        try:
            profile = run_profile(
                snapshot,
                resolved_options,
                out_dir=resolved_run_dir if write_report else None,
            )
        except Exception as e:
            logger.exception("画像构建失败 — 降级为未生成, 不阻断验证")
            profile = {"generated": False, "error": f"{type(e).__name__}: {e}"}

    duration = time.perf_counter() - t0

    # ---- 包装 ValidationReport ----
    report = ValidationReport(
        run_id=resolved_run_id,
        yaml_path=yaml_path,
        snapshot=snapshot,
        results=results,
        duration_seconds=duration,
        started_at_iso=started_iso,
        run_dir=resolved_run_dir,
        fingerprint=fingerprint,
        profile=profile,
        operator=operator or _default_operator(),
        tool_version=__version__,
        environment=_collect_environment(),
    )

    # ---- 写报告产物 ----
    if write_report and resolved_run_dir is not None:
        report_path = resolved_run_dir / "report.json"
        report_path.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            md_path = resolved_run_dir / "report.md"
            md_path.write_text(render_markdown(report), encoding="utf-8")
            logger.info(f"Markdown 报告已写入: {md_path}")
        except Exception:
            logger.exception("Markdown 报告渲染失败 — JSON 报告不受影响")

    return report
