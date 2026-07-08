#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : validate_data.py
# @Function  : odp-validate CLI — 数据集验证命令行入口 (D4)
"""odp-validate: 对已转换的数据集运行全部检查项, 产出 report.json。"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from od_platform.common.constants import Task
from od_platform.data_validation.registry import ValidationOptions
from od_platform.data_validation.service import validate_dataset

logger = logging.getLogger(__name__)


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S", force=True)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="odp-validate",
        description="YOLO 数据集质量验证 — 产出 report.json",
    )
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--dataset", help="数据集名")
    source.add_argument("--yaml", type=Path, help="yaml 完整路径")
    p.add_argument("--task", choices=Task.all(), default=None, help="任务类型")
    p.add_argument("--check-images", action="store_true", help="图像完整性深检 (重型)")
    p.add_argument("--verbose", "-v", action="store_true", help="DEBUG 日志")
    return p


def _resolve_yaml(ref: str) -> Path:
    p = Path(ref)
    if p.exists():
        return p.resolve()
    for prefix in ("apps/platform/", ""):
        r = Path(f"{prefix}configs/datasets/{ref}.yaml")
        if r.exists():
            return r.resolve()
    return Path(f"configs/datasets/{ref}.yaml").resolve()


def main(argv: Optional[list] = None) -> int:
    args = _build_parser().parse_args(argv)
    _setup_logging(verbose=args.verbose)

    try:
        ref = str(args.dataset if args.dataset else args.yaml)
        yaml_path = _resolve_yaml(ref)

        if not yaml_path.exists():
            logger.error("yaml 文件不存在: %s", yaml_path)
            return 2

        options = ValidationOptions(check_images=args.check_images)

        report = validate_dataset(
            yaml_path=yaml_path,
            task_type=args.task,
            options=options,
        )

        return report.exit_code

    except KeyboardInterrupt:
        return 3
    except Exception:
        logger.exception("未预期异常")
        return 3


if __name__ == "__main__":
    sys.exit(main())
