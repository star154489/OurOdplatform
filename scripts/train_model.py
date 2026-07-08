#!/usr/bin/env python
"""ODPlatform 开发期训练入口。"""
import sys
from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_PATH = _REPO_ROOT / "apps" / "platform" / "src"
sys.path.insert(0, str(_SRC_PATH.resolve()))
from od_platform.cli.train_model import main
if __name__ == "__main__":
    sys.exit(main())
