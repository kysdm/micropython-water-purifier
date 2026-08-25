import asyncio
import time
import math

import config
import oled
import log


stop_event = asyncio.Event()


# 格式化倒计时输出
def format_time(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{hours:02}:{minutes:02}:{seconds:02}"


async def countdown(seconds: int, stop_event: asyncio.Event, after_func) -> None:
    """
    倒计时任务：以秒为单位倒计时，每秒更新剩余时间（以分钟为单位）显示到 OLED 上。
    当 stop_event 被设置时提前终止倒计时；倒计时结束后调用 after_func 函数。
    """
    start_time = time.ticks_ms()  # 记录起始时间（毫秒）
    end_time = time.ticks_add(start_time, seconds * 1000)  # 计算倒计时结束时间

    last_displayed_min = None

    while True:
        if stop_event.is_set():
            log.print_log("纯水泡膜倒计时被终止！")
            return

        now = time.ticks_ms()
        remaining_secs = time.ticks_diff(end_time, now) // 1000  # 剩余秒数
        if remaining_secs <= 0:
            break

        # 计算剩余分钟数，并避免重复更新
        remaining_min = math.ceil(remaining_secs / 60)
        if remaining_min != last_displayed_min:
            await oled.display_countdown_time(remaining_min)
            last_displayed_min = remaining_min

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
