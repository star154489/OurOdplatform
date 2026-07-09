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
from pathlib import Path

from od_platform.common.archive_utils import create_zip_archive
from od_platform.common.logging_utils import get_logger
from od_platform.common.paths import (
    META_DIR,
    META_LOGGING_DIR,
    ROOT_DIR,
    get_project_core_backup_target_map,
)

LINE_WIDTH = 70
BACKUP_DIR = META_DIR / "backups"
CORE_BACKUP_LABEL = "project-core"
_LOG_TYPE = "snapshot_project"


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


def _resolve_targets(
    *,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[Path]:
    """按名字解析项目快照目标。"""
    target_map = get_project_core_backup_target_map()
    include_names = include or []
    exclude_names = exclude or []

    unknown = sorted(set(include_names + exclude_names) - set(target_map))
    if unknown:
        raise ValueError(f"未知快照目标: {', '.join(unknown)}")

    selected_names = list(target_map) if not include_names else include_names
    excluded = set(exclude_names)
    selected = [(name, target_map[name]) for name in selected_names if name not in excluded]
    return [path for _, path in selected]


def _print_target_catalog() -> None:
    """打印可选快照目标列表。"""
    print("[PROJECT CORE TARGET OPTIONS]")
    for name, path in get_project_core_backup_target_map().items():
        print(f"{name:<20} {_relative(path)}")


def snapshot_project(
    *,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> int:
    """打包项目核心文件。"""
    logger = get_logger(
        base_path=META_LOGGING_DIR,
        log_type=_LOG_TYPE,
        logger_name="od_platform.cli.snapshot_project",
    )

    logger.info("项目快照工具".center(LINE_WIDTH, "="))
    logger.info("项目根目录: %s", ROOT_DIR)

    targets = _resolve_targets(include=include, exclude=exclude)
    logger.info("准备打包 %d 个核心目标", len(targets))
    for target in targets:
        logger.info("  - %s", _relative(target))

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
    parser = argparse.ArgumentParser(
        prog="odp-snapshot",
        description="打包备份 ODPlatform 项目核心文件快照。",
        epilog=(
            "示例:\n"
            "  odp-snapshot              # 打包项目核心文件\n"
            "  odp-snapshot --list       # 查看可选快照目标\n"
            "  odp-snapshot --include src docs\n"
            "  odp-snapshot --exclude docs\n"
            "  python scripts/snapshot_project.py\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出可选的项目快照目标并退出",
    )
    parser.add_argument(
        "--include",
        nargs="+",
        metavar="TARGET",
        help="只打包指定名称的快照目标",
    )
    parser.add_argument(
        "--exclude",
        nargs="+",
        metavar="TARGET",
        help="从默认目标中排除指定名称的快照目标",
    )
    return parser

def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.list:
        _print_target_catalog()
        return 0

    try:
        return snapshot_project(include=args.include, exclude=args.exclude)
    except ValueError as e:
        parser.error(str(e))


if __name__ == "__main__":
    sys.exit(main())
