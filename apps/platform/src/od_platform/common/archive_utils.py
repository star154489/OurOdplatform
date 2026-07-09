"""归档/打包相关工具。"""

from __future__ import annotations

import json
import logging
import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterable


def build_archive_name(label: str) -> str:
    """生成归档包名。"""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{label}-backup-{timestamp}.zip"


def _relative_strings(root_dir: Path, targets: Iterable[Path]) -> list[str]:
    """把目标路径转成相对路径字符串。"""
    items: list[str] = []
    for target in targets:
        try:
            items.append(target.relative_to(root_dir).as_posix())
        except ValueError:
            items.append(str(target))
    return items


def _write_archive_manifest(
    logger: logging.Logger,
    *,
    manifest_path: Path,
    tool_name: str,
    label: str,
    root_dir: Path,
    archive_path: Path,
    targets: list[Path],
    dir_count: int,
    file_count: int,
) -> Path | None:
    """为归档包写入 manifest。"""
    payload = {
        "format_version": 1,
        "tool_name": tool_name,
        "label": label,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "root_dir": str(root_dir),
        "archive_path": str(archive_path),
        "targets": _relative_strings(root_dir, targets),
        "dir_count": dir_count,
        "file_count": file_count,
    }
    try:
        manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("已生成 manifest: %s", manifest_path)
        return manifest_path
    except OSError as e:
        logger.warning("写入 manifest 失败: %s", e)
        return None


def create_zip_archive(
    logger: logging.Logger,
    *,
    root_dir: Path,
    targets: Iterable[Path],
    backup_dir: Path,
    label: str,
    tool_name: str,
) -> Path | None:
    """把给定目标打包为 zip 归档，并生成同名 manifest。"""
    existing_targets = [path for path in targets if path.exists()]
    if not existing_targets:
        logger.info("没有可备份的目标，跳过打包")
        return None

    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("创建备份目录失败，跳过打包: %s", e)
        return None

    backup_path = backup_dir / build_archive_name(label)
    file_count = 0
    dir_count = 0

    try:
        with zipfile.ZipFile(
            backup_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as zf:
            for target in existing_targets:
                if target.is_dir():
                    dir_count += 1
                    for root, _, files in os.walk(target):
                        root_path = Path(root)
                        rel_root = root_path.relative_to(root_dir)
                        zf.writestr(f"{rel_root.as_posix()}/", "")
                        for name in files:
                            src = root_path / name
                            arcname = src.relative_to(root_dir).as_posix()
                            zf.write(src, arcname)
                            file_count += 1
                else:
                    arcname = target.relative_to(root_dir).as_posix()
                    zf.write(target, arcname)
                    file_count += 1

        logger.info(
            "已打包备份[%s]: %s (目录 %d 个, 文件 %d 个)",
            label,
            backup_path,
            dir_count,
            file_count,
        )

        manifest_path = backup_path.with_suffix(".json")
        if _write_archive_manifest(
            logger,
            manifest_path=manifest_path,
            tool_name=tool_name,
            label=label,
            root_dir=root_dir,
            archive_path=backup_path,
            targets=existing_targets,
            dir_count=dir_count,
            file_count=file_count,
        ) is None:
            try:
                if backup_path.exists():
                    backup_path.unlink()
            except OSError:
                pass
            return None

        return backup_path
    except OSError as e:
        logger.warning("创建备份包失败，跳过打包: %s", e)
        try:
            if backup_path.exists():
                backup_path.unlink()
        except OSError:
            pass
        return None
