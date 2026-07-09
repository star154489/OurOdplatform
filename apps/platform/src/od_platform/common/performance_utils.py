#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName  : performance_utils.py
# @Project   : ODPlatform
# @Function  : 性能测量工具——@time_it 装饰器
#              (name 支持 callable; 兼容 async; 异常也计时; 耗时可编程读取)

import asyncio
import logging
import time
from functools import wraps
from typing import Callable, Optional, Union

# 业务模块标准写法:拿一个以本模块命名的 logger,只管"发声"
logger = logging.getLogger(__name__)


def _format_time_auto_unit(seconds: float) -> str:
    """根据耗时长短,自动选择合适的单位,让数字好读。"""
    if seconds < 0.001:
        return f"{seconds * 1_000_000:.3f} 微秒"
    elif seconds < 1.0:
        return f"{seconds * 1000:.3f} 毫秒"
    elif seconds < 60:
        return f"{seconds:.2f} 秒"
    elif seconds < 3600:
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins:.0f} 分钟 {secs:.2f} 秒"
    else:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        secs = (seconds % 3600) % 60
        return f"{hours:.0f} 小时 {mins:.0f} 分钟 {secs:.2f} 秒"


def time_it(
    iterations: int = 1,
    name: Optional[Union[str, Callable[..., str]]] = None,
    logger_instance: logging.Logger = None,
):
    """通用执行时间测量装饰器 —— 同步 / 异步函数通用。

    name 可以传:
        - None      : 用被装饰函数的 __name__
        - str       : 固定显示名
        - callable  : 接收"被装饰函数运行期实参",返回显示名(每次调用名字不同的场景)

    行为特性:
        - 兼容 async: 装饰 `async def` 时返回协程函数, await 内部计时(逐轮 await)。
        - 异常也计时: 被测函数抛异常时, 仍记录"失败前耗时"并标注 [失败], 再原样抛出。
        - 耗时可编程读取: 每次调用后, 结果挂在 wrapper 上:
            fn.last_duration          -> float, 平均耗时(秒)
            fn.last_total_duration    -> float, 总耗时(秒)
            fn.last_succeeded         -> bool, 最近一次是否成功跑完
          (未调用过时这些属性为 None。)

    Examples:
        @time_it()
        def my_func(): ...

        @time_it(iterations=10, name="批量推理")
        def infer_batch(): ...

        @time_it()
        async def fetch(): ...

        print(my_func.last_duration)   # 编程读取上一次耗时
    """
    # 默认用本模块的 logger;调用方可以传一个特定 logger 进来
    # (比如希望日志带着调用方的 logger 名,一眼看出是谁报的耗时)
    log = logger_instance if logger_instance is not None else logger

    # 迭代次数至少 1, 防止除零 / 空循环
    safe_iterations = max(1, iterations)

    def _resolve_name(func, args, kwargs) -> str:
        # 只有 callable 才走"运行期取名"; str / None 完全保持简单逻辑
        if callable(name):
            try:
                return name(*args, **kwargs)
            except Exception:
                # 取名失败绝不能拖垮被测函数 —— 退回函数名,测量照常进行
                log.warning(f"time_it: name() 计算失败, 回退到 {func.__name__}", exc_info=True)
                return func.__name__
        if name is not None:
            return name
        return func.__name__

    def _report(wrapper, display_name: str, total: float, succeeded: bool) -> None:
        """统一写"性能报告"日志, 并把耗时数据挂到 wrapper 上供编程读取。"""
        avg = total / safe_iterations
        wrapper.last_total_duration = total
        wrapper.last_duration = avg
        wrapper.last_succeeded = succeeded

        status = "" if succeeded else " [失败]"
        avg_str = _format_time_auto_unit(avg)
        if safe_iterations == 1:
            log.info(
                f"性能报告{status}: '{display_name}' 执行 {safe_iterations} 次 ,  耗时: {avg_str}"
            )
        else:
            total_str = _format_time_auto_unit(total)
            log.info(
                f"性能报告{status}: '{display_name}' 执行 {safe_iterations} 次 | "
                f"总耗时: {total_str} | 平均耗时: {avg_str}"
            )

    def decorator(func):
        is_coro = asyncio.iscoroutinefunction(func)

        if is_coro:
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                display_name = _resolve_name(func, args, kwargs)
                total = 0.0
                result = None
                succeeded = False
                try:
                    for _ in range(safe_iterations):
                        start = time.perf_counter()
                        result = await func(*args, **kwargs)
                        total += (time.perf_counter() - start)
                    succeeded = True
                    return result
                except BaseException:
                    # 异常前已累计的耗时也要记录 —— 但当前这一轮未跑完, 补记它
                    total += (time.perf_counter() - start)
                    raise
                finally:
                    _report(async_wrapper, display_name, total, succeeded)

            async_wrapper.last_duration = None
            async_wrapper.last_total_duration = None
            async_wrapper.last_succeeded = None
            return async_wrapper

        @wraps(func)
        def wrapper(*args, **kwargs):
            display_name = _resolve_name(func, args, kwargs)
            total = 0.0
            result = None
            succeeded = False
            try:
                for _ in range(safe_iterations):
                    start = time.perf_counter()
                    result = func(*args, **kwargs)
                    total += (time.perf_counter() - start)
                succeeded = True
                return result
            except BaseException:
                total += (time.perf_counter() - start)
                raise
            finally:
                _report(wrapper, display_name, total, succeeded)

        wrapper.last_duration = None
        wrapper.last_total_duration = None
        wrapper.last_succeeded = None
        return wrapper

    return decorator


if __name__ == "__main__":
    # 自测:单独配一个简单 handler——真实使用中, CLI 入口已经配好了, 这里不用
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s",
                        datefmt="%H:%M:%S")

    @time_it(name="测试睡眠 0.1 秒")
    def test_sleep():
        time.sleep(0.1)

    @time_it(iterations=5, name="测试快函数")
    def test_fast():
        sum(range(1000))

    @time_it(name="测试异常计时")
    def test_raise():
        time.sleep(0.02)
        raise ValueError("boom")

    @time_it(name="测试异步", iterations=3)
    async def test_async():
        await asyncio.sleep(0.01)
        return "ok"

    test_sleep()
    print("last_duration =", test_sleep.last_duration)

    test_fast()

    try:
        test_raise()
    except ValueError:
        print("异常已抛出, 但耗时仍被记录:", test_raise.last_duration,
              "succeeded =", test_raise.last_succeeded)

    print("async 返回:", asyncio.run(test_async()), "耗时:", test_async.last_duration)
