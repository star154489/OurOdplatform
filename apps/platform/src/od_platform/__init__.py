"""ODPlatform 顶层包初始化。"""

from od_platform._version import __version__  # noqa: F401

# 将公共层核心符号提升到包顶层
from od_platform.common.paths import (
    ROOT_DIR,
    APP_DIR,
)
from od_platform.common.paths import get_dirs_to_initialize

__all__ = [
    "__version__",
    "ROOT_DIR",
    "APP_DIR",
    "get_dirs_to_initialize",
]
