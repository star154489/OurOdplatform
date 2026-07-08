#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :transform_data.py
# @Function  :odp-transform CLI —— 数据流水线命令行入口
"""odp-transform:一行命令把原始数据集变成可训练数据集 + dataset.yaml。

用法:
    odp-transform --dataset safety_helmet --format pascal_voc
    odp-transform --dataset demo --format coco --split-strategy stratified
    odp-transform --dataset demo --format pascal_voc --classes head helmet
"""
from __future__ import annotations

import argparse
import logging
import sys

from od_platform.common.constants import AnnotationFormat, SplitStrategy, Task
from od_platform.data_pipeline.orchestrator import DatasetPipeline

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_DATA_ERR = 1
EXIT_USAGE = 2


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="odp-transform",
        description="完成数据集的转换、划分、落盘及对应 yaml 文件的生成",
    )
    p.add_argument("--dataset", required=True, help="数据集名称(data/raw/下的文件夹名)")
    p.add_argument("--format", required=True, choices=AnnotationFormat.all(), dest="fmt",
                   help="标注格式")
    p.add_argument("--task", default=Task.DETECT, choices=Task.all(),
                   help="任务类型(detect/segment)")
    p.add_argument("--split-strategy", default=SplitStrategy.RANDOM,
                   choices=SplitStrategy.all(), dest="strategy",
                   help="划分策略(random/stratified)")
    p.add_argument("--classes", nargs="+", default=None,
                   help="类别白名单(空格分隔,如: head helmet person)")
    p.add_argument("--train-rate", type=float, default=0.8,
                   help="训练集比例(默认 0.8)")
    p.add_argument("--val-rate", type=float, default=0.1,
                   help="验证集比例(默认 0.1,余数为测试集)")
    p.add_argument("--seed", type=int, default=1210,
                   help="随机种子(保证划分可复现)")

    args = p.parse_args(argv)

    pipe = DatasetPipeline(
        args.dataset, args.fmt,
        task=args.task,
        train_rate=args.train_rate,
        val_rate=args.val_rate,
        classes=args.classes,
        split_strategy=args.strategy,
        random_state=args.seed,
    )
    try:
        result = pipe.run()
    except (FileNotFoundError, ValueError) as e:
        logger.error("处理失败: %s", e)
        return EXIT_DATA_ERR

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
