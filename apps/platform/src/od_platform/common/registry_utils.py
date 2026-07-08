"""注册表工具 —— import_submodules:扫描包目录,主动 import 每个模块触发 @register。

convert 和 split 两张注册表共用同一套懒加载逻辑,所以抽到 common 层。
第一次抽象发生在"第二个消费者出现时"(split 系统),符合"第二次才抽象"原则。
"""
from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType


def import_submodules(package: ModuleType) -> None:
    """扫描 package 所在目录,import 所有非 _ 开头的子模块。

    典型用法:
        from my_package import sub_package
        import_submodules(sub_package)
        # 此时 sub_package 下每个 .py 文件的顶层代码都被执行了,
        # 包括它们头顶的 @register("name") 装饰器,于是注册表里有了条目。

    Args:
        package: 已 import 的包模块(必须有 __path__ 属性)。
    """
    for m in pkgutil.iter_modules(package.__path__):
        if not m.name.startswith("_"):
            importlib.import_module(f"{package.__name__}.{m.name}")
