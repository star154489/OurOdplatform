#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :audit_utils.py
# @Author    :ODPlatform team
# @Project   :ODPlatform
# @Function  :审计上下文采集工具——为 reset_project 等危险操作提供可追溯的执行记录
"""
审计上下文采集模块。

每次危险操作（如 reset_project）执行前调用 ``_audit_context()``，
返回结构化的上下文字典，包含执行者、时间、环境、目标命令等信息。

设计原则（FR-AUDIT-001）：
  - 函数本身不写任何文件；仅返回 dict。
  - 所有软依赖失败时降级（不抛异常）。
  - 耗时 ≤ 500ms。
"""

from __future__ import annotations

import getpass
import os
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from od_platform import __version__
from od_platform.common import paths


def _audit_context() -> dict:
    """
    采集并返回结构化的审计上下文字典。

    Returns:
        包含以下字段的 dict：
        - timestamp:    UTC 时间，ISO 8601 格式
        - tool_name:    固定 "reset_project"
        - tool_version: 从 ``od_platform.__version__`` 读取
        - user:         系统登录用户名（失败时降级 "unknown"）
        - hostname:     主机名
        - cwd:          当前工作目录
        - root_dir:     ``paths.ROOT_DIR`` 字符串
        - argv:         原始命令行参数列表
        - os_info:      操作系统名与版本
        - python_version: Python 版本
        - git_commit:   当前 HEAD commit hash（失败时 "unknown"）
    """
    # ── 时间 ────────────────────────────────────────────────
    timestamp: str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── 用户 & 主机 ──────────────────────────────────────────
    try:
        user: str = getpass.getuser()
    except Exception:
        user = "unknown"

    try:
        hostname: str = socket.gethostname()
    except Exception:
        hostname = "unknown"

    # ── 操作系统 & Python 版本 ────────────────────────────────
    os_info: str = f"{platform.system()}-{platform.release()}-{platform.machine()}"
    python_version: str = platform.python_version()

    # ── Git commit ──────────────────────────────────────────
    git_commit: str = "unknown"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=paths.ROOT_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            git_commit = result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass

    return {
        "timestamp": timestamp,
        "tool_name": "reset_project",
        "tool_version": __version__,
        "user": user,
        "hostname": hostname,
        "cwd": str(Path.cwd()),
        "root_dir": str(paths.ROOT_DIR),
        "argv": sys.argv,
        "os_info": os_info,
        "python_version": python_version,
        "git_commit": git_commit,
    }
