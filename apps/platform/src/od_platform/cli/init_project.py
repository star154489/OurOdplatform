"""
项目初始化 CLI 入口 —— ``main``。

执行步骤:
  1. 创建 logger
  2. 打印阶段标题 / 项目根
  3. 输出环境快照
  4. 遍历 paths.get_dirs_to_initialize() 逐个创建目录
  5. 检查 RAW_DATA_DIR 状态
  6. 输出汇总表格
  7. 输出下一步指引

三种调用方式:
  - ``odp-init`` (console_script, 安装后)
  - ``python -m od_platform.cli.init_project`` (模块路径)
  - ``python scripts/init_project.py`` (开发期入口)

退出码:
  - 0 = 成功
  - 3 = 初始化失败（工具自身错误）
"""

import argparse
import logging
import shutil
import sys
from pathlib import Path
from typing import List, Tuple

from od_platform.common import paths
from od_platform.common.logging_utils import get_logger
from od_platform.common.performance_utils import time_it
from od_platform.common.string_utils import (
    format_table_row,
    format_table_separator,
)
from od_platform.common.system_utils import log_device_info

# 退出码常量
EXIT_OK = 0
EXIT_CRASH = 3

# 日志类型常量（决定日志文件子目录与文件名前缀）
_LOG_TYPE = "init_project"
_LINE_WIDTH: int = 60


# ---------------------------------------------------------------------------
# 核心：初始化函数
# ---------------------------------------------------------------------------


def initialize_project() -> None:
    """
    项目初始化主入口。

    创建全部运行时目录、采集环境快照、检查原始数据目录状态，
    并提供下一步指引。
    """
    # ── 1. 创建 logger ───────────────────────────────────────
    logger = get_logger(
        base_path=paths.LOGGING_DIR,
        log_type=_LOG_TYPE,
        logger_name="od_platform.cli.init_project",
    )

    # ── 2. 阶段标题 ───────────────────────────────────────────
    logger.info("")
    logger.info("=" * _LINE_WIDTH)
    logger.info("  ODPlatform 项目初始化")
    logger.info("=" * _LINE_WIDTH)
    logger.info(f"项目根目录: {paths.ROOT_DIR}")

    # ── 3. 环境快照 ───────────────────────────────────────────
    logger.info("")
    log_device_info(logger)

    # ── 4. 创建运行时目录 ─────────────────────────────────────
    logger.info("")
    logger.info("─" * _LINE_WIDTH)
    logger.info("目录初始化")
    logger.info("─" * _LINE_WIDTH)

    dirs = paths.get_dirs_to_initialize()
    summary: List[Tuple[str, str]] = []  # (相对路径, 状态)

    for d in dirs:
        relative = _relative_path(d)
        try:
            if d.exists():
                logger.info("  目录已存在: %s", relative)
                summary.append((relative, "已存在"))
            else:
                d.mkdir(parents=True, exist_ok=True)
                logger.info("  成功创建:   %s", relative)
                summary.append((relative, "成功创建"))
        except OSError as e:
            logger.error("  目录创建失败: %s — %s", relative, e)
            sys.exit(1)  # fail-fast

    # ── 5. RAW_DATA_DIR 状态检查 ──────────────────────────────
    _check_raw_data_status(logger)

    # ── 6. 汇总表格 ───────────────────────────────────────────
    logger.info("")
    logger.info("─" * _LINE_WIDTH)
    logger.info("初始化汇总")
    logger.info("─" * _LINE_WIDTH)
    _log_summary_table(logger, summary)

    # ── 7. 下一步指引 ─────────────────────────────────────────
    logger.info("")
    logger.info("=" * _LINE_WIDTH)
    logger.info("下一步指引")
    logger.info("=" * _LINE_WIDTH)
    logger.info("  1. 将数据集放入 data/raw/<数据集名称>/（含 images/ 与 annotations/）")
    logger.info("  2. 检查 models/pretrained/ 下是否有预训练权重")
    logger.info("  3. 开始训练: python scripts/train.py")
    logger.info("")
    logger.info("  日志已保存至: %s", paths.LOGGING_DIR / _LOG_TYPE)
    logger.info("=" * _LINE_WIDTH)


# ---------------------------------------------------------------------------
# FR-INIT-002：原始数据目录状态检查
# ---------------------------------------------------------------------------


def _check_raw_data_status(logger) -> None:
    """
    检查 ``paths.RAW_DATA_DIR`` 状态，输出对应的指引信息。
    """
    raw = paths.RAW_DATA_DIR
    if not raw.exists():
        logger.warning("原始数据目录不存在: %s", _relative_path(raw))
        logger.warning("请创建该目录并放入以数据集名称命名的子文件夹")
        logger.warning("预期结构: data/raw/<dataset_name>/{images/, annotations/}")
    elif not any(raw.iterdir()):
        logger.warning("原始数据目录为空: %s", _relative_path(raw))
        logger.warning("请放入至少一个数据集子文件夹")
        logger.warning("预期结构: data/raw/<dataset_name>/{images/, annotations/}")
    else:
        datasets = sorted(
            [p.name for p in raw.iterdir() if p.is_dir()]
        )
        logger.info("原始数据目录中包含 %d 个数据集:", len(datasets))
        for ds in datasets:
            logger.info("  - %s", ds)


# ---------------------------------------------------------------------------
# FR-INIT-003：汇总表格（幂等性 + 结果展示）
# ---------------------------------------------------------------------------


def _log_summary_table(logger, summary: List[Tuple[str, str]]) -> None:
    """
    以对齐表格输出目录创建汇总。
    """
    col_widths = [48, 12]
    header = format_table_row(["目录", "状态"], col_widths)
    sep = format_table_separator(col_widths)

    logger.info(sep)
    logger.info(header)
    logger.info(sep)
    for rel_path, status in summary:
        logger.info(format_table_row([rel_path, status], col_widths))
    logger.info(sep)


def _relative_path(p: Path) -> str:
    """返回相对于 ROOT_DIR 的可读路径。"""
    try:
        return str(p.relative_to(paths.ROOT_DIR))
    except ValueError:
        return str(p)


# ---------------------------------------------------------------------------
# 模块路径直接运行支持 / CLI 入口
# ---------------------------------------------------------------------------


def main(argv: list | None = None) -> int:
    """
    项目初始化的 CLI 入口。

    用法::

        odp-init [--verbose]

    Args:
        argv: 命令行参数列表，默认读取 sys.argv

    Returns:
        int: 退出码（0=成功, 3=失败）
    """
    parser = argparse.ArgumentParser(
        prog="odp-init",
        description="初始化 ODPlatform 项目运行时目录与环境",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="输出更详细的日志",
    )
    args = parser.parse_args(argv)

    try:
        if args.verbose:
            logging.getLogger("od_platform.cli.init_project").setLevel(logging.DEBUG)
        initialize_project()
    except Exception as e:
        logging.getLogger("od_platform.cli.init_project").exception(
            "项目初始化失败: %s", e
        )
        return EXIT_CRASH

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
