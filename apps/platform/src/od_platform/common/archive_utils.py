"""归档/打包相关工具。"""

from __future__ import annotations

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


def create_zip_archive(
    logger: logging.Logger,
    *,
    root_dir: Path,
    targets: Iterable[Path],
    backup_dir: Path,
    label: str,
) -> Path | None:
    """把给定目标打包为 zip 归档。"""
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
        return backup_path
    except OSError as e:
        logger.warning("创建备份包失败，跳过打包: %s", e)
        try:
            if backup_path.exists():
                backup_path.unlink()
        except OSError:
            pass
        return None
