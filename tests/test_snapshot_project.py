"""项目快照 CLI 测试。"""
from __future__ import annotations

import logging
import sys
import zipfile
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "apps" / "platform" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def test_snapshot_project_creates_core_archive(tmp_path, monkeypatch):
    from od_platform.cli import snapshot_project as sp

    repo_root = tmp_path / "repo"
    src_dir = repo_root / "apps" / "platform" / "src"
    docs_dir = repo_root / "docs"
    scripts_dir = repo_root / "scripts"
    pyproject_path = repo_root / "pyproject.toml"

    (src_dir / "od_platform").mkdir(parents=True)
    (src_dir / "od_platform" / "__init__.py").write_text("__all__ = []", encoding="utf-8")
    docs_dir.mkdir(parents=True)
    (docs_dir / "intro.md").write_text("# docs", encoding="utf-8")
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "reset_project.py").write_text("print('ok')", encoding="utf-8")
    pyproject_path.write_text("[build-system]\nrequires = []\n", encoding="utf-8")

    monkeypatch.setattr(sp, "ROOT_DIR", repo_root)
    monkeypatch.setattr(sp, "META_DIR", repo_root / ".odp-meta")
    monkeypatch.setattr(sp, "BACKUP_DIR", repo_root / ".odp-meta" / "backups")
    monkeypatch.setattr(sp, "get_project_core_backup_targets", lambda: [src_dir, docs_dir, scripts_dir, pyproject_path])

    logger = logging.getLogger("od_platform.test.snapshot_project")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    monkeypatch.setattr(sp, "get_logger", lambda *args, **kwargs: logger)

    code = sp.snapshot_project()

    assert code == 0
    archives = list((repo_root / ".odp-meta" / "backups").glob("project-core-backup-*.zip"))
    assert len(archives) == 1

    with zipfile.ZipFile(archives[0]) as zf:
        names = set(zf.namelist())
        assert "apps/platform/src/od_platform/__init__.py" in names
        assert "docs/intro.md" in names
        assert "scripts/reset_project.py" in names
        assert "pyproject.toml" in names


def test_snapshot_project_returns_error_when_archive_fails(monkeypatch, tmp_path):
    from od_platform.cli import snapshot_project as sp

    repo_root = tmp_path / "repo"
    monkeypatch.setattr(sp, "ROOT_DIR", repo_root)
    monkeypatch.setattr(sp, "get_project_core_backup_targets", lambda: [repo_root / "scripts"])

    logger = logging.getLogger("od_platform.test.snapshot_project_fail")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    monkeypatch.setattr(sp, "get_logger", lambda *args, **kwargs: logger)
    monkeypatch.setattr(sp, "create_zip_archive", lambda *args, **kwargs: None)

    code = sp.snapshot_project()

    assert code == 2
