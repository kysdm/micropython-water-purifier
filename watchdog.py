from machine import WDT


wdt = None


def feed():
    global wdt
    if wdt is None:
        # 初始化看门狗定时器，设置超时时间为10秒
        wdt = WDT(timeout=10000)  # 超时时间单位为毫秒
    # 喂狗，刷新看门狗定时器
    wdt.feed()
