"""ODPlatform 统一测试入口 & 工程基础测试。"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "apps" / "platform" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ---------- paths.py ----------

def test_workspace_root():
    from od_platform.common.paths import ROOT_DIR
    assert ROOT_DIR.exists()
    assert (ROOT_DIR / ".odp-workspace").exists()


def test_app_dir():
    from od_platform.common.paths import APP_DIR
    assert APP_DIR.exists()
    assert "apps" in APP_DIR.parts


def test_key_paths():
    from od_platform.common.paths import (
        DATA_DIR, MODELS_DIR, RUNS_DIR, RAW_DATA_DIR,
        CONFIGS_DIR, LOGGING_DIR, DATASET_CONFIGS_DIR,
        RUNTIME_CONFIGS_DIR, VALIDATION_RUNS_DIR,
    )
    for p in [DATA_DIR, MODELS_DIR, RUNS_DIR, RAW_DATA_DIR,
              CONFIGS_DIR, DATASET_CONFIGS_DIR, RUNTIME_CONFIGS_DIR]:
        assert isinstance(p, Path)


def test_get_dirs_to_initialize():
    from od_platform.common.paths import get_dirs_to_initialize, RUNTIME_CONFIGS_DIR
    dirs = get_dirs_to_initialize()
    assert RUNTIME_CONFIGS_DIR in dirs


def test_get_dirs_to_reset():
    from od_platform.common.paths import get_dirs_to_reset
    assert len(get_dirs_to_reset()) >= 4


def test_dataset_processed_dir():
    from od_platform.common.paths import dataset_processed_dir, PROCESSED_DATA_DIR
    assert dataset_processed_dir("demo") == PROCESSED_DATA_DIR / "demo"


def test_runtime_config_path():
    from od_platform.common.paths import runtime_config_path, RUNTIME_CONFIGS_DIR
    assert runtime_config_path("train") == RUNTIME_CONFIGS_DIR / "train.yaml"


# ---------- is_protected (匹配用户当前 paths.py 的实现) ----------

class TestIsProtected:
    def setup_method(self):
        from od_platform.common.paths import ROOT_DIR
        self.ROOT = ROOT_DIR

    def test_git_is_protected(self):
        from od_platform.common.paths import is_protected
        assert is_protected(self.ROOT / ".git") is True

    def test_git_subpath_is_protected(self):
        from od_platform.common.paths import is_protected
        assert is_protected(self.ROOT / ".git" / "objects") is True

    def test_raw_data_subpath_is_protected(self):
        from od_platform.common.paths import is_protected
        assert is_protected(self.ROOT / "data" / "raw" / "something") is True

    def test_runs_is_not_protected(self):
        from od_platform.common.paths import is_protected
        assert is_protected(self.ROOT / "runs") is False

    def test_meta_logging_is_protected(self):
        from od_platform.common.paths import is_protected
        from od_platform.common.paths import META_LOGGING_DIR
        assert is_protected(META_LOGGING_DIR) is True

    def test_empty_list(self):
        from od_platform.common.paths import get_dirs_to_reset, is_protected
        for d in get_dirs_to_reset():
            assert is_protected(d) is False, f"{d} should not be protected"

    def test_reset_targets_do_not_enclose_protected_dirs(self):
        from od_platform.common.paths import PROTECTED_DIRS, get_dirs_to_reset

        for reset_dir in get_dirs_to_reset():
            for protected_dir in PROTECTED_DIRS:
                assert not protected_dir.resolve(strict=False).is_relative_to(
                    reset_dir.resolve(strict=False)
                ), f"{reset_dir} should not enclose protected dir {protected_dir}"
