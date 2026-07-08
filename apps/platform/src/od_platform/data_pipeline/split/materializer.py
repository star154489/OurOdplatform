#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : materializer.py
# @Function  : 落盘 —— 把 SplitManifest 的三组文件写进物理目录
"""把划分结果拷贝/链接到可训练目录结构。"""
from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from od_platform.data_pipeline.split.manifest import PairList, SplitManifest

logger = logging.getLogger(__name__)


@dataclass
class SplitOutputDirs:
    """划分后的输出目录结构(train/val/test 各含 images/ + labels/)。"""
    train_images: Path
    train_labels: Path
    val_images: Path
    val_labels: Path
    test_images: Path
    test_labels: Path

    @classmethod
    def for_dataset_root(cls, root: Path) -> 'SplitOutputDirs':
        return cls(
            train_images=root / "train" / "images",
            train_labels=root / "train" / "labels",
            val_images=root / "val" / "images",
            val_labels=root / "val" / "labels",
            test_images=root / "test" / "images",
            test_labels=root / "test" / "labels",
        )

    def all_dirs(self) -> list[Path]:
        return [
            self.train_images, self.train_labels,
            self.val_images, self.val_labels,
            self.test_images, self.test_labels,
        ]


def _link_or_copy(src: Path, dst: Path) -> None:
    """优先硬链接(零拷贝),跨盘退回复制。"""
    if dst.exists():
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _materialize_one_set(split_name: str, pairs: PairList,
                         img_dir: Path, lbl_dir: Path) -> int:
    """把一组 (图,标) 对落盘到指定目录,返回落盘数量。"""
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for img_path, lbl_path in pairs:
        _link_or_copy(img_path, img_dir / img_path.name)
        if lbl_path.exists():
            _link_or_copy(lbl_path, lbl_dir / lbl_path.name)
        count += 1
    logger.info("  %s: %d 个样本", split_name, count)
    return count


def materialize(manifest: SplitManifest, dirs: SplitOutputDirs) -> dict:
    """把 manifest 里三组 PairList 写到 dirs 对应的物理目录。

    Returns:
        dict: {"train": N, "val": M, "test": K}
    """
    logger.info("落盘划分结果...")
    return {
        "train": _materialize_one_set("train", manifest.train, dirs.train_images, dirs.train_labels),
        "val": _materialize_one_set("val", manifest.val, dirs.val_images, dirs.val_labels),
        "test": _materialize_one_set("test", manifest.test, dirs.test_images, dirs.test_labels),
    }
