#!/usr/bin/env python
"""
ODPlatform 开发期路径诊断入口。
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_PATH = _REPO_ROOT / "apps" / "platform" / "src"
sys.path.insert(0, str(_SRC_PATH.resolve()))

from od_platform.cli.show_paths import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
