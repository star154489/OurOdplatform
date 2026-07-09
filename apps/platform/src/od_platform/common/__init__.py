"""ODPlatform 通用工具层公共初始化。"""

# 路径工具 —— 整个项目最底层的模块,不依赖本包其他模块
from od_platform.common.paths import (
    ROOT_DIR as ROOT_DIR,
    APP_DIR as APP_DIR,
    DATA_DIR as DATA_DIR,
    RAW_DATA_DIR as RAW_DATA_DIR,
    MODELS_DIR as MODELS_DIR,
    PRETRAINED_MODELS_DIR as PRETRAINED_MODELS_DIR,
    TRAINED_MODELS_DIR as TRAINED_MODELS_DIR,
    RUNS_DIR as RUNS_DIR,
    PROCESSED_DATA_DIR as PROCESSED_DATA_DIR,
    CONFIGS_DIR as CONFIGS_DIR,
    DATASET_CONFIGS_DIR as DATASET_CONFIGS_DIR,
    LOGGING_DIR as LOGGING_DIR,
    UNIT_TEST_DIR as UNIT_TEST_DIR,
    DOCS_DIR as DOCS_DIR,
    SCRIPTS_DIR as SCRIPTS_DIR,
    META_DIR as META_DIR,
    META_LOGGING_DIR as META_LOGGING_DIR,
    get_dirs_to_reset as get_dirs_to_reset,
    get_dirs_to_initialize as get_dirs_to_initialize,
    get_runtime_backup_targets as get_runtime_backup_targets,
    get_project_core_backup_target_map as get_project_core_backup_target_map,
    get_project_core_backup_targets as get_project_core_backup_targets,
    is_protected as is_protected,
    dataset_processed_dir as dataset_processed_dir,
    dataset_yaml_path as dataset_yaml_path,
)

# 审计上下文
from od_platform.common.audit_utils import _audit_context as _audit_context
from od_platform.common.archive_utils import (
    build_archive_name as build_archive_name,
    create_zip_archive as create_zip_archive,
)

# 注册表工具
from od_platform.common.registry_utils import import_submodules as import_submodules

__all__ = [
    "ROOT_DIR",
    "APP_DIR",
    "DATA_DIR",
    "RAW_DATA_DIR",
    "MODELS_DIR",
    "PRETRAINED_MODELS_DIR",
    "TRAINED_MODELS_DIR",
    "RUNS_DIR",
    "PROCESSED_DATA_DIR",
    "CONFIGS_DIR",
    "DATASET_CONFIGS_DIR",
    "LOGGING_DIR",
    "UNIT_TEST_DIR",
    "DOCS_DIR",
    "SCRIPTS_DIR",
    "META_DIR",
    "META_LOGGING_DIR",
    "get_dirs_to_initialize",
    "get_dirs_to_reset",
    "get_runtime_backup_targets",
    "get_project_core_backup_target_map",
    "get_project_core_backup_targets",
    "is_protected",
    "dataset_processed_dir",
    "dataset_yaml_path",
    "_audit_context",
    "build_archive_name",
    "create_zip_archive",
    "import_submodules",
]
