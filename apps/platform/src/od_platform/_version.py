"""ODPlatform 版本号 —— 单一数据源（Single Source of Truth）。

pyproject.toml 通过 ``[tool.setuptools.dynamic]`` 读取此文件，
确保 `od_platform.__version__` 与打包版本号始终一致。
"""

__version__ = "0.2.0"   # D4: 新增 data_validation 子系统
