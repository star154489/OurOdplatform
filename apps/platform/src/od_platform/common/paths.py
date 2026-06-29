#!/usr/bin/env python
# -*- coding: utf-8 -*-
from pathlib import Path
from typing import List, Tuple

# 找到Workspace根目录
WORKSPACE_MARKER: str = ".odp-workspace"


def _find_workspace_root(
    start: Path,
    markers: Tuple[str, ...] = (WORKSPACE_MARKER,),
) -> Path:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for parent in [current, *current.parents]:
        for marker in markers:
            if (parent / marker).exists():
                return parent
    raise FileNotFoundError(
        f"找不到workspace marker文件({markers}) "
        f"请确认仓库根目录已存在{WORKSPACE_MARKER}文件"
    )


# 计算ROOT_DIR位置
ROOT_DIR: Path = _find_workspace_root(Path(__file__))

# 日志目录
LOGGING_DIR: Path = ROOT_DIR / "apps" / "platform" / "logging"


def get_dirs_to_initialize() -> List[Path]:
    """返回需要初始化的所有目录"""
    return [
        ROOT_DIR / "data",
        ROOT_DIR / "data" / "raw",
        ROOT_DIR / "data" / "processed",
        ROOT_DIR / "models",
        ROOT_DIR / "models" / "pretrained",
        ROOT_DIR / "models" / "trained",
        ROOT_DIR / "runs",
        ROOT_DIR / "apps" / "platform" / "configs",
        ROOT_DIR / "apps" / "platform" / "logging",
        ROOT_DIR / "apps" / "platform" / "tests",
        ROOT_DIR / "docs",
        ROOT_DIR / "scripts",
    ]
