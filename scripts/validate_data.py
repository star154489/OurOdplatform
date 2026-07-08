#!/usr/bin/env python
"""开发期快捷入口: python scripts/validate_data.py — 直接调 CLI 主入口。"""

import sys
from od_platform.cli.validate_data import main

if __name__ == "__main__":
    sys.exit(main())
