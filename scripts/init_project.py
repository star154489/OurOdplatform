#!/usr/bin/env python
"""
ODPlatform 开发期项目初始化入口。

在 ``pip install`` 之前使用，通过 ``sys.path`` 临时注入使导入生效。
"""

import sys
from pathlib import Path

# 定位仓库根（本文件在 ODPlatform/scripts/init_project.py）
_REPO_ROOT = Path(__file__).resolve().parent.parent

# 将 platform 的 src/ 注入 sys.path 首位，使 import 能找到 od_platform
_SRC_PATH = _REPO_ROOT / "apps" / "platform" / "src"
sys.path.insert(0, str(_SRC_PATH.resolve()))

from od_platform.cli.init_project import initialize_project  # noqa: E402

if __name__ == "__main__":
    initialize_project()
