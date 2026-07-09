"""主类别分层划分策略 —— 按每张图的主类别分组，组内按比例切分。

对比 random：
    random 全局打乱直接切 → 稀有类可能整个消失在 val/test 里。
    stratified 保证每个类别都会按比例出现在三组中，稀有类不至于"灭绝"。

主类别的定义：每张图中出现次数最多的那个类别(tie 取第一个遇到的)。
无标注的图 → 归入"无标签组"，随机分配。
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Dict, List

from od_platform.common.constants import SplitStrategy
from od_platform.data_pipeline.split.manifest import Pair, PairList, SplitManifest
from od_platform.data_pipeline.split.strategies.common import (
    seeded_shuffled,
    three_way_counts,
    validate_rates,
)
from od_platform.data_pipeline.split.strategy_registry import (
    SplitOptions,
    register_strategy,
)

logger = logging.getLogger(__name__)


@register_strategy(SplitStrategy.STRATIFIED, requires_labels=True)
def stratified_split(pairs: PairList, options: SplitOptions) -> SplitManifest:
    """按主类别分层:每类内打乱 → 按比例切 → 合并各组对应部分。

    需要 labels_per_image;如果调用方没传,回退到纯随机。
    """
    total = len(pairs)
    if total == 0:
        return SplitManifest(
            train_rate=options.train_rate, val_rate=options.val_rate,
            test_rate=round(1.0 - options.train_rate - options.val_rate, 4),
        )

    validate_rates(options.train_rate, options.val_rate)
    test_rate = round(1.0 - options.train_rate - options.val_rate, 4)

    labels_per_image = options.labels_per_image

    # — 回退:没有 labels 信息时按纯随机处理 —
    if not labels_per_image:
        logger.warning(
            "stratified 策略需要 labels_per_image 但未提供,回退到纯随机划分"
        )
        shuffled = seeded_shuffled(pairs, options.random_state)
        n_train, n_val, n_test = three_way_counts(total, options.train_rate, options.val_rate)
        return SplitManifest(
            train=shuffled[:n_train],
            val=shuffled[n_train:n_train + n_val],
            test=shuffled[n_train + n_val:],
            train_rate=options.train_rate,
            val_rate=options.val_rate,
            test_rate=test_rate,
        )

    # — 1. 按主类别分组 —
    # 主类别 = 该图中出现次数最多的类别名
    groups: Dict[str, PairList] = defaultdict(list)
    unlabeled: PairList = []

    for img_path, lbl_path in pairs:
        stem = img_path.stem
        class_names = labels_per_image.get(stem, [])
        if not class_names:
            unlabeled.append((img_path, lbl_path))
        else:
            # 取出现次数最多的类别;tie 时取第一个
            primary = Counter(class_names).most_common(1)[0][0]
            groups[primary].append((img_path, lbl_path))

    class_names = sorted(groups.keys())
    logger.info(
        "分层划分: %d 个类别组 + %d 张无标签图 (总 %d 张)",
        len(class_names), len(unlabeled), total,
    )
    if len(class_names) <= 1:
        logger.info("只有 %d 个类别组,分层效果等同于随机", len(class_names))

    # — 2. 每组内按种子打乱 → 按比例切 —
    train: PairList = []
    val: PairList = []
    test: PairList = []

    for cls_name in class_names:
        group = groups[cls_name]
        shuffled = seeded_shuffled(group, options.random_state)
        n = len(group)
        n_train, n_val, n_test = three_way_counts(n, options.train_rate, options.val_rate)
        train.extend(shuffled[:n_train])
        val.extend(shuffled[n_train:n_train + n_val])
        test.extend(shuffled[n_train + n_val:])

    # — 3. 无标签组随机分配 —
    if unlabeled:
        shuffled_ul = seeded_shuffled(unlabeled, options.random_state)
        n = len(unlabeled)
        n_train, n_val, n_test = three_way_counts(n, options.train_rate, options.val_rate)
        train.extend(shuffled_ul[:n_train])
        val.extend(shuffled_ul[n_train:n_train + n_val])
        test.extend(shuffled_ul[n_train + n_val:])

    # — 4. 最终打乱各组内部顺序(不同组的样本混合均匀) —
    train = seeded_shuffled(train, options.random_state + 1)
    val = seeded_shuffled(val, options.random_state + 2)
    test = seeded_shuffled(test, options.random_state + 3)

    logger.info(
        "分层结果: train=%d, val=%d, test=%d (期望 %.0f%%/%.0f%%/%.0f%%)",
        len(train), len(val), len(test),
        options.train_rate * 100, options.val_rate * 100, test_rate * 100,
    )

    return SplitManifest(
        train=train,
        val=val,
        test=test,
        train_rate=options.train_rate,
        val_rate=options.val_rate,
        test_rate=test_rate,
    )
