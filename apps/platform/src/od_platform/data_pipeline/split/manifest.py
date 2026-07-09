"""数据容器:Pair / PairList / SplitManifest。

Pair = (image_path, label_path) ——哪张图配哪个标注文件,是整个 split 子系统的"原子"。
SplitManifest = 三次划分的结果 + 比例元数据。
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

from od_platform.common.constants import IMAGE_EXTENSIONS

logger = logging.getLogger(__name__)

Pair = Tuple[Path, Path]
""" (image_path, label_path)。p[0]=图,p[1]=标。"""

PairList = List[Pair]
""" 一批 Pair。"""


def build_manifest(images_dir: Path, labels_dir: Path) -> PairList:
    """按 stem 配对上目录下的图像与标注,返回 (img, lbl) 列表。

    两份目录必须都存在,否则直接报错。
    对于: 有图无标注 / 有标注无图 / 标注为空,会分别打出 WARNING + 统计。
    """
    if not images_dir.is_dir():
        raise FileNotFoundError(f"images 目录不存在: {images_dir}")
    if not labels_dir.is_dir():
        raise FileNotFoundError(f"labels 目录不存在: {labels_dir}")

    # 1. 收集 stems
    image_stems: Dict[str, Path] = {}
    for ext in IMAGE_EXTENSIONS:
        for p in images_dir.glob(f"*{ext}"):
            image_stems[p.stem] = p

    label_stems: Dict[str, Path] = {}
    for p in labels_dir.glob("*.txt"):
        label_stems[p.stem] = p

    # 2. 配对 + 统计异常
    common = sorted(set(image_stems) & set(label_stems))
    only_images = sorted(set(image_stems) - set(label_stems))
    only_labels = sorted(set(label_stems) - set(image_stems))

    pairs: PairList = [(image_stems[s], label_stems[s]) for s in common]

    logger.info(
        "配对完成: %d 对 / %d 图 / %d 标%s",
        len(pairs), len(image_stems), len(label_stems),
        f" (缺标:{len(only_images)} 缺图:{len(only_labels)})" if only_images or only_labels else "",
    )
    if only_images:
        logger.warning("有图无标注 %d 张: %s...", len(only_images), only_images[:5])
    if only_labels:
        logger.warning("有标注无图 %d 个: %s...", len(only_labels), only_labels[:5])
    for stem in common:
        if label_stems[stem].stat().st_size == 0:
            logger.debug("空标注: %s", label_stems[stem].name)

    return pairs


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

    @property
    def counts(self) -> Dict[str, int]:
        return {"train": len(self.train), "val": len(self.val), "test": len(self.test)}

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

    def shuffled(self, seed: int = 0) -> "SplitManifest":
        """返回一个新的 SplitManifest,内部每组 PairList 用给定种子打乱。"""
        rng = random.Random(seed)
        return SplitManifest(
            train=_shuffled_copy(self.train, rng),
            val=_shuffled_copy(self.val, rng),
            test=_shuffled_copy(self.test, rng),
            train_rate=self.train_rate,
            val_rate=self.val_rate,
            test_rate=self.test_rate,
        )


def _shuffled_copy(items: PairList, rng: random.Random) -> PairList:
    lst = list(items)
    rng.shuffle(lst)
    return lst
