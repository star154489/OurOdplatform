"""split 策略注册表 —— 与 convert 的 registry 完全同构。

一张表(策略名→条目) + @register_strategy + 参数包 SplitOptions + 懒加载自动发现。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from od_platform.data_pipeline.split.manifest import PairList, SplitManifest

logger = logging.getLogger(__name__)


@dataclass
class SplitOptions:
    """划分策略共用的参数包。

    train_rate / val_rate: 决定三组大小。
    random_state:          随机种子(保证可复现)。
    labels_per_image:      {图路径: [类别名]} ——分层策略需要它,
                           随机策略不需要。None 表示未提供。
    """
    train_rate: float = 0.8
    val_rate: float = 0.1
    random_state: int = 1210
    labels_per_image: Optional[Dict[str, List[str]]] = field(default=None)


# 一个策略 = 吃 (PairList, SplitOptions) → SplitManifest
StrategyFunc = Callable[[PairList, SplitOptions], SplitManifest]


@dataclass(frozen=True)
class StrategyEntry:
    """注册表里一条记录:实现函数 + 它是否需要 labels_per_image。"""
    func: StrategyFunc
    requires_labels: bool = False


_STRATEGY_REGISTRY: Dict[str, StrategyEntry] = {}


def register_strategy(name: str, *, requires_labels: bool = False):
    """装饰器:把被装饰的函数登记进策略注册表。"""
    def decorator(func: StrategyFunc) -> StrategyFunc:
        if name in _STRATEGY_REGISTRY:
            logger.warning("策略 %s 被重复注册,后者覆盖前者", name)
        _STRATEGY_REGISTRY[name] = StrategyEntry(func=func, requires_labels=requires_labels)
        return func
    return decorator


def get_strategy(name: str) -> StrategyEntry:
    """按策略名取出条目。Raises: ValueError 未注册的策略。"""
    _lazy_init()
    if name not in _STRATEGY_REGISTRY:
        raise ValueError(f"未注册的策略: {name!r}。已注册: {sorted(_STRATEGY_REGISTRY)}")
    return _STRATEGY_REGISTRY[name]


def available_strategies() -> List[str]:
    """当前已注册的策略名。"""
    _lazy_init()
    return sorted(_STRATEGY_REGISTRY)


_LAZY_INITIALIZED = False


def _lazy_init() -> None:
    """懒加载:首次用表时扫描 strategies/ 目录。"""
    global _LAZY_INITIALIZED
    if _LAZY_INITIALIZED:
        return
    from od_platform.common.registry_utils import import_submodules
    from od_platform.data_pipeline.split import strategies
    import_submodules(strategies)
    _LAZY_INITIALIZED = True
