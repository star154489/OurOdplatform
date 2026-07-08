#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :transform_data.py
# @Time      :2026/7/1 15:35:11
# @Author    :雨霓同学
# @Project   :ODPlatform
# @Function  :数据转换 CLI 入口 —— odp-transform 命令
"""
三种调用方式:
  1. ``odp-transform`` (console_script, 安装后)
  2. ``python -m od_platform.cli.transform_data`` (模块路径)
  3. ``python scripts/transform_data.py`` (开发期入口)
"""
from __future__ import annotations

import argparse
import logging
import sys

from od_platform.common.constants import AnnotationFormat, SplitStrategy, Task
from od_platform.common.paths import LOGGING_DIR
from od_platform.data_pipeline.orchestrator import DatasetPipeline

EXIT_OK = 0
EXIT_DATA_ERR = 1
EXIT_USAGE = 2


def main(argv: list[str] | None = None) -> int:
    # 导入 logger(只初始化一次)
    from od_platform.common.logging_utils import get_logger
    logger = get_logger(
        base_path=LOGGING_DIR,
        log_type="transform_data",
        logger_name="od_platform.cli.transform_data",
    )

    p = argparse.ArgumentParser(
        prog="odp-transform",
        description="完成数据集的转换、划分、落盘及 yaml 文件生成",
    )
    p.add_argument("--dataset", required=True, help="数据集名称(对应 data/raw/<name>/)")
    p.add_argument("--format", required=True, choices=AnnotationFormat.all(), dest="fmt",
                   help="标注格式")
    p.add_argument("--task", default=Task.DETECT, choices=Task.all(),
                   help="任务类型")
    p.add_argument("--split-strategy", default=SplitStrategy.RANDOM,
                   choices=SplitStrategy.all(), dest="strategy",
                   help="划分策略")
    p.add_argument("--classes", nargs="+", default=None,
                   help="类别白名单(仅 VOC/COCO 支持过滤)")
    p.add_argument("--train-rate", type=float, default=0.8)
    p.add_argument("--val-rate", type=float, default=0.1)
    p.add_argument("--seed", type=int, default=1210)

    a = p.parse_args(argv)

    pipe = DatasetPipeline(
        dataset=a.dataset,
        annotation_format=a.fmt,
        task=a.task,
        train_rate=a.train_rate,
        val_rate=a.val_rate,
        classes=a.classes,
        random_state=a.seed,
        split_strategy=a.strategy,
    )
    try:
        res = pipe.run()
        logger.info("流水线完成: %s", res)
    except (FileNotFoundError, ValueError) as e:
        logger.error("处理失败: %s", e)
        return EXIT_DATA_ERR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
