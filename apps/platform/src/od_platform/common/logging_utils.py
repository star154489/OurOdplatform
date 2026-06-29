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


def log_execution(func=None, *, logger=None, repeat: int = 1):
    """装饰器：记录函数执行时间/异常，支持多次运行取平均值

    Args:
        logger: 指定日志记录器
        repeat: 执行次数，用于计算平均/最快/最慢耗时（默认 1）
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            _logger = logger or logging.getLogger(func.__module__)
            times: list[float] = []
            last_result = None

            for run in range(1, repeat + 1):
                label = f" 第{run}/{repeat}次" if repeat > 1 else ""
                _logger.info(f"[{func.__name__}] 开始执行{label}")
                start = time.monotonic()
                last_result = func(*args, **kwargs)
                elapsed = time.monotonic() - start
                times.append(elapsed)
                _logger.info(f"[{func.__name__}] 完成{label}, 耗时 {elapsed:.3f}s")

            if repeat > 1 and times:
                avg = sum(times) / len(times)
                _logger.info(
                    f"[{func.__name__}] ===== 共 {len(times)} 次, "
                    f"平均 {avg:.3f}s, "
                    f"最快 {min(times):.3f}s, "
                    f"最慢 {max(times):.3f}s ====="
                )

            return last_result
        return wrapper
    if func is not None:
        return decorator(func)
    return decorator
