#!/usr/bin/env python
# -*- coding: utf-8 -*-
from pathlib import Path
from typing import List

from od_platform.common.paths import ROOT_DIR, get_dirs_to_initialize, LOGGING_DIR
from od_platform.common.logging_utils import get_logger, log_execution

LINE_WIDTH = 60
logger = get_logger(
    base_path=LOGGING_DIR,
    log_type="init_project",
    temp_log=False,
)


@log_execution(logger=logger,repeat=4)
def initialize_project() -> None:
    """初始化项目，创建所有必需的目录结构"""
    logger.info("开始初始化项目核心目录".center(LINE_WIDTH, '='))
    print(f"项目根目录: {ROOT_DIR}")

    created: List[Path] = []
    existed: List[Path] = []

    for d in get_dirs_to_initialize():
        rel = d.relative_to(ROOT_DIR)
        if d.exists():
            logger.info(f"目录已存在: {rel}")
            existed.append(d)
        else:
            try:
                d.mkdir(parents=True, exist_ok=True)
                created.append(d)
                logger.info(f"成功创建目录: {rel}")
            except OSError as e:
                logger.error(f"创建目录失败: {rel}: {e}")
                raise SystemExit(1) from e

    logger.info("初始化汇总".center(LINE_WIDTH, '='))
    logger.info(f"{'目录':<25} | {'状态':<10}")
    logger.info("-" * LINE_WIDTH)
    for d in created:
        logger.info(f"{str(d.relative_to(ROOT_DIR)):<25} | {'新创建':<10}")
    for d in existed:
        logger.info(f"{str(d.relative_to(ROOT_DIR)):<25} | {'已存在':<10}")
    logger.info("-" * LINE_WIDTH)
    print(f"初始化完成: 新建了{len(created)}个目录, 已存在{len(existed)}个目录")


if __name__ == "__main__":
    initialize_project()
