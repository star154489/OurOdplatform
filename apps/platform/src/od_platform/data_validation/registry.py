#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : registry.py
# @Function  : data_validation 注册表 + 数据契约
"""data_validation 注册表 + 数据契约 (CheckResult / CheckSeverity / CheckContext)。

跟 D3 的 data_pipeline/registry.py 是【同一模式的两种用法】:
    - D3: 互斥分发 (一次调用一个 converter)
    - D4: 聚合执行 (一次调用全部 check, 收集结果)

公开 API:
    @check(name)                 装饰器, 自动注册一个 check 函数
    CheckResult                  统一返回类型
    CheckSeverity                严重程度 (四级 + rank)
    CheckContext                 check 函数的入参合同 (yaml_path + snapshot + options)
    ValidationOptions            运行级开关 (frozen, 全默认值)
    get_all_checks()             返回全部注册的 check (供 service 调度)
    get_check(name)              按名查询单个 check (供测试)
    list_check_names()           返回注册的 check 名列表
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


# ============================================================
# 1. CheckSeverity — 严重程度 (四级一次到位 + rank)
# ============================================================

class CheckSeverity:
    """Check 结果的严重程度。

    跨级关系 (供 ValidationReport.overall_severity 比较):
        ERROR > WARNING > INFO > PASS

    四级而不是两级 (passed: bool) 的理由 — 见 D4 撞墙①。
    """
    ERROR   = "ERROR"     # 阻塞级 (CI 必须停, 训练绝不能继续)
    WARNING = "WARNING"   # 关注级 (能继续, 但需要人工 review)
    INFO    = "INFO"      # 告知级 (知道一下, 不阻断)
    PASS    = "PASS"      # 通过

    _ORDER = {"PASS": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}

    @classmethod
    def rank(cls, level: str) -> int:
        """供聚合层比较 severity 用 — ERROR.rank() > PASS.rank()。"""
        return cls._ORDER.get(level, 0)


# ============================================================
# 2. CheckResult — 单个 check 的统一返回类型
# ============================================================

@dataclass
class CheckResult:
    """单个 check 的完整产出。

    Args:
        name:     check 名 (= 注册时的字符串)
        severity: ERROR / WARNING / INFO / PASS
        summary:  一句话总结, 供终端日志 / 报告头部使用
        details:  结构化详情字典 (给机器 — JSON 报告 / 监控趋势)
    """
    name:     str
    severity: str
    summary:  str
    details:  Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """PASS / INFO 都算通过 — INFO 的语义是"知道一下但不阻断"。"""
        return self.severity in (CheckSeverity.PASS, CheckSeverity.INFO)


# ============================================================
# 3. ValidationOptions — 一次验证运行的开关集合
# ============================================================

@dataclass(frozen=True)
class ValidationOptions:
    """验证运行级开关 — 经由 CheckContext.options 下发给所有 check / profiler。

    设计:
        - frozen: 运行中不可变, 杜绝某个 check 偷偷改开关影响后续 check
        - 全部带默认值: 老调用方行为零变化 — 向后兼容
        - 这里只放"行为开关", 阈值仍在 constants.py

    Args:
        check_images:       True 时 image_integrity 逐张解码验证 (重型, 默认关)
        profile:            True 时生成实例画像 + instances.csv (轻型, 默认开)
        read_image_headers: True 时 profiler 读图像头取分辨率 (单图 <1ms)
        top_n_anomalies:    画像层异常锚点清单长度
    """
    check_images:       bool = False
    profile:            bool = True
    read_image_headers: bool = True
    top_n_anomalies:    int  = 20


# ============================================================
# 4. CheckContext — check 函数的入参合同 (extension point)
# ============================================================

@dataclass
class CheckContext:
    """Check 函数的入参 — 所有 check 函数签名: (ctx: CheckContext) -> CheckResult。

    资源随便加, 签名永不动 — 这是 CheckContext 这层包装的全部意义。

    Args:
        yaml_path: 数据集 yaml 文件路径
        snapshot:  DatasetSnapshot — 一次扫描产物, 供所有 check 共享消费
        options:   ValidationOptions — 运行级开关 (带默认值保持兼容)
    """
    yaml_path: Path
    snapshot: "DatasetSnapshot"          # type: ignore — 延迟引用, 避免循环导入
    options: ValidationOptions = field(default_factory=ValidationOptions)


# ============================================================
# 5. 注册表条目
# ============================================================

@dataclass(frozen=True)
class CheckEntry:
    """注册表里的一条记录。frozen — 注册后不可改, 一锤子买卖。"""
    name: str
    func: Callable[[CheckContext], CheckResult]


# ============================================================
# 6. 模块级注册表 + @check 装饰器
# ============================================================

_REGISTRY: Dict[str, CheckEntry] = {}
_LAZY_INITIALIZED: bool = False


def check(name: str) -> Callable:
    """注册一个 check 函数到全局注册表。

    用法:
        @check("yaml_schema")
        def validate_yaml_schema(ctx: CheckContext) -> CheckResult: ...

    设计:
        - 装饰器不包装函数 — 直接 return func。
        - 重复注册立刻报 ValueError, 不是覆盖。
    """
    def decorator(func: Callable[[CheckContext], CheckResult]) -> Callable[[CheckContext], CheckResult]:
        if name in _REGISTRY:
            raise ValueError(
                f"check '{name}' 重复注册 — 第二次出现在 {func.__module__}.{func.__name__}"
            )
        _REGISTRY[name] = CheckEntry(name=name, func=func)
        logger.debug("注册 check: %s", name)
        return func
    return decorator


# ============================================================
# 7. 自动 import
# ============================================================

def _lazy_init() -> None:
    global _LAZY_INITIALIZED
    if _LAZY_INITIALIZED:
        return
    import importlib
    import pkgutil
    checks_pkg = importlib.import_module("od_platform.data_validation.checks")
    for m in pkgutil.iter_modules(checks_pkg.__path__):
        if not m.name.startswith("_"):
            importlib.import_module(f"od_platform.data_validation.checks.{m.name}")
    _LAZY_INITIALIZED = True


# ============================================================
# 8. 查询 API
# ============================================================

def get_all_checks() -> List[CheckEntry]:
    _lazy_init()
    return list(_REGISTRY.values())


def get_check(name: str) -> CheckEntry:
    _lazy_init()
    if name not in _REGISTRY:
        raise KeyError(f"check '{name}' 未注册 — 已注册的: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def list_check_names() -> List[str]:
    _lazy_init()
    return sorted(_REGISTRY)
