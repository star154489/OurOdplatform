#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : model_train.py
# @Function  : odp-train CLI — YOLO 训练命令行入口
"""odp-train: 一行命令启动 YOLO 训练。"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime

from od_platform.common.paths import LOGGING_DIR
from od_platform.training.service import train_yolo, TrainResult

logger = logging.getLogger(__name__)


def _setup_logging() -> Path:
    """root logger 同时输出到终端和 LOGGING_DIR/train_<ts>.log。"""
    log_dir = LOGGING_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"train_{ts}.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.FileHandler(log_path, encoding="utf-8", mode="w")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    return log_path


def main(argv: list | None = None) -> int:
    log_path = _setup_logging()

    p = argparse.ArgumentParser(prog="odp-train", description="YOLO 训练")
    p.add_argument("--dataset", default=None, help="数据集名(如 demo_voc)")
    p.add_argument("--config", default="train.yaml", help="训练配置(runtime/train.yaml)")
    p.add_argument("--device", default=None, help="设备(cpu / 0 / 0,1)")
    p.add_argument("--epochs", type=int, default=None)
    p.add_argument("--fraction", type=float, default=None)
    args = p.parse_args(argv)

    logger.info("=" * 60)
    logger.info("YOLO 训练启动")
    logger.info(f"日志文件: {log_path}")

    # 训练配置 yaml (configs/runtime/train.yaml) — 不存在则自动生成
    from od_platform.common.paths import runtime_config_path, RUNTIME_CONFIGS_DIR
    config_path = args.config
    config_full = RUNTIME_CONFIGS_DIR / config_path
    if not config_full.exists():
        logger.info("训练配置不存在,自动生成: %s", config_full)
        from od_platform.runtime_config.train import YOLOTrainConfig
        from od_platform.runtime_config.generator import ConfigGenerator
        ConfigGenerator().generate(YOLOTrainConfig, config_full)

    # CLI 参数覆盖
    cli_args: dict = {}
    if args.dataset:
        from od_platform.common.paths import dataset_yaml_path
        cli_args["data"] = str(dataset_yaml_path(args.dataset))
    if args.device:
        cli_args["device"] = args.device
    if args.epochs:
        cli_args["epochs"] = args.epochs
    if args.fraction:
        cli_args["fraction"] = args.fraction

    result: TrainResult = train_yolo(
        yaml_path=config_path,
        cli_args=cli_args or None,
    )

    if result.success:
        logger.info("训练成功: output=%s", result.output_dir)
        return 0
    else:
        logger.error("训练失败: %s", result.error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
