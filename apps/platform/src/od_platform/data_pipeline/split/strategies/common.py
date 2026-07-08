#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : common.py
# @Function  : 划分策略公共工具:比例校验 / 三段计数 / 可复现打乱
"""三个纯函数,给所有划分策略共用。"""
from __future__ import annotations

import math
import random
from typing import List, Tuple, TypeVar

T = TypeVar("T")


def validate_rates(train_rate: float, val_rate: float) -> None:
    """校验 train/val 比例合法(>0, 和 <=1)。"""
    if not (0.0 < train_rate <= 1.0):
        raise ValueError(f"train_rate 必须在 (0,1],实际为 {train_rate}")
    if not (0.0 <= val_rate < 1.0):
        raise ValueError(f"val_rate 必须在 [0,1),实际为 {val_rate}")
    if train_rate + val_rate > 1.0:
        raise ValueError(
            f"train_rate({train_rate}) + val_rate({val_rate}) = {train_rate + val_rate} > 1"
        )


def three_way_counts(n: int, train_rate: float, val_rate: float) -> Tuple[int, int, int]:
    """按比例算出三段数量,余数归 train。

    Returns:
        (n_train, n_val, n_test)
    """
    n_train = math.floor(n * train_rate)
    n_val = math.floor(n * val_rate)
    n_test = n - n_train - n_val
    # 余数归 train(保证不丢样本)
    n_train += n - (n_train + n_val + n_test)
    return n_train, n_val, n_test


def seeded_shuffled(items: List[T], seed: int) -> List[T]:
    """返回一个用给定 seed 打乱后的新列表(不改原列表),保证可复现。"""
    rng = random.Random(seed)
    lst = list(items)
    rng.shuffle(lst)
    return lst
