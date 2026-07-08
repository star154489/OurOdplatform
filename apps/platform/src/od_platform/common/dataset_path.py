#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :dataset_path.py
# @Time      :2026/7/6 14:15:14
# @Author    :雨霓同学
# @Project   :ODPlatform
# @Function  :
from __future__ import  annotations

import logging
from pathlib import Path


from od_platform.common.paths import DATASET_CONFIGS_DIR

logger = logging.getLogger(__name__)


def resolve_dataset_path(data: str | Path) -> Path:
    data_path = Path(data)
    # 分支1：绝对路径
    if data_path.is_absolute():
        if data_path.exists():
            return data_path
        raise FileNotFoundError(f"数据集路径不存在: {data_path}")

    # 分支2：按文件名查找（尝试加 .yaml 后缀）
    candidates = [
        DATASET_CONFIGS_DIR / data_path.name,
        DATASET_CONFIGS_DIR / f"{data_path.name}.yaml",
    ]
    for c in candidates:
        if c.exists():
            logger.info(f"数据集配置文件已找到: {c}")
            return c

    # 分支3: 找不到 → 报错（不把无效路径传给 ultralytics）
    raise FileNotFoundError(
        f"找不到数据集配置 '{data}'。\n"
        f"  已搜索: {DATASET_CONFIGS_DIR}\n"
        f"  提示: 请先运行 odp-transform --dataset {data_path.stem} --format <fmt>\n"
        f"  或使用 --yaml 参数直接指定 yaml 路径"
    )
