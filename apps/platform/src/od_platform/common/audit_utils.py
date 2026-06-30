#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : audit_utils.py
# @Author    : 雨霓同学
# @Project   : ODPlatform
# @Function  : 审计追踪工具 —— 采集运行上下文 + 落盘审计日志

from __future__ import annotations

import getpass
import json
import logging
import os
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from od_platform._version import version as _tool_version
from od_platform.common.paths import ROOT_DIR


def _audit_context() -> dict:
    """采集当前执行环境的审计上下文字典。

    每次 reset_project 执行（含 dry-run）前调用，返回结构化信息，
    之后由调用方序列化写入审计日志首行。

    Returns:
        dict: 包含 timestamp / tool_name / tool_version / user /
              hostname / cwd / root_dir / argv / os_info /
              python_version / git_commit 字段。
    """
    # -- git commit（软依赖，失败降级） --
    git_commit: str = "unknown"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            git_commit = result.stdout.strip()
    except Exception:
        git_commit = "unknown"

    # -- 用户名（软依赖） --
    user: str = "unknown"
    try:
        user = getpass.getuser()
    except Exception:
        user = "unknown"

    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool_name": "reset_project",
        "tool_version": _tool_version,
        "user": user,
        "hostname": socket.gethostname(),
        "cwd": str(Path.cwd()),
        "root_dir": str(ROOT_DIR),
        "argv": sys.argv,
        "os_info": f"{platform.system()}-{platform.release()}",
        "python_version": platform.python_version(),
        "git_commit": git_commit,
    }


def write_audit_log(
    log_dir: Path,
    context: dict,
    logger: logging.Logger,
) -> Path:
    """将审计上下文写入独立审计日志文件，并配置 logger 向其输出。

    日志文件命名格式：reset-project_<YYYYMMDD-HHMMSS-fff>_<pid>.log
    首行为 [AUDIT] 前缀的 JSON 上下文，后续为运行记录。

    Args:
        log_dir: 日志输出目录（应为 META_LOGGING_DIR / "reset_project"）。
        context: 由 _audit_context() 返回的上下文字典。
        logger: 业务 logger，会在本函数内为其添加文件 handler。

    Returns:
        Path: 审计日志文件路径。
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp_str = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]  # 毫秒精度
    pid = os.getpid()
    log_filename = f"reset-project_{timestamp_str}_{pid}.log"
    log_path = log_dir / log_filename

    # 写入首行 [AUDIT] JSON
    audit_line = "[AUDIT] " + json.dumps(context, ensure_ascii=False) + "\n"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(audit_line)

    # 为 logger 添加文件 handler（不含 ANSI 颜色码）
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # 记录审计上下文到日志流
    logger.debug(f"审计日志文件: {log_path}")
    logger.debug(f"审计上下文: {json.dumps(context, ensure_ascii=False)}")

    return log_path
