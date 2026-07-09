"""注册表工具 —— 供各子系统的插件式注册表共用。

本模块是"注册表与装饰器扩展"的公共底座, 提供两件事:

  1. import_submodules(): 扫描包目录、逐个 import 子模块, 触发它们头顶的
     @register / @check 装饰器副作用(懒加载自动发现)。
     convert / split / data_validation 三张注册表共用它, 所以抽到 common 层。

  2. handle_duplicate_registration(): 统一"重复注册"处理, 让三张表的
     @register / @check 装饰器风格一致(同一段代码、同样的日志措辞),
     各表只用 policy 选择自己的语义, 不再各写各的 if。

第一次抽象发生在"第二个消费者出现时"(split 系统), 符合"第二次才抽象"原则。
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from types import ModuleType
from typing import List, Optional

_logger = logging.getLogger(__name__)


def import_submodules(
    package: ModuleType,
    *,
    recursive: bool = True,
    on_error: str = "raise",
    logger: Optional[logging.Logger] = None,
) -> List[str]:
    """扫描 package 目录, import 所有非 _ 开头的子模块(可递归子包)。

    典型用法:
        from my_package import sub_package
        import_submodules(sub_package)
        # 此时 sub_package 下每个 .py 文件的顶层代码都被执行了,
        # 包括它们头顶的 @register("name") 装饰器, 于是注册表里有了条目。

    Args:
        package:   已 import 的包模块(必须有 __path__ 属性)。
        recursive: True 时递归进入子包(默认)。现有各注册表目录暂无嵌套子包,
                   开启不改变其行为, 只为将来分层目录(如 converters/voc/*.py)留路。
        on_error:  单个子模块 import 失败时的策略:
                     "raise" —— 原样抛出(默认, 与历史行为一致, 让坏模块立即可见)。
                     "warn"  —— 记 warning 后跳过, 继续扫描其余模块
                                (一个坏模块不拖垮整张表的自动发现)。
        logger:    记日志用的 logger(默认本模块 logger)。

    Returns:
        本次成功 import 的子模块全名列表(按发现顺序; 含递归进入的子模块)。
        调用方可据此知道"到底扫进来了哪些、几个", 也便于测试断言。

    Raises:
        Exception: on_error="raise" 时, 透传子模块 import 期间的任意异常。
    """
    log = logger or _logger
    imported: List[str] = []

    for m in pkgutil.iter_modules(package.__path__):
        if m.name.startswith("_"):
            continue
        full_name = f"{package.__name__}.{m.name}"
        try:
            submodule = importlib.import_module(full_name)
        except Exception:
            if on_error == "warn":
                log.warning("import_submodules: 跳过导入失败的模块 %s", full_name, exc_info=True)
                continue
            raise
        imported.append(full_name)
        log.debug("import_submodules: 已导入 %s", full_name)

        if recursive and m.ispkg:
            imported.extend(
                import_submodules(
                    submodule, recursive=True, on_error=on_error, logger=log
                )
            )

    return imported


def handle_duplicate_registration(
    key: str,
    *,
    already_exists: bool,
    label: str = "条目",
    policy: str = "error",
    where: str = "",
    logger: Optional[logging.Logger] = None,
) -> bool:
    """统一处理"重复注册"—— 供各注册表的 @register / @check 装饰器共用。

    把三张表原本各自手写的 "if key in registry: warn/raise" 收敛到一处,
    让重复策略的代码与日志措辞一致; 各表只用 policy 表达自己的语义,
    行为与原来完全等价(纯风格统一, 不改运行结果)。

    Args:
        key:            要注册的名字。
        already_exists: 该名字是否已在表里(由调用方判断后传入)。
        label:          日志/报错里的中文类别名, 如 "格式" / "策略" / "check"。
        policy:         重复注册的语义:
                          "error"  —— 抛 ValueError(重复=bug, 立即可见);
                          "warn"   —— 记 warning 后允许覆盖;
                          "ignore" —— 静默允许覆盖。
        where:          第二次注册发生的位置(如 "module.func"), 仅用于报错/日志。
        logger:         记日志用的 logger(默认本模块 logger)。

    Returns:
        是否应写入注册表(True=写入/覆盖; 只有极端自定义 policy 才会返回 False)。

    Raises:
        ValueError: policy="error" 且 already_exists=True。
    """
    if not already_exists:
        return True

    log = logger or _logger
    loc = f" — 第二次出现在 {where}" if where else ""

    if policy == "error":
        raise ValueError(f"{label} '{key}' 重复注册{loc}")
    if policy == "warn":
        log.warning("%s '%s' 被重复注册, 后者覆盖前者%s", label, key, loc)
    # "warn" / "ignore" 都放行覆盖
    return True
