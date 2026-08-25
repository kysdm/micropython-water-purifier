import asyncio
import time
import math

import config
import oled
import log


stop_event = asyncio.Event()


async def countdown(seconds: int, stop_event: asyncio.Event, after_func) -> None:
    """
    倒计时任务：以秒为单位倒计时，将剩余时间显示到 OLED 上（纯数字，不带单位）：
    - 剩余 >= 1 分钟：显示分钟数（每分钟刷新一次）
    - 剩余 < 1 分钟：显示秒数（每秒刷新一次）
    通过数字的刷新频率即可区分当前显示的是分钟还是秒。
    当 stop_event 被设置时提前终止倒计时；倒计时结束后调用 after_func 函数。
    """
    start_time = time.ticks_ms()  # 记录起始时间（毫秒）
    end_time = time.ticks_add(start_time, seconds * 1000)  # 计算倒计时结束时间

    last_displayed_value = None

    while True:
        if stop_event.is_set():
            log.print_log("纯水泡膜倒计时被终止！")
            return

        now = time.ticks_ms()
        remaining_secs = time.ticks_diff(end_time, now) // 1000  # 剩余秒数
        if remaining_secs <= 0:
            break

        if remaining_secs >= 60:
            # 剩余 1 分钟以上：显示分钟数（向上取整，每分钟刷新一次）
            display_value = math.ceil(remaining_secs / 60)
        else:
            # 剩余不足 1 分钟：显示秒数（每秒刷新一次）
            display_value = remaining_secs

        # 值变化时才刷新屏幕（分钟慢刷、秒快刷，刷新频率即单位提示）
        if display_value != last_displayed_value:
            await oled.display_countdown_time(display_value)
            last_displayed_value = display_value

        await asyncio.sleep(1)

    log.print_log("纯水泡膜倒计时结束！")
    await after_func()  # 倒计时结束后调用后续函数


async def start(after_func) -> None:
    """
    启动倒计时任务：
    - 先等待 30 秒，如果期间 stop_event 触发，则提前终止
    - 之后开始倒计时
    """

    try:
        log.print_log("开始纯水泡膜倒计时，准备启动纯水泡膜")
        await asyncio.wait_for(stop_event.wait(), timeout=30)
        log.print_log("纯水泡膜倒计时被终止！（在 30 秒等待阶段）")
        return
    except asyncio.TimeoutError:
        pass  # 30 秒超时后继续执行

    seconds = config.get_countdown_time()

    await countdown(seconds, stop_event, after_func)
