"""落盘:把 SplitManifest 里的 Pair 按 train/val/test 三组拷贝到目标目录。"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator, List, Tuple

from od_platform.data_pipeline.split.manifest import SplitManifest

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp")


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


def _clean_targets(dirs: SplitOutputDirs) -> None:
    """清理目标目录(幂等:已存在则 rmtree 重建)。"""
    for d in dirs.all_dirs():
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)


def _copy_one(src: Path, dst_dir: Path) -> Path:
    """拷贝一个文件到目标目录,返回目标路径。"""
    dst = dst_dir / src.name
    shutil.copy2(src, dst)
    return dst


def materialize(
    manifest: SplitManifest,
    dirs: SplitOutputDirs,
) -> dict:
    """将划分结果物化到目标目录结构。

    Args:
        manifest: 划分结果。
        dirs:     六个目标目录。

    Returns:
        {组名: {images: 路径列表, labels: 路径列表}}
    """
    _clean_targets(dirs)

    result: dict = {}
    groups = [
        ("train", manifest.train, dirs.train_images, dirs.train_labels),
        ("val", manifest.val, dirs.val_images, dirs.val_labels),
        ("test", manifest.test, dirs.test_images, dirs.test_labels),
    ]

    for group_name, pairs, img_dir, lbl_dir in groups:
        images: List[Path] = []
        labels: List[Path] = []
        for img_path, lbl_path in pairs:
            images.append(_copy_one(img_path, img_dir))
            labels.append(_copy_one(lbl_path, lbl_dir))
        result[group_name] = {"images": images, "labels": labels}

    return result
