import time
import asyncio
import ntptime

import threadsafe_context

from log import print_log
from time_utils import get_local_time
from time_utils import seconds_until_4_am
from time_utils import save_time_to_flash

# 设置自定义 NTP 服务器
ntptime.host = "ntp.aliyun.com"  # 使用阿里云的 NTP 服务器


MAX_RETRIES = 5  # 最大重试次数
INITIAL_DELAY = 5  # 初始重试间隔时间（秒）
BACKOFF_FACTOR = 2  # 指数退避倍数，每次失败后间隔时间翻倍

# 上一次时间是否同步成功
last_sync_success = False


def last_ntp_sync_status():
    global last_sync_success
    return last_sync_success


def sync_time_sync():
    global last_sync_success
    attempt = 0
    delay = INITIAL_DELAY  # 初始间隔时间

    while attempt < MAX_RETRIES:
        try:
            print_log(f"开始第 {attempt + 1} 次时间同步")
            ntptime.settime()  # 从 NTP 服务器获取时间
            last_sync_success = True
            save_time_to_flash()  # 备份当前时间，供断电后恢复近似时钟
            print_log("同步时间成功")
            print_log(f"本地时间: {get_local_time()}")
            return "ok"  # 成功后直接返回
        except Exception as e:
            print_log(f"同步时间失败 ({attempt + 1}/{MAX_RETRIES}): {e}")
            last_sync_success = False
            attempt += 1

            if attempt < MAX_RETRIES:
                print_log(f"等待 {delay} 秒后重试...")
                time.sleep(delay)
                delay *= BACKOFF_FACTOR  # 退避机制：间隔时间翻倍

    print_log("达到最大重试次数，放弃同步时间")


# 异步同步时间
async def sync_time():
    await threadsafe_context.internal_hardware.assign(sync_time_sync)


# 定时同步时间
async def schedule_sync_time():
    while True:
        try:
            if last_sync_success:
                # 时间已同步：每天 4 点定时校准一次
                await asyncio.sleep(seconds_until_4_am())
            else:
                # 上次同步失败（如断电后离线启动）：每 10 分钟重试，尽快校准时间
                await asyncio.sleep(600)
            await sync_time()
        except Exception as e:
            print_log(f"定时同步时间失败: {e}")
        finally:
            # 等待1秒，避免因为异常导致频繁错误循环
            await asyncio.sleep(10)
