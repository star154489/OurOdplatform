#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : snapshot_project.py
# @Author    : ODPlatform team
# @Project   : ODPlatform
# @Function  : 项目快照工具 —— 打包备份项目核心文件
"""ODPlatform 项目快照工具。"""

from __future__ import annotations

import argparse
import sys

from od_platform.common.archive_utils import create_zip_archive
from od_platform.common.logging_utils import get_logger
from od_platform.common.paths import (
    META_DIR,
    META_LOGGING_DIR,
    ROOT_DIR,
    get_project_core_backup_targets,
)

LINE_WIDTH = 70
BACKUP_DIR = META_DIR / "backups"
CORE_BACKUP_LABEL = "project-core"
_LOG_TYPE = "snapshot_project"


def snapshot_project() -> int:
    """打包项目核心文件。"""
    logger = get_logger(
        base_path=META_LOGGING_DIR,
        log_type=_LOG_TYPE,
        logger_name="od_platform.cli.snapshot_project",
    )

    logger.info("项目快照工具".center(LINE_WIDTH, "="))
    logger.info("项目根目录: %s", ROOT_DIR)

    targets = get_project_core_backup_targets()
    logger.info("准备打包 %d 个核心目标", len(targets))
    for target in targets:
        try:
            relative = target.relative_to(ROOT_DIR)
        except ValueError:
            relative = target
        logger.info("  - %s", relative)

    logger.info("")
    logger.info("开始打包项目核心文件...".center(LINE_WIDTH, "="))
    backup_path = create_zip_archive(
        logger,
        root_dir=ROOT_DIR,
        targets=targets,
        backup_dir=BACKUP_DIR,
        label=CORE_BACKUP_LABEL,
        tool_name="odp-snapshot",
    )
    if backup_path is None:
        logger.error("项目核心文件快照失败")
        return 2

    logger.info("项目核心文件快照完成: %s", backup_path)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="odp-snapshot",
        description="打包备份 ODPlatform 项目核心文件快照。",
        epilog=(
            "示例:\n"
            "  odp-snapshot              # 打包项目核心文件\n"
            "  python scripts/snapshot_project.py\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    parser.parse_args(argv)
    return snapshot_project()


if __name__ == "__main__":
    sys.exit(main())
