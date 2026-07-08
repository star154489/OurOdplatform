#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : __init__.py
# @Function  : checks 包 — pkgutil 自动 import,触发 @check 注册
"""加新 check = 在本目录加一个 .py 文件。不需要改这里,不需要改 registry,
不需要改 service —— import 即注册,这是开闭原则的物理基础。
"""
import importlib
import pkgutil

for _finder, _name, _ispkg in pkgutil.iter_modules(__path__):
    if not _name.startswith("_"):
        importlib.import_module(f"{__name__}.{_name}")
