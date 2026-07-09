"""纯随机划分策略 —— 直接把 PairList 打乱后按比例切分。

不需要 labels_per_image,是"最简单、对稀有类可能不公平"的策略。
"""
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


@register_strategy(SplitStrategy.RANDOM, requires_labels=False)
def random_split(pairs: PairList, options: SplitOptions) -> SplitManifest:
    """纯随机:打乱后按比例切三份。"""
    total = len(pairs)
    if total == 0:
        return SplitManifest(
            train_rate=options.train_rate, val_rate=options.val_rate,
            test_rate=round(1.0 - options.train_rate - options.val_rate, 4),
        )

    validate_rates(options.train_rate, options.val_rate)
    n_train, n_val, n_test = three_way_counts(
        total, options.train_rate, options.val_rate,
    )
    shuffled = seeded_shuffled(pairs, options.random_state)

    return SplitManifest(
        train=shuffled[:n_train],
        val=shuffled[n_train:n_train + n_val],
        test=shuffled[n_train + n_val:],
        train_rate=options.train_rate,
        val_rate=options.val_rate,
        test_rate=round(1.0 - options.train_rate - options.val_rate, 4),
    )
