#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging
import time
from functools import wraps
from pathlib import Path
from datetime import datetime


def get_logger(
    base_path: Path,
    log_type: str,
    temp_log: bool = False,
) -> logging.Logger:
    """创建带文件和控制台的 logger"""
    logger = logging.getLogger(log_type)
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台 handler
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # 文件 handler
    base_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "_temp" if temp_log else ""
    log_file = base_path / f"{log_type}_{timestamp}{suffix}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def log_execution(func=None, *, logger=None):
    """装饰器：自动记录函数执行时间和异常，可指定 logger"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            _logger = logger or logging.getLogger(func.__module__)
            _logger.info(f"[{func.__name__}] 开始执行")
            start = time.monotonic()
            try:
                result = func(*args, **kwargs)
                elapsed = time.monotonic() - start
                _logger.info(f"[{func.__name__}] 执行完成, 耗时 {elapsed:.3f}s")
                return result
            except Exception as e:
                elapsed = time.monotonic() - start
                _logger.error(f"[{func.__name__}] 执行失败({elapsed:.3f}s): {e}")
                raise
        return wrapper
    if func is not None:
        return decorator(func)
    return decorator
