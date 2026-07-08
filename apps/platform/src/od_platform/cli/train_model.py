#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""odp-train CLI —— 一行起训练。"""
from __future__ import annotations

import argparse
import logging
import os as _os
import platform as _platform
import sys
from pathlib import Path

from od_platform.common.constants import Task
from od_platform.common.logging_utils import get_logger
from od_platform.common.paths import LOGGING_DIR


def main(argv: list[str] | None = None) -> int:
    # Windows CUDA DLL 加载限制: 在 import torch/ultralytics 之前设置
    if _platform.system() == "Windows":
        _os.environ.setdefault("CUDA_MODULE_LOADING", "LAZY")
        # 如果页面文件实在太小, 可传 --device cpu 跳过 CUDA DLL 加载
        # (训练变慢但保证能跑)

    from od_platform.training.service import train_yolo
    parser = argparse.ArgumentParser(
        prog="odp-train",
        description="YOLO 模型训练——编排 D4 校验 + D5 配置 + ultralytics 训练",
    )
    parser.add_argument("--config", default=None, help="train 配置 yaml (默认 configs/runtime/train.yaml)")
    parser.add_argument("--data", default=None, help="数据集 yaml/名字 (默认从配置里取)")
    parser.add_argument("--model", default=None, help="模型名/权重路径 (默认 yolo11n.pt)")
    parser.add_argument("--epochs", type=int, default=None, help="训练轮数 (覆盖 yaml)")
    parser.add_argument("--batch", type=int, default=None, help="批次大小 (覆盖 yaml)")
    parser.add_argument("--imgsz", type=int, default=None, help="输入尺寸 (覆盖 yaml)")
    parser.add_argument("--lr0", type=float, default=None, help="初始学习率 (覆盖 yaml)")
    parser.add_argument("--device", default=None, help="设备 (如 0 / 'cpu' / '0,1')")
    parser.add_argument("--task", choices=Task.all(), default=None, help=f"任务类型: {Task.all()}")
    parser.add_argument("--experiment-name", default=None, dest="experiment_name", help="实验名 (组织输出目录)")
    parser.add_argument("--no-archive", action="store_true", help="不归档权重到 trained/")
    parser.add_argument("--no-rename-log", action="store_true", help="不改名日志文件")
    parser.add_argument("--academic-plots", action="store_true", help="应用学术发表绘图风格")
    parser.add_argument("-v", "--verbose", action="store_true", help="DEBUG 日志")

    args = parser.parse_args(argv)

    logger = get_logger(
        base_path=LOGGING_DIR,
        log_type="train",
        log_level=logging.DEBUG if args.verbose else logging.INFO,
        logger_name="od_platform.cli.train_model",
    )

    # 构建 cli extras
    extras = {}
    if args.data:   extras["data"] = args.data
    if args.model:  extras["model"] = args.model
    if args.epochs: extras["epochs"] = args.epochs
    if args.batch:  extras["batch"] = args.batch
    if args.imgsz:  extras["imgsz"] = args.imgsz
    if args.lr0:    extras["lr0"] = args.lr0
    if args.device: extras["device"] = args.device
    if args.task:   extras["task"] = args.task
    if args.experiment_name: extras["experiment_name"] = args.experiment_name

    if args.academic_plots:
        from od_platform.common.plot_style import apply_academic_style
        apply_academic_style()

    result = train_yolo(
        yaml_path=args.config,
        cli_args=extras,
        archive=not args.no_archive,
        rename_log=not args.no_rename_log,
    )

    if result.success:
        logger.info("训练成功！最佳权重: %s", result.best_weight)
        return 0
    else:
        logger.error("训练失败: %s", result.error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
