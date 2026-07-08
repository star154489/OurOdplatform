#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : strategy_registry.py
# @Function  : 划分策略注册表 —— 一张表 + @register_strategy + SplitOptions
"""划分策略注册框架:让每种划分方式自己声明,调度层只查表。

和 convert 的 registry 完全对称:
  - convert 的注册表 = {格式名 → ConverterEntry(函数 + 支持的task)}
  - split 的注册表   = {策略名 → StrategyEntry(函数 + 能力标签)}
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from od_platform.data_pipeline.split.manifest import PairList, SplitManifest

logger = logging.getLogger(__name__)

# 划分策略需要知道的全部上下文,一个参数包传进去。
@dataclass
class SplitOptions:
    strategy: str
    train_rate: float
    val_rate: float
    random_state: int
    labels_per_image: Optional[Dict[str, List[str]]] = None  # 分层策略需要;随机会忽略它


# 一个划分函数 = 吃 (pairs, options) 返回 SplitManifest。
SplitFunc = Callable[[PairList, SplitOptions], SplitManifest]


@dataclass(frozen=True)
class StrategyEntry:
    func: SplitFunc
    needs_labels: bool = False          # 是否依赖 labels_per_image(分层=True,随机=False)


# 注册表本体
_REGISTRY: Dict[str, StrategyEntry] = {}


def register_strategy(strategy_name: str, *, needs_labels: bool = False):
    """装饰器:把划分函数登记进策略注册表。"""
    def decorator(func: SplitFunc) -> SplitFunc:
        if strategy_name in _REGISTRY:
            logger.warning("策略 %s 被重复注册,后者覆盖前者", strategy_name)
        _REGISTRY[strategy_name] = StrategyEntry(func=func, needs_labels=needs_labels)
        logger.debug("注册 split 策略: %s (needs_labels=%s)", strategy_name, needs_labels)
        return func
    return decorator


def get_strategy(strategy_name: str) -> StrategyEntry:
    _lazy_init()
    if strategy_name not in _REGISTRY:
        raise ValueError(f"未注册的划分策略: {strategy_name!r}。已注册: {sorted(_REGISTRY)}")
    return _REGISTRY[strategy_name]


def available_strategies() -> List[str]:
    _lazy_init()
    return sorted(_REGISTRY)


_LAZY_INITIALIZED = False


def _lazy_init() -> None:
    global _LAZY_INITIALIZED
    if _LAZY_INITIALIZED:
        return
    import importlib
    import pkgutil
    from od_platform.data_pipeline.split import strategies
    for m in pkgutil.iter_modules(strategies.__path__):
        if not m.name.startswith("_"):
            importlib.import_module(f"{strategies.__name__}.{m.name}")
    _LAZY_INITIALIZED = True
