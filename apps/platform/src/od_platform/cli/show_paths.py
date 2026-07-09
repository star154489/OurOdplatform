#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : show_paths.py
# @Author    : ODPlatform team
# @Project   : ODPlatform
# @Function  : 路径诊断工具 —— 打印关键路径与目标清单
"""ODPlatform 路径诊断工具。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from od_platform.common.paths import (
    APP_DIR,
    CONFIGS_DIR,
    DATASET_CONFIGS_DIR,
    DATA_DIR,
    DOCS_DIR,
    LOGGING_DIR,
    META_DIR,
    META_LOGGING_DIR,
    MODELS_DIR,
    PRETRAINED_MODELS_DIR,
    PROCESSED_DATA_DIR,
    PROTECTED_DIRS,
    RAW_DATA_DIR,
    ROOT_DIR,
    RUNTIME_CONFIGS_DIR,
    RUNS_DIR,
    SCRIPTS_DIR,
    TRAINED_MODELS_DIR,
    WORKSPACE_MARKER,
    get_dirs_to_initialize,
    get_dirs_to_reset,
    get_project_core_backup_targets,
    get_runtime_backup_targets,
)


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


def build_paths_report() -> dict[str, list[tuple[str, str]]]:
    """构造路径诊断报告。"""
    core = [
        ("WORKSPACE_MARKER", WORKSPACE_MARKER),
        ("ROOT_DIR", str(ROOT_DIR)),
        ("APP_DIR", _relative(APP_DIR)),
        ("DATA_DIR", _relative(DATA_DIR)),
        ("MODELS_DIR", _relative(MODELS_DIR)),
        ("RUNS_DIR", _relative(RUNS_DIR)),
    ]
    runtime = [
        ("RAW_DATA_DIR", _relative(RAW_DATA_DIR)),
        ("PROCESSED_DATA_DIR", _relative(PROCESSED_DATA_DIR)),
        ("PRETRAINED_MODELS_DIR", _relative(PRETRAINED_MODELS_DIR)),
        ("TRAINED_MODELS_DIR", _relative(TRAINED_MODELS_DIR)),
        ("CONFIGS_DIR", _relative(CONFIGS_DIR)),
        ("DATASET_CONFIGS_DIR", _relative(DATASET_CONFIGS_DIR)),
        ("RUNTIME_CONFIGS_DIR", _relative(RUNTIME_CONFIGS_DIR)),
        ("LOGGING_DIR", _relative(LOGGING_DIR)),
        ("DOCS_DIR", _relative(DOCS_DIR)),
        ("SCRIPTS_DIR", _relative(SCRIPTS_DIR)),
        ("META_DIR", _relative(META_DIR)),
        ("META_LOGGING_DIR", _relative(META_LOGGING_DIR)),
    ]
    return {
        "core": core,
        "runtime": runtime,
        "initialize_targets": [("INIT", _relative(path)) for path in get_dirs_to_initialize()],
        "reset_targets": [("RESET", _relative(path)) for path in get_dirs_to_reset()],
        "runtime_backup_targets": [("RUNTIME_BACKUP", _relative(path)) for path in get_runtime_backup_targets()],
        "project_core_targets": [("PROJECT_CORE", _relative(path)) for path in get_project_core_backup_targets()],
        "protected_targets": [("PROTECTED", _relative(path)) for path in PROTECTED_DIRS],
    }


def _print_section(title: str, rows: list[tuple[str, str]]) -> None:
    print(f"[{title}]")
    for key, value in rows:
        print(f"{key:<22} {value}")
    print("")


def show_paths() -> int:
    """打印路径诊断报告。"""
    report = build_paths_report()
    _print_section("CORE", report["core"])
    _print_section("RUNTIME", report["runtime"])
    _print_section("INIT TARGETS", report["initialize_targets"])
    _print_section("RESET TARGETS", report["reset_targets"])
    _print_section("RUNTIME BACKUP TARGETS", report["runtime_backup_targets"])
    _print_section("PROJECT CORE TARGETS", report["project_core_targets"])
    _print_section("PROTECTED TARGETS", report["protected_targets"])
    return 0


def _build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="odp-paths",
        description="打印 ODPlatform 的关键路径与工程目标清单。",
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    parser.parse_args(argv)
    return show_paths()


if __name__ == "__main__":
    sys.exit(main())
