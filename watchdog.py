from machine import WDT

import asyncio


wdt = None
FEED_INTERVAL_S = 5  # 独立喂狗任务间隔（秒），必须小于 WDT 超时 10 秒


def feed():
    global wdt
    if wdt is None:
        # 初始化看门狗定时器，设置超时时间为10秒
        wdt = WDT(timeout=10000)  # 超时时间单位为毫秒
    wdt.feed()


async def _feed_loop():
    """独立喂狗任务：任何业务协程崩溃都不会停止喂狗；
    只有 asyncio 事件循环整体卡死时看门狗才会复位（保留防卡死作用）"""
    while True:
        feed()
        await asyncio.sleep(FEED_INTERVAL_S)


def start_feed_task():
    """在 asyncio 事件循环内调用：启动独立的喂狗任务（须在 main 协程内调用）"""
    asyncio.create_task(_feed_loop())
