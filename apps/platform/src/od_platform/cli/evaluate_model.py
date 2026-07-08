#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : evaluate_model.py
# @Project   : ODPlatform
# @Function  : odp-val entry-point —— YOLO 模型验证命令行入口
"""CLI 极薄:解析参数 → 挂日志 → 调 service → 退出码。"""
from __future__ import annotations

import argparse
import logging
import sys

from od_platform.common.logging_utils import get_logger
from od_platform.common.paths import LOGGING_DIR
from od_platform.evaluation import evaluate_yolo

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="odp-val",
        description="评估(验证)YOLO 模型——评估 D6 训练归档的模型权重",
    )
    parser.add_argument("--config", default="val.yaml",
                        help="运行配置名(默认 val.yaml, 由 YAMLLoader 自动在 configs/runtime/ 里查找)")
    parser.add_argument("--model", required=True, help="已训练权重名或路径(models/trained/)")
    parser.add_argument("--data", required=True, help="数据集名或 yaml 路径(configs/datasets/)")
    parser.add_argument("--task", default=None, choices=["detect", "segment"], help="任务类型")
    parser.add_argument("--device", default=None, help="设备(如 0 / 'cpu')")
    parser.add_argument("-v", "--verbose", action="store_true", help="DEBUG 日志")
    args = parser.parse_args(argv)

    get_logger(
        base_path=LOGGING_DIR,
        log_type="val",
        log_level=logging.DEBUG if args.verbose else logging.INFO,
        logger_name="od_platform.cli.evaluate_model",
    )

    cli_overrides = {}
    if args.task:   cli_overrides["task"] = args.task
    if args.device: cli_overrides["device"] = args.device

    result = evaluate_yolo(args.config, args.model, args.data, cli_overrides=cli_overrides)

    if result.success:
        logger.info("评估成功!")
        if result.metrics:
            logger.info(f"  mAP50:   {result.metrics.map50:.4f}")
            logger.info(f"  mAP50-95:{result.metrics.map50_95:.4f}")
            logger.info(f"  精准率:   {result.metrics.precision:.4f}")
            logger.info(f"  召回率:   {result.metrics.recall:.4f}")
        return 0
    else:
        logger.error(f"评估失败: {result.error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
