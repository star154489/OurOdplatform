#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : reset_project.py
# @Author    : ODPlatform team
# @Project   : ODPlatform
# @Function  : 项目重置工具 —— 安全地撤销 init_project 创建的运行时产物
"""
ODPlatform 项目重置工具——安全、可控、可追溯地清理运行时产物。

符合 FR-CLI-001 ~ FR-CLI-017 / FR-SAFE-001 ~ 005 / FR-AUDIT-001 ~ 003 需求。

三种调用方式:
  1. ``odp-reset`` (console_script, 安装后)
  2. ``python -m od_platform.cli.reset_project`` (模块路径)
  3. ``python scripts/reset_project.py`` (开发期入口)

安全机制:
  - 默认 dry-run（Safe by Default）
  - 双层防护：Allowlist + Denylist
  - 交互式二次确认（输入 RESET）
  - 自指安全（日志写入 META_LOGGING_DIR，与 LOGGING_DIR 物理隔离）

退出码（FR-CLI-007）:
  - 0 = dry-run / 用户取消 / 全部删除成功
  - 1 = 删除部分失败
  - 2 = 全部删除失败 / 双层防护触发 / 参数错误
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import stat
import sys
from pathlib import Path
from typing import List, Tuple

from od_platform.common.audit_utils import _audit_context
from od_platform.common.logging_utils import get_logger
from od_platform.common.paths import (
    META_LOGGING_DIR,
    PRETRAINED_MODELS_DIR,
    RAW_DATA_DIR,
    ROOT_DIR,
    get_dirs_to_reset,
    is_protected,
)
from od_platform.common.string_utils import format_table_row, format_table_separator

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
CONFIRM_KEYWORD = "RESET"
LINE_WIDTH = 70
LARGE_DIR_THRESHOLD = 1 * 1024 ** 3  # 1 GiB

# 日志类型
_LOG_TYPE = "reset_project"


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _format_size(bytes_size: int) -> str:
    """二进制单位（GiB / MiB / KiB）—— 统一用 1024 进制。"""
    if bytes_size >= 1024 ** 3:
        return f"{bytes_size / (1024 ** 3):.2f} GiB"
    if bytes_size >= 1024 ** 2:
        return f"{bytes_size / (1024 ** 2):.2f} MiB"
    if bytes_size >= 1024:
        return f"{bytes_size / 1024:.2f} KiB"
    return f"{bytes_size} B"


def _on_rm_error(func, path, exc_info):
    """rmtree 错误回调 —— 处理 Windows 只读文件场景。

    Windows 上某些被 git checkout 出来的文件会被标记只读，
    shutil.rmtree 直接 PermissionError。改成可写后重试。
    Linux / macOS 上 chmod + retry 是无害的，可跨平台使用。

    仅对 PermissionError（WinError 5）尝试 chmod；其他错误直接传播。
    """
    # 仅处理 PermissionError 类错误
    exc = exc_info[1]
    if isinstance(exc, PermissionError):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
            return
        except OSError:
            pass
    # 非 PermissionError 或重试仍失败，传播原始异常
    raise exc


def _scan_target_dirs(logger: logging.Logger) -> Tuple[List[Tuple[Path, int, int]], List[Path]]:
    """扫描所有目标目录，返回 (可删除项, 不存在的目录)。

    可删除项格式：(path, file_count, total_size_bytes)。
    不存在的目录不报错，视为 "0 文件 0 字节"。
    """
    targets: List[Tuple[Path, int, int]] = []
    missing: List[Path] = []

    for d in get_dirs_to_reset():
        if not d.exists():
            missing.append(d)
            continue

        file_count = 0
        total_size = 0
        try:
            for f in d.rglob("*"):
                if f.is_file():
                    file_count += 1
                    try:
                        total_size += f.stat().st_size
                    except OSError:
                        pass
        except (OSError, PermissionError) as e:
            logger.warning(f"扫描 {d.relative_to(ROOT_DIR)} 时出错: {e}")

        targets.append((d, file_count, total_size))

    return targets, missing


def _print_plan(
    logger: logging.Logger,
    targets: List[Tuple[Path, int, int]],
    missing: List[Path],
    will_actually_delete: bool,
) -> None:
    """输出表格化的删除计划（FR-CLI-004）。

    Args:
        logger: 日志记录器
        targets: (path, file_count, total_size) 列表
        missing: 不存在的目录列表
        will_actually_delete: 后续是否会实际删除
    """
    if will_actually_delete:
        logger.warning("⚠️  即将删除以下目录".center(LINE_WIDTH, "="))
    else:
        logger.info("📋 [DRY-RUN] 计划如下（未实际删除）".center(LINE_WIDTH, "="))

    if not targets:
        logger.info("（没有可删除的目录 —— 项目已经是干净状态）")
        return

    # 表格列宽：目录名 40，文件数 12，大小 14
    widths = [40, 12, 14]
    aligns = ["left", "right", "right"]

    logger.info(format_table_row(["目录", "文件数", "大小"], widths, aligns))
    logger.info(format_table_separator(widths))

    total_files = 0
    total_bytes = 0
    for path, count, size in targets:
        rel = path.relative_to(ROOT_DIR)
        logger.info(format_table_row(
            [str(rel), str(count), _format_size(size)], widths, aligns,
        ))
        total_files += count
        total_bytes += size

    logger.info(format_table_separator(widths))
    logger.info(format_table_row(
        ["【合计】", str(total_files), _format_size(total_bytes)], widths, aligns,
    ))

    # 报告不存在的目录
    if missing:
        for path in missing:
            rel = path.relative_to(ROOT_DIR)
            logger.info(f"  （{rel} 不存在，跳过）")

    # 明确列出不会动的目录
    logger.info("")
    logger.info("✅ 以下重要目录【不会】被动:")
    logger.info(f"  - 原始数据: {RAW_DATA_DIR.relative_to(ROOT_DIR)}/")
    logger.info(f"  - 预训练权重: {PRETRAINED_MODELS_DIR.relative_to(ROOT_DIR)}/")
    logger.info("  - 所有代码、文档、配置（进 git 的）")

    if not will_actually_delete:
        logger.info("")
        logger.info("💡 这是 dry-run（默认行为）。要真正执行删除，请加 --yes:")
        logger.info("   python scripts/reset_project.py --yes")
        logger.info("   odp-reset --yes")


def _confirm(deletable_count: int) -> bool:
    """交互式二次确认（FR-SAFE-003）。

    用 print 而非 logger，这是【刻意的视觉打断】——
    让用户从"扫日志"模式切换到"主动决策"模式，
    避免误按回车造成不可逆操作。

    Returns:
        True 表示用户输入了精确的 RESET，False 表示取消。
    """
    print()
    print("=" * LINE_WIDTH)
    print(f"⚠️  你正要删除 {deletable_count} 个目录的内容。这个操作不可撤销。")
    print(f"⚠️  如果确认，请精确输入大写的 '{CONFIRM_KEYWORD}'（其他任何输入都会取消）:")
    print("=" * LINE_WIDTH)
    try:
        user_input = input("> ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return False
    return user_input == CONFIRM_KEYWORD


def _delete_one(
    logger: logging.Logger,
    path: Path,
    idx: int,
    total: int,
    file_count: int,
    size: int,
) -> str | None:
    """删除单个目录，带进度提示（FR-CLI-005 / FR-CLI-012 / FR-CLI-013）。

    Args:
        logger: 日志记录器
        path: 待删除目录的 Path
        idx: 当前序号（从 1 开始）
        total: 总目录数
        file_count: 该目录的文件数
        size: 该目录的总字节数

    Returns:
        None 表示成功，字符串为失败原因。
    """
    # 删除前再做一次防护检查（第二层 Denylist 复核）
    if is_protected(path):
        logger.error(f"[{idx}/{total}] ⛔ 删除前检查失败，受保护路径: {path}")
        return "受保护目录（Denylist 拦截）"

    rel = path.relative_to(ROOT_DIR)
    size_str = _format_size(size)

    if size >= LARGE_DIR_THRESHOLD:
        logger.warning(
            f"[{idx}/{total}] 正在删除 {rel} ({size_str}, {file_count} 个文件)"
            f" —— 这可能需要一会..."
        )
    else:
        logger.info(f"[{idx}/{total}] 删除 {rel} ({size_str}, {file_count} 个文件)")

    try:
        shutil.rmtree(path, onerror=_on_rm_error)
        logger.info(f"[{idx}/{total}] ✅ 已删除: {rel}")
        return None
    except OSError as e:
        logger.error(f"[{idx}/{total}] ❌ 删除失败 {rel}: {e}")
        return str(e)


def _execute_delete(
    logger: logging.Logger,
    targets: List[Tuple[Path, int, int]],
) -> Tuple[int, List[Tuple[Path, str]]]:
    """实际执行删除流程（FR-CLI-005 / FR-SAFE-005）。

    Args:
        logger: 日志记录器
        targets: (path, file_count, total_size) 可删除列表

    Returns:
        (成功数, 失败列表) —— 失败列表元素为 (path, error_message)
    """
    total = len(targets)
    success_count = 0
    failures: List[Tuple[Path, str]] = []

    for idx, (path, file_count, size) in enumerate(targets, 1):
        reason = _delete_one(logger, path, idx, total, file_count, size)
        if reason is None:
            success_count += 1
        else:
            failures.append((path, reason))

    return success_count, failures


def _print_summary(
    logger: logging.Logger,
    success_count: int,
    failures: List[Tuple[Path, str]],
) -> None:
    """输出执行汇总（FR-CLI-006）。

    Args:
        logger: 日志记录器
        success_count: 成功删除的目录数
        failures: (path, error_message) 失败列表
    """
    logger.info("=" * LINE_WIDTH)
    if failures:
        logger.warning(f"完成: 成功 {success_count} 个, 失败 {len(failures)} 个")
        for path, reason in failures:
            logger.warning(f"  - {path.relative_to(ROOT_DIR)}: {reason}")
    else:
        logger.info(f"完成: 成功 {success_count} 个, 失败 0 个")


# ---------------------------------------------------------------------------
# 核心业务函数
# ---------------------------------------------------------------------------


def reset_project(yes: bool = False, force: bool = False, dry_run: bool = False) -> int:
    """项目重置业务函数（FR-CLI-002）。

    作为纯函数设计——所有参数显式传入，不读取 sys.argv / 环境变量，
    便于测试与作为库被其他工具调用。

    Args:
        yes:     是否真正执行删除（默认仅 dry-run）。对应 ``--yes``。
        force:   是否跳过交互式确认（仅当 ``yes=True`` 时有效）。对应 ``--force``。
        dry_run: 显式声明 dry-run；与 ``yes`` 互斥时优先。对应 ``--dry-run``。

    Returns:
        int: 退出码（FR-CLI-007）
          - 0 = dry-run / 用户取消 / 全部成功
          - 1 = 部分删除失败
          - 2 = 全部失败 / 双层防护触发
    """
    # ── 1. 创建工具自身 logger，写入 META_LOGGING_DIR ──────────
    # 符合 FR-AUDIT-003: logger 必须通过 get_logger(base_path=META_LOGGING_DIR) 创建
    logger = get_logger(
        base_path=META_LOGGING_DIR,
        log_type=_LOG_TYPE,
        logger_name="od_platform.cli.reset_project",
    )

    # ── 2. 阶段标题 ─────────────────────────────────────────────
    logger.info("项目重置工具".center(LINE_WIDTH, "="))
    logger.info(f"项目根目录: {ROOT_DIR}")

    # ── 3. 采集审计上下文（FR-AUDIT-001）────────────────────────
    # 审计发生在任何破坏性动作之前（Audit before action）
    ctx = _audit_context()
    logger.info(f"[AUDIT] {ctx}")
    logger.info(f"用户: {ctx['user']}, 主机: {ctx['hostname']}, "
                f"OS: {ctx['os_info']}, Python: {ctx['python_version']}")
    logger.info(f"Git commit: {ctx['git_commit']}")
    logger.info(f"命令行: {' '.join(ctx['argv'])}")

    # ── 4. 参数冲突处理（FR-CLI-009）────────────────────────────
    if dry_run and yes:
        logger.warning("⚠️  同时给了 --dry-run 和 --yes，以 --dry-run 为准（只打印不删除）")
        yes = False

    # ── 5. 获取清理清单 & 双层防护（FR-SAFE-002）────────────────
    targets_raw = get_dirs_to_reset()

    # 第二层 Denylist 复核：任一目标受保护则立即中止（fail-fast）
    for d in targets_raw:
        if is_protected(d):
            logger.error(
                f"⛔ 双层防护触发: {d} 在 get_dirs_to_reset() 清单中，"
                f"但 is_protected() 判定为受保护路径。已中止，未执行任何删除。"
            )
            return 2

    # ── 6. 扫描目标目录（FR-CLI-003）────────────────────────────
    targets, missing = _scan_target_dirs(logger)

    # ── 7. 输出删除计划（FR-CLI-004）────────────────────────────
    _print_plan(logger, targets, missing, will_actually_delete=yes)

    # ── 8. 没有可删除内容 → 直接结束 ────────────────────────────
    if not targets:
        return 0

    # ── 9. 决策分支（FR-SAFE-001 / FR-SAFE-003 / FR-SAFE-004）───
    if not yes:
        return 0

    if not force:
        if not _confirm(len(targets)):
            logger.warning("❌ 用户取消，未执行删除")
            return 0  # 用户取消 → 退出码 0

    # ── 10. 执行删除（FR-CLI-005）─────────────────────────────────
    logger.info("")
    logger.info("开始删除...".center(LINE_WIDTH, "="))
    success_count, failures = _execute_delete(logger, targets)

    # ── 11. 输出汇总（FR-CLI-006）────────────────────────────────
    _print_summary(logger, success_count, failures)

    # ── 12. 返回退出码（FR-CLI-007）─────────────────────────────
    if not failures:
        return 0
    elif success_count == 0:
        return 2  # 全部失败
    else:
        return 1  # 部分失败


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """构建参数解析器（FR-CLI-008）。"""
    parser = argparse.ArgumentParser(
        prog="odp-reset",
        description="重置 ODPlatform 项目 —— 撤销 init_project 创建的运行时产物。"
                    "默认 dry-run（只打印计划，不删除）。必须 --yes 才执行删除。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  odp-reset                  # dry-run，预览将删除的内容\n"
            "  odp-reset --yes            # 预览后交互式确认删除\n"
            "  odp-reset --yes --force    # 无交互删除（CI 友好）\n"
            "  odp-reset --dry-run        # 显式 dry-run\n\n"
            "安全说明:\n"
            "  - 默认 dry-run，绝不意外删除任何文件\n"
            "  --force 仅在同时给出 --yes 时生效\n"
            "  双层防护确保受保护目录不会被删除\n"
            "  每次执行都会在 meta_logging/ 下生成审计日志"
        ),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="真正执行删除（默认是 dry-run，只打印不删除）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="跳过交互式确认（仅当 --yes 时有效）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="显式声明 dry-run（默认行为也是 dry-run，但显式更可读）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口（FR-CLI-001）。

    通过 argparse 解析命令行参数，调度业务流程，返回进程退出码。

    Args:
        argv: 命令行参数列表（用于测试注入），默认读取 sys.argv。

    Returns:
        int: 退出码（遵循 FR-CLI-007 规范）。
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    # FR-SAFE-004: --force 不能单独使用；无 --yes 时等同于 dry-run
    effective_force = args.force if args.yes else False

    return reset_project(
        yes=args.yes,
        force=effective_force,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
