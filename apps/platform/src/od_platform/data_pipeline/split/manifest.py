#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : manifest.py
# @Function  : 划分清单数据结构
"""Pair / PairList / SplitManifest —— 划分子系统的核心数据类型。"""
from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

# (原图路径, 标注 txt 路径)
Pair = Tuple[Path, Path]
PairList = List[Pair]


@dataclass
class SplitManifest:
    """一次划分的完整结果:三组 (图,标注) 对。"""
    train: PairList
    val: PairList
    test: PairList

    def shuffled(self, seed: int = 0) -> 'SplitManifest':
        """返回各组内部随机打乱后的新副本(不改原数据)。"""
        rng = random.Random(seed)
        return SplitManifest(
            train=_shuffled_copy(self.train, rng),
            val=_shuffled_copy(self.val, rng),
            test=_shuffled_copy(self.test, rng),
        )


def _shuffled_copy(items: PairList, rng: random.Random) -> PairList:
    lst = list(items)
    rng.shuffle(lst)
    return lst
