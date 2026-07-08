"""ODPlatform — 打包入口。"""
from pathlib import Path

from setuptools import find_packages, setup

# 读版本
_src = Path("apps/platform/src/od_platform/_version.py")
_version = {}
exec(_src.read_text(encoding="utf-8"), _version)

setup(
    version=_version.get("__version__", "0.1.0"),
    packages=find_packages(where="apps/platform/src", include=["od_platform*"]),
    package_dir={"": "apps/platform/src"},
)
