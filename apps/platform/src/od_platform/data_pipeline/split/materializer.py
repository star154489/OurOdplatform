"""落盘:把 SplitManifest 里的 Pair 按 train/val/test 三组拷贝到目标目录。"""
from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Generator, List, Tuple

from od_platform.data_pipeline.split.manifest import PairList, SplitManifest

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SplitOutputDirs:
    """物化输出的六个目录路径。"""
    train_images: Path
    train_labels: Path
    val_images: Path
    val_labels: Path
    test_images: Path
    test_labels: Path

    @classmethod
    def for_dataset_root(cls, root: Path) -> "SplitOutputDirs":
        """根据数据集根生成标准目录结构。"""
        return cls(
            train_images=root / "train" / "images",
            train_labels=root / "train" / "labels",
            val_images=root / "val" / "images",
            val_labels=root / "val" / "labels",
            test_images=root / "test" / "images",
            test_labels=root / "test" / "labels",
        )

    def all_dirs(self) -> Generator[Path, None, None]:
        """按 train → val → test 顺序 yield 六个路径。"""
        yield self.train_images
        yield self.train_labels
        yield self.val_images
        yield self.val_labels
        yield self.test_images
        yield self.test_labels

    def relative_paths(self) -> dict:
        """返回 yaml 用的相对路径字典(相对于数据集根)。"""
        return {
            "train": "train/images",
            "val": "val/images",
            "test": "test/images",
        }


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
