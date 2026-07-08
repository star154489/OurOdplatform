#!/usr/bin/env python
"""
ODPlatform 开发期数据转换入口。

在 ``pip install`` 之前使用,通过 ``sys.path`` 临时注入使导入生效。
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_PATH = _REPO_ROOT / "apps" / "platform" / "src"
sys.path.insert(0, str(_SRC_PATH.resolve()))

from od_platform.cli.transform_data import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
