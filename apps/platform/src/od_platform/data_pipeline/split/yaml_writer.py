"""生成 ultralytics 可直接吃的 dataset.yaml。

包含 odp_meta 元数据块,可追溯数据集来源与划分参数。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from od_platform.data_pipeline.split.manifest import SplitManifest

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def write_dataset_yaml(
    yaml_path: Path,
    *,
    dataset_root: Path,
    classes: List[str],
    manifest: SplitManifest,
    dataset_name: str,
    source_format: str,
    task: str,
    fingerprint: str = "",
) -> Path:
    """生成 ultralytics 风格的 dataset.yaml。

    Args:
        yaml_path:      输出的 yaml 文件路径 (如 configs/datasets/safety_helmet.yaml)。
        dataset_root:   数据落盘根目录 (yaml 里 path 字段指向它)。
        classes:        类别名列表 (下标即 class_id)。
        manifest:       划分清单 (用于判断 train/val/test 是否存在)。
        dataset_name:   数据集名。
        source_format:  来源格式 (写入 yaml 注释,方便追溯)。
        task:           任务类型 (detect / segment)。
        fingerprint:    数据指纹(SHA256 前 16 位),用于验证划分可复现。

    Returns:
        yaml_path(写入了内容)。
    """
    yaml_path.parent.mkdir(parents=True, exist_ok=True)

    names_str = "\n".join(f"  {i}: {name}" for i, name in enumerate(classes))

    # 只写入有数据的子集
    subsets: List[str] = []
    if manifest.train:
        subsets.append("train: train/images")
    if manifest.val:
        subsets.append("val: val/images")
    if manifest.test:
        subsets.append("test: test/images")

    counts = manifest.counts

    meta = {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": dataset_name,
        "source_format": source_format,
        "fingerprint": fingerprint,
        "train_rate": manifest.train_rate,
        "val_rate": manifest.val_rate,
        "test_rate": manifest.test_rate,
        "counts": counts,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_lines = "\n".join(f"#   {k}: {v}" for k, v in meta.items())

    content = f"""# {dataset_name} — ultralytics 数据集配置
# 来源格式: {source_format} | 任务: {task} | 类别数: {len(classes)}
# 由 odp-transform 自动生成,请勿手工修改。
#
# odp_meta:
{meta_lines}

path: {dataset_root}
{chr(10).join(subsets)}
nc: {len(classes)}

names:
{names_str}
"""
    yaml_path.write_text(content, encoding="utf-8")
    logger.info("yaml 已写入: %s (%d 个类别)", yaml_path, len(classes))
    return yaml_path
