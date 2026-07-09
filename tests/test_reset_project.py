"""D2 reset_project 备份逻辑测试。"""
from __future__ import annotations

import logging
import sys
import zipfile
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "apps" / "platform" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def test_create_backup_archive(tmp_path, monkeypatch):
    from od_platform.cli import reset_project as rp

    repo_root = tmp_path / "repo"
    processed_dir = repo_root / "data" / "processed"
    runs_dir = repo_root / "runs"

    (processed_dir / "exp1").mkdir(parents=True)
    (processed_dir / "exp1" / "sample.txt").write_text("hello", encoding="utf-8")
    (runs_dir / "train1").mkdir(parents=True)
    (runs_dir / "train1" / "log.txt").write_text("run", encoding="utf-8")

    monkeypatch.setattr(rp, "ROOT_DIR", repo_root)

    logger = logging.getLogger("od_platform.test.reset_backup")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())

    archive = rp._create_backup_archive(
        logger,
        [processed_dir, runs_dir],
        label="runtime-artifacts",
        backup_dir=repo_root / ".odp-meta" / "backups",
    )

    assert archive is not None
    assert archive.exists()

    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        assert "data/processed/exp1/sample.txt" in names
        assert "runs/train1/log.txt" in names


def test_reset_project_aborts_when_backup_fails(tmp_path, monkeypatch):
    from od_platform.cli import reset_project as rp

    repo_root = tmp_path / "repo"
    processed_dir = repo_root / "data" / "processed"
    processed_dir.mkdir(parents=True)
    (processed_dir / "sample.txt").write_text("hello", encoding="utf-8")

    monkeypatch.setattr(rp, "ROOT_DIR", repo_root)
    monkeypatch.setattr(rp, "RAW_DATA_DIR", repo_root / "data" / "raw")
    monkeypatch.setattr(rp, "PRETRAINED_MODELS_DIR", repo_root / "models" / "pretrained")
    monkeypatch.setattr(rp, "get_dirs_to_reset", lambda: [processed_dir])
    monkeypatch.setattr(rp, "_scan_target_dirs", lambda logger: ([(processed_dir, 1, 5)], []))
    monkeypatch.setattr(
        rp,
        "_create_backup_archive",
        lambda logger, targets, label, backup_dir=rp.BACKUP_DIR: None,
    )

    called = {"delete": False}

    def fake_delete(*args, **kwargs):
        called["delete"] = True
        return 0, []

    monkeypatch.setattr(rp, "_execute_delete", fake_delete)

    logger = logging.getLogger("od_platform.test.reset_backup_abort")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    monkeypatch.setattr(rp, "get_logger", lambda *args, **kwargs: logger)
    monkeypatch.setattr(rp, "_audit_context", lambda: {"argv": [], "user": "u", "hostname": "h", "os_info": "o", "python_version": "p", "git_commit": "g"})

    code = rp.reset_project(yes=True, force=True, dry_run=False, backup=True)

    assert code == 2
    assert called["delete"] is False


def test_reset_project_keeps_backup_when_interrupted_after_backup(tmp_path, monkeypatch):
    from od_platform.cli import reset_project as rp

    repo_root = tmp_path / "repo"
    processed_dir = repo_root / "data" / "processed"
    processed_dir.mkdir(parents=True)
    (processed_dir / "sample.txt").write_text("hello", encoding="utf-8")

    backup_dir = repo_root / ".odp-meta" / "backups"
    archive_path = backup_dir / "runtime-artifacts-backup-20260709-000000.zip"

    monkeypatch.setattr(rp, "ROOT_DIR", repo_root)
    monkeypatch.setattr(rp, "RAW_DATA_DIR", repo_root / "data" / "raw")
    monkeypatch.setattr(rp, "PRETRAINED_MODELS_DIR", repo_root / "models" / "pretrained")
    monkeypatch.setattr(rp, "get_dirs_to_reset", lambda: [processed_dir])
    monkeypatch.setattr(rp, "_scan_target_dirs", lambda logger: ([(processed_dir, 1, 5)], []))
    def fake_backup(logger, targets, label, backup_dir=rp.BACKUP_DIR):
        assert label == "runtime-artifacts"
        backup_dir.mkdir(parents=True, exist_ok=True)
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_bytes(b"zip")
        return archive_path

    monkeypatch.setattr(rp, "_create_backup_archive", fake_backup)

    def fake_delete(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(rp, "_execute_delete", fake_delete)

    logger = logging.getLogger("od_platform.test.reset_backup_interrupt")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    monkeypatch.setattr(rp, "get_logger", lambda *args, **kwargs: logger)
    monkeypatch.setattr(rp, "_audit_context", lambda: {"argv": [], "user": "u", "hostname": "h", "os_info": "o", "python_version": "p", "git_commit": "g"})

    try:
        rp.reset_project(yes=True, force=True, dry_run=False, backup=True)
    except KeyboardInterrupt:
        pass

    assert archive_path.exists()
    assert (processed_dir / "sample.txt").exists()
