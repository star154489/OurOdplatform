#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : random_split.py
# @Function  : 纯随机划分策略
"""纯随机划分:打乱 → 按比例切三段。最通用的划分方式。"""
from __future__ import annotations

from od_platform.common.constants import SplitStrategy
from od_platform.data_pipeline.split.manifest import PairList, SplitManifest
from od_platform.data_pipeline.split.strategies.common import (
    seeded_shuffled,
    three_way_counts,
    validate_rates,
)
from od_platform.data_pipeline.split.strategy_registry import (
    SplitOptions,
    register_strategy,
)


@register_strategy(SplitStrategy.RANDOM, needs_labels=False)
def random_split(pairs: PairList, options: SplitOptions) -> SplitManifest:
    """纯随机划分:打乱后按比例切三段。

    labels_per_image 参数被忽略——随机策略不关心每张图有什么类别。
    """
    validate_rates(options.train_rate, options.val_rate)
    n_train, n_val, _ = three_way_counts(
        len(pairs), options.train_rate, options.val_rate
    )
    shuffled = seeded_shuffled(pairs, options.random_state)
    return SplitManifest(
        train=shuffled[:n_train],
        val=shuffled[n_train:n_train + n_val],
        test=shuffled[n_train + n_val:],
    )
