"""划分调度层 —— 按策略名分发到具体策略实现。

与 convert/service.py 同构:查表 → 校验 → 分发。
"""
from __future__ import annotations

from od_platform.data_pipeline.split.manifest import PairList, SplitManifest
from od_platform.data_pipeline.split.strategy_registry import (
    SplitOptions,
    get_strategy,
)


def split_pairs(
    pairs: PairList,
    strategy: str,
    options: SplitOptions,
) -> SplitManifest:
    """统一入口:按 strategy 分发到具体划分策略。

    Args:
        pairs:   待划分的(图,标)配对列表。
        strategy: 策略名(如 "random"/"stratified")。
        options:  参数包。

    Raises:
        ValueError: 策略未注册。

    Returns:
        划分结果 SplitManifest。
    """
    entry = get_strategy(strategy)
    return entry.func(pairs, options)
