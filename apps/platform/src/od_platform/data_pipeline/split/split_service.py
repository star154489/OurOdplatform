#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : split_service.py
# @Function  : 划分调度层 —— 几行代码接住所有划分策略(永不增长)
"""按策略名分发到具体划分函数。加了新策略,本文件一行都不改。"""
from __future__ import annotations

from typing import Dict, List, Optional

from od_platform.data_pipeline.split.manifest import PairList, SplitManifest
from od_platform.data_pipeline.split.strategy_registry import (
    SplitOptions,
    get_strategy,
)


def split_pairs(
    pairs: PairList,
    train_rate: float = 0.8,
    val_rate: float = 0.1,
    random_state: int = 1210,
    strategy: str = "random",
    labels_per_image: Optional[Dict[str, List[str]]] = None,
) -> SplitManifest:
    """统一入口:按 strategy 名称分发到具体划分函数。

    Args:
        pairs: (图, 标) 对列表。
        train_rate / val_rate: 训练/验证比例,余数为 test。
        random_state: 随机种子,保证划分可复现。
        strategy: 策略名(random / stratified / ...)。
        labels_per_image: {图stem: [类名, ...]},分层策略需要;随机会忽略。

    Returns:
        SplitManifest: 三组 (train/val/test) 的 PairList。
    """
    entry = get_strategy(strategy)
    opts = SplitOptions(
        strategy=strategy,
        train_rate=train_rate,
        val_rate=val_rate,
        random_state=random_state,
        labels_per_image=labels_per_image,
    )
    return entry.func(pairs, opts)
