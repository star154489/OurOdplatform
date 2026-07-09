#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  :log_rename.py
# @Time      :2026/7/6 13:21:04
# @Author    :雨霓同学
# @Project   :ODPlatform
# @Function  :把运行期的"临时日志"改名归档到最终产物目录名下
#
# 配合 logging_utils.get_logger(temp_log=True):
#   起跑时还不知道最终产物目录(ultralytics 运行中才建 exp 目录),
#   先写 temp_<时间戳>.log; 跑完拿到 save_dir 再调本函数改成有意义的名字。
from __future__ import annotations

import logging
from pathlib import Path

from od_platform.common.logging_utils import LOG_TIMESTAMP_RE, ROOT_LOGGER_NAME

logger = logging.getLogger(__name__)

_UNKNOWN_TIME = "unknown-time"


def _iter_od_platform_loggers() -> list[logging.Logger]:
    """收集根 logger 及其所有已实例化的 od_platform.* 子 logger。

    历史原因: CLI 入口有的把 handler 挂在根 'od_platform', 有的挂在子 logger
    (如 'od_platform.cli.train_model')。只看根会漏掉子 logger 上的 FileHandler,
    导致 train/val 流程改名静默失败。这里把两种情况都覆盖。
    """
    root = logging.getLogger(ROOT_LOGGER_NAME)
    seen = {id(root)}          # 根 logger 已在列, 防止 loggerDict 里再加一遍导致重复处理
    loggers = [root]
    manager = logging.Logger.manager
    for name, obj in manager.loggerDict.items():
        if not isinstance(obj, logging.Logger):
            continue  # 跳过 PlaceHolder
        # 只收子 logger(od_platform.xxx); 根已在 loggers 里, 用 id 去重再保险一层
        if name.startswith(ROOT_LOGGER_NAME + ".") and id(obj) not in seen:
            seen.add(id(obj))
            loggers.append(obj)
    return loggers


def _find_file_handlers() -> list[tuple[logging.Logger, logging.FileHandler]]:
    """在所有 od_platform 相关 logger 上找 FileHandler。"""
    found: list[tuple[logging.Logger, logging.FileHandler]] = []
    seen_handlers: set[int] = set()  # 同一 handler 若挂在多个 logger 上, 只处理一次
    for lg in _iter_od_platform_loggers():
        for h in lg.handlers:
            if isinstance(h, logging.FileHandler) and id(h) not in seen_handlers:
                seen_handlers.add(id(h))
                found.append((lg, h))
    return found


def rename_log_to_save_dir(
    save_dir: Path,
    model_stem: str,
) -> Path | None:
    """把当前的(临时)日志文件改名成 <save_dir名>_<时间戳>_<model_stem>.log。

    特性:
      - 健壮查找: 根 logger 和子 logger 上的 FileHandler 都能找到。
      - 幂等: 若日志名已归档到本 save_dir(前缀匹配), 直接跳过, 不再套一层前缀。
      - 安全: 改名失败时回滚旧 handler, 保证后续日志不丢。

    Returns:
        改名后的新路径; 无 FileHandler 或改名失败时返回 None;
        已是目标名(幂等命中)时返回当前路径。
    """
    handlers = _find_file_handlers()
    if not handlers:
        logger.warning(f"{ROOT_LOGGER_NAME} 相关 logger 上没有 FileHandler, 跳过日志改名")
        return None

    # 通常只有一个 FileHandler; 若有多个(如 debug/error 分离), 全部改名, 返回第一个。
    result_path: Path | None = None
    for lg, file_handler in handlers:
        renamed = _rename_one(lg, file_handler, save_dir, model_stem)
        if renamed is not None and result_path is None:
            result_path = renamed
    return result_path


def _rename_one(
    owner: logging.Logger,
    file_handler: logging.FileHandler,
    save_dir: Path,
    model_stem: str,
) -> Path | None:
    old_path = Path(file_handler.baseFilename)
    prefix = f"{save_dir.name}_"

    # ── 幂等保护: 已经改到本 save_dir 名下, 不重复改名(避免 exp_exp_... 脏名) ──
    if old_path.name.startswith(prefix):
        logger.debug(f"日志 {old_path.name} 已归档到 {save_dir.name}, 跳过重复改名")
        return old_path

    # 1. 从原文件名提取时间戳
    match = LOG_TIMESTAMP_RE.search(old_path.stem)
    if match:
        timestamp = match.group(0)
    else:
        timestamp = _UNKNOWN_TIME
        logger.warning(f"原日志 {old_path} 没有时间戳, 使用 {_UNKNOWN_TIME}")

    new_name = f"{save_dir.name}_{timestamp}_{model_stem}.log"
    new_path = old_path.parent / new_name

    # 2. 保存旧 handler 配置, 供新 handler / 回滚复用
    formatter = file_handler.formatter
    level = file_handler.level
    encoding = getattr(file_handler, "encoding", None) or "utf-8"

    # 3. 关闭旧 handler 释放文件句柄(Windows 上占用中的文件无法 rename)
    file_handler.close()
    owner.removeHandler(file_handler)

    # 4. 物理改名
    if not old_path.exists():
        logger.warning(f"原日志 {old_path} 不存在, 跳过改名")
        return None
    try:
        old_path.rename(new_path)
    except OSError as e:
        logger.warning(f"原日志 {old_path} 改名失败({e}), 尝试恢复旧 handler 继续写")
        _reattach(owner, old_path, formatter, level, encoding)
        return None

    # 5. 新 handler 指向新文件, 保证改名后仍能继续写
    new_handler = _reattach(owner, new_path, formatter, level, encoding)
    if new_handler is None:
        # 新 handler 建不起来: 文件已改名成功, 但后续日志可能丢
        return new_path

    logger.info(f"日志文件已重命名: {new_path.name}")
    return new_path


def _reattach(
    owner: logging.Logger,
    path: Path,
    formatter: logging.Formatter | None,
    level: int,
    encoding: str,
) -> logging.FileHandler | None:
    """在 owner 上重建一个指向 path 的 FileHandler(改名后续写 / 回滚共用)。"""
    try:
        handler = logging.FileHandler(path, encoding=encoding)
        if formatter:
            handler.setFormatter(formatter)
        handler.setLevel(level)
        owner.addHandler(handler)
        return handler
    except OSError as e:
        logger.error(f"重建 FileHandler 失败({e}) - 后续日志可能丢失")
        return None
