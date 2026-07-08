#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : validate_data.py
# @Function  : 开发期入口 — 无需 pip install 即可运行数据集验证
"""validate 开发期入口脚本。

用法:
    python scripts/validate_data.py --dataset demo_voc
    python scripts/validate_data.py --yaml apps/platform/configs/datasets/demo_voc.yaml
"""
import sys
from pathlib import Path

# 将 apps/platform/src 注入 sys.path
_repo_root = Path(__file__).resolve().parent.parent
_src = _repo_root / "apps" / "platform" / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from od_platform.cli.validate_data import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
