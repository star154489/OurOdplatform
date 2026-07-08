"""数据容器:Pair / PairList / SplitManifest。

Pair = (image_path, label_path) ——哪张图配哪个标注文件,是整个 split 子系统的"原子"。
SplitManifest = 三次划分的结果 + 比例元数据。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

Pair = Tuple[Path, Path]
""" (image_path, label_path)。p[0]=图,p[1]=标。"""

PairList = List[Pair]
""" 一批 Pair。"""


def pairs_to_images(pairs: PairList) -> List[Path]:
    return [p[0] for p in pairs]


def pairs_to_labels(pairs: PairList) -> List[Path]:
    return [p[1] for p in pairs]


@dataclass
class SplitManifest:
    """一次划分的全部结果 + 产生它的元数据。

    train/val/test 各是一批 Pair。
    train_rate/val_rate/test_rate 是调用者要求的比例(可能因浮点不精确,与数据实际比例有微小偏差)。
    """
    train: PairList = field(default_factory=list)
    val: PairList = field(default_factory=list)
    test: PairList = field(default_factory=list)
    train_rate: float = 0.8
    val_rate: float = 0.1
    test_rate: float = 0.1

    @property
    def total(self) -> int:
        return len(self.train) + len(self.val) + len(self.test)

    def summary(self) -> dict:
        """人类可读的汇总。"""
        return {
            "train": len(self.train),
            "val": len(self.val),
            "test": len(self.test),
            "total": self.total,
            "train_rate": self.train_rate,
            "val_rate": self.val_rate,
            "test_rate": self.test_rate,
        }
