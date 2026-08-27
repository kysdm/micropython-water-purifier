import network
import asyncio
import time

import config
import threadsafe_context

from log import print_log

# 初始化 Wi-Fi 接口
sta_if = network.WLAN(network.STA_IF)
sta_if.active(True)


# 连接到 Wi-Fi；返回 True 表示已连接，False 表示连接失败
def connect_wifi_sync():
    try:
        if not sta_if.isconnected():
            print_log("连接到 Wi-Fi")
            try:
                sta_if.connect(
                    config.get_config_value("wifi_ssid"),
                    config.get_config_value("wifi_password"),
                )
            except Exception:
                pass
            time.sleep(5)
            for i in range(24):  # 最多等待约 2 分钟（每 5 秒检查一次，共 24 次）
                if not sta_if.isconnected():
                    print_log(f"等待 Wi-Fi 连接...，已等待 {i * 5} 秒")
                    time.sleep(5)
                else:
                    print_log("Wi-Fi 连接成功")
                    print_log(f"WIFI 信息: {sta_if.ifconfig()}")
                    return True
            print_log("连接 Wi-Fi 超时")
            return False
        else:
            print_log("Wi-Fi 已连接")
            print_log(f"WIFI 信息: {sta_if.ifconfig()}")
            return True
    except Exception as e:
        print_log(f"连接 Wi-Fi 发生异常: {e}")
        return False


async def connect_wifi():
    await threadsafe_context.internal_hardware.assign(connect_wifi_sync)


# 监控 Wi-Fi 连接状态
async def monitor_wifi():
    while True:
        try:
            if not sta_if.isconnected():
                print_log("Wi-Fi 断开，尝试重连...")
                await connect_wifi()
            await asyncio.sleep(30)
        except Exception as e:
            print_log(f"监控 Wi-Fi 异常: {e}")
            await asyncio.sleep(60)  # 异常后等待 60 秒再继续
