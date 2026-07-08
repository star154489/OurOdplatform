#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : yaml_writer.py
# @Function  : 生成 ultralytics 可直接吃的 dataset.yaml
"""根据划分结果写入 YAML 配置文件。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from od_platform.data_pipeline.split.manifest import SplitManifest

logger = logging.getLogger(__name__)


def write_dataset_yaml(
    yaml_path: Path,
    *,
    dataset_root: Path,
    classes: List[str],
    manifest: SplitManifest,
    dataset_name: str,
    source_format: str,
    task: str,
) -> None:
    """生成 ultralytics 风格的 dataset.yaml。

    Args:
        yaml_path:      输出的 yaml 文件路径 (如 configs/datasets/safety_helmet.yaml)。
        dataset_root:   数据落盘根目录 (yaml 里 path 字段指向它)。
        classes:        类别名列表 (下标即 class_id)。
        manifest:       划分清单 (用于判断 train/val/test 是否存在)。
        dataset_name:   数据集名。
        source_format:  来源格式 (写入 yaml 注释,方便追溯)。
        task:           任务类型 (detect / segment)。
    """
    yaml_path.parent.mkdir(parents=True, exist_ok=True)

    names_str = "\n".join(f"  {i}: {name}" for i, name in enumerate(classes))

    # 只写入有数据的子集
    subsets = []
    if manifest.train:
        subsets.append(f"train: train/images")
    if manifest.val:
        subsets.append(f"val: val/images")
    if manifest.test:
        subsets.append(f"test: test/images")

    content = f"""# {dataset_name} — ultralytics 数据集配置
# 来源格式: {source_format} | 任务: {task} | 类别数: {len(classes)}
# 由 odp-transform 自动生成,请勿手工修改。

path: {dataset_root}
{chr(10).join(subsets)}
nc: {len(classes)}

names:
{names_str}
"""
    yaml_path.write_text(content, encoding="utf-8")
    logger.info("yaml 已写入: %s (%d 个类别)", yaml_path, len(classes))
