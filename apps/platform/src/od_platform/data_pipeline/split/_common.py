"""split 子系统内部共享工具:比例校验 / 随机打乱 / 三路计数。"""
from __future__ import annotations

import random
from typing import List, Tuple

from od_platform.common.constants import RATE_EPSILON


def validate_rates(train_rate: float, val_rate: float) -> float:
    """校验比例并计算 test_rate。Raises: ValueError 比例不合法。"""
    if train_rate < 0 or val_rate < 0:
        raise ValueError(f"比例不能为负: train={train_rate}, val={val_rate}")
    test_rate = 1.0 - train_rate - val_rate
    if test_rate < -RATE_EPSILON:
        raise ValueError(f"train_rate + val_rate = {train_rate + val_rate} > 1.0")
    if test_rate < 0:
        test_rate = 0.0
    if test_rate < 0 and abs(test_rate) < RATE_EPSILON:
        test_rate = 0.0
    return test_rate


def seeded_shuffled(items: list, random_state: int) -> list:
    """用固定种子打乱列表并返回新列表(不修改原列表)。"""
    rng = random.Random(random_state)
    xs = list(items)
    rng.shuffle(xs)
    return xs


def three_way_counts(
    total: int, train_rate: float, val_rate: float, test_rate: float,
) -> Tuple[int, int, int]:
    """根据总数和比例计算 train/val/test 三组各应分多少项。"""
    n_train = round(total * train_rate)
    n_val = round(total * val_rate)
    n_test = total - n_train - n_val
    if n_test < 0:
        n_val += n_test
        n_test = 0
    return n_train, n_val, n_test
