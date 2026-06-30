#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : init_project.py
# @Function  : 开发期入口 —— 无需 pip install 即可运行 init_project
"""init_project 开发期入口脚本。

用法：
    python scripts/init_project.py
"""
import sys
from pathlib import Path

# 将 apps/platform/src 注入 sys.path
_repo_root = Path(__file__).resolve().parent.parent
_src = _repo_root / "apps" / "platform" / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from od_platform.cli.init_project import initialize_project  # noqa: E402

if __name__ == "__main__":
    initialize_project()
