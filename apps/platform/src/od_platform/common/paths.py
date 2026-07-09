#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :paths.py
# @Time      :2026/6/29 13:39:33
# @Author    :雨霓同学
# @Project   :ODPlatform
# @Function  :定义所有的路径变量信息，方便其他模块调用

from pathlib import Path
from typing import List, Tuple

# 找到 Workspace 根目录
WORKSPACE_MARKER: str = ".odp-workspace"


def _find_workspace_root(
    start: Path,
    markers: Tuple[str, ...] = (WORKSPACE_MARKER,),
) -> Path:
    current = start.resolve()
    if current.is_file():
        current = current.parent

    for parent in [current, *current.parents]:
        for marker in markers:
            if (parent / marker).exists():
                return parent

    raise FileNotFoundError(
        f"找不到 workspace marker 文件 ({markers})，"
        f"请确认仓库根目录已存在 {WORKSPACE_MARKER} 文件"
    )


# 计算 ROOT_DIR 位置
# 策略: 先尝试从 __file__ 找 (editable install / 开发期),
# 失败则从当前工作目录 cwd 找 (wheel 安装, 此时 __file__ 在 site-packages 里,
# 项目文件不在那里, 只能靠用户从项目根执行命令)。
try:
    ROOT_DIR: Path = _find_workspace_root(Path(__file__))
except FileNotFoundError:
    ROOT_DIR = _find_workspace_root(Path.cwd())

# 端的根目录 APP_DIR
APP_DIR: Path = ROOT_DIR / "apps" / "platform"

# 共享资产
DATA_DIR: Path = ROOT_DIR / "data"
MODELS_DIR: Path = ROOT_DIR / "models"
RUNS_DIR: Path = ROOT_DIR / "runs"

# 模型的子目录
PRETRAINED_MODELS_DIR: Path = MODELS_DIR / "pretrained"  # 存放预训练模型
TRAINED_MODELS_DIR: Path = MODELS_DIR / "trained"        # 训练好的归档模型

# 数据集的子目录
RAW_DATA_DIR: Path = DATA_DIR / "raw"                    # 用户原始数据
PROCESSED_DATA_DIR: Path = DATA_DIR / "processed"        # train/val/test 派生数据

# 端私有资产
CONFIGS_DIR: Path = APP_DIR / "configs"
DATASET_CONFIGS_DIR: Path = CONFIGS_DIR / "datasets"
LOGGING_DIR: Path = APP_DIR / "logging"
UNIT_TEST_DIR: Path = APP_DIR / "tests"

# 顶层的文档目录
DOCS_DIR: Path = ROOT_DIR / "docs"

# 工程基础设置目录共享的
SCRIPTS_DIR: Path = ROOT_DIR / "scripts"

# 元工具数据目录 / 工具自身的一些日志
META_DIR: Path = ROOT_DIR / ".odp-meta"
META_LOGGING_DIR: Path = META_DIR / "logging"

# ============================================================
# D4 增量: 数据验证运行目录
# ============================================================
VALIDATION_RUNS_DIR: Path = RUNS_DIR / "data_validation"


def validation_run_dir(run_id: str) -> Path:
    """单次验证运行的产出目录: runs/data_validation/<run_id>/。"""
    return VALIDATION_RUNS_DIR / run_id


# ============================================================
# D5 增量: 运行配置目录
#   DATASET_CONFIGS_DIR: 描述【数据】的 yaml (odp-transform 产出)
#   RUNTIME_CONFIGS_DIR : 描述【跑法】的 yaml (runtime_config 子系统产出)
# ============================================================
RUNTIME_CONFIGS_DIR: Path = CONFIGS_DIR / "runtime"


def runtime_config_path(name: str) -> Path:
    """返回某个运行配置文件的路径: <CONFIGS_DIR>/runtime/<name>.yaml。"""
    return RUNTIME_CONFIGS_DIR / f"{name}.yaml"


def get_dirs_to_initialize() -> List[Path]:
    """返回 init_project 需要创建的目录列表。"""
    return [
        DATA_DIR,
        MODELS_DIR,
        RUNS_DIR,
        PRETRAINED_MODELS_DIR,
        TRAINED_MODELS_DIR,
        RAW_DATA_DIR,
        PROCESSED_DATA_DIR,
        CONFIGS_DIR,
        LOGGING_DIR,
        UNIT_TEST_DIR,
        DOCS_DIR,
        SCRIPTS_DIR,
        META_DIR,
        META_LOGGING_DIR,
        DATASET_CONFIGS_DIR,
        RUNTIME_CONFIGS_DIR,
    ]


def get_dirs_to_reset() -> List[Path]:
    """返回 reset_project 可以安全清理的目录列表。"""
    return [
        PROCESSED_DATA_DIR,
        RUNS_DIR,
        LOGGING_DIR,
        CONFIGS_DIR,
        TRAINED_MODELS_DIR,
    ]


def get_runtime_backup_targets() -> List[Path]:
    """返回 reset 时可选打包的运行产物目录列表。"""
    return list(get_dirs_to_reset())


def get_project_core_backup_targets() -> List[Path]:
    """返回项目核心文件/目录的备份清单。"""
    return [
        APP_DIR / "src",
        DOCS_DIR,
        SCRIPTS_DIR,
        ROOT_DIR / "pyproject.toml",
        APP_DIR / "pyproject.toml",
        ROOT_DIR / "setup.py",
        ROOT_DIR / "ODPlatform说明.md",
    ]


# 绝对保护目录：reset 工具永远不能删除这些内容
PROTECTED_DIRS: tuple[Path, ...] = (
    ROOT_DIR,
    SCRIPTS_DIR,
    DOCS_DIR,
    UNIT_TEST_DIR,
    ROOT_DIR / ".git",
    ROOT_DIR / WORKSPACE_MARKER,
    RAW_DATA_DIR,
    PRETRAINED_MODELS_DIR,
    APP_DIR / "src",
    META_DIR,
    META_LOGGING_DIR,
)


def _is_relative_to(path: Path, other: Path) -> bool:
    try:
        return path.is_relative_to(other)
    except AttributeError:
        try:
            path.relative_to(other)
            return True
        except ValueError:
            return False


def is_protected(path: Path) -> bool:
    """
    路径是否受保护，即 reset 工具是否可以删除该路径。

    1. 路径本身在 PROTECTED_DIRS 中
    2. 路径位于受保护目录内部
    """
    path = path.resolve(strict=False)
    for protected in PROTECTED_DIRS:
        protected_resolve = protected.resolve(strict=False)
        if path == protected_resolve:
            return True
        if protected_resolve == ROOT_DIR:
            continue
        if _is_relative_to(path, protected_resolve):
            return True
    return False


def dataset_processed_dir(name: str) -> Path:
    """某数据集的派生根: data/processed/<name>/。"""
    return PROCESSED_DATA_DIR / name


def dataset_yaml_path(name: str) -> Path:
    """某数据集生成的 ultralytics yaml 路径: configs/datasets/<name>.yaml。"""
    return DATASET_CONFIGS_DIR / f"{name}.yaml"


if __name__ == "__main__":
    print(f"ROOT DIR (workspace) = {ROOT_DIR}")
    print(f"APP DIR = {APP_DIR}")
    print(f"DATA DIR = {DATA_DIR}")
    print(f"MODELS DIR = {MODELS_DIR}")
    print(f"RUNS DIR = {RUNS_DIR}")
    print(f"PRETRAINED MODELS DIR = {PRETRAINED_MODELS_DIR}")
    print(f"TRAINED MODELS DIR = {TRAINED_MODELS_DIR}")
    print(f"RAW DATA DIR = {RAW_DATA_DIR}")
    print(f"PROCESSED DATA DIR = {PROCESSED_DATA_DIR}")
    print(f"CONFIGS DIR = {CONFIGS_DIR}")
    print(f"LOGGING DIR = {LOGGING_DIR}")
    print(f"UNIT TEST DIR = {UNIT_TEST_DIR}")
    for d in get_dirs_to_initialize():
        print(f"将要初始化的目录有: {d.relative_to(ROOT_DIR)}")




