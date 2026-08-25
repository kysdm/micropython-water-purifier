import asyncio

import oled
import water
import log
import wifi
import ntp
import web


# from log import print_log

# https://github.com/peterhinch/micropython-async/blob/master/v3/docs/THREADING.md
# http://mytju.com/classcode/tools/encode_utf8.asp


# 主程序
async def main():
    try:
        log.print_log("程序启动")
        asyncio.create_task(log.check_and_rotate_log())  # 启动日志轮换任务
        asyncio.create_task(log.flush_logs_to_flash())  # 启动每分钟写入闪存的任务

        while True:
            # 连接WiFi
            oled.display_text("wifi connection", 3, 30)
            wifi.connect_wifi_sync()
            # 同步NTP时间
            oled.display_fill()  # 清空屏幕
            oled.display_text("ntp time sync", 3, 30)
            if ntp.sync_time_sync() == "ok":
                break
            await asyncio.sleep(10)
            # 未成功同步时间，禁止启动程序

        oled.display_fill()  # 清空屏幕
        oled.init()
        asyncio.create_task(water.timed_refresh_of_cartridge_usage_time())  # 启动定时刷新滤芯使用时间
        asyncio.create_task(water.refresh_tds_value())  # 启动刷新TDS值任务
        asyncio.create_task(wifi.monitor_wifi())  # 监控WiFi连接状态，自动重连
        asyncio.create_task(ntp.schedule_sync_time())  # 定时同步时间
        asyncio.create_task(web.start_web_server())  # 启动 Web 服务器

        await water.after_booting_flush_ro()  # 启动后立即冲洗一次

        asyncio.create_task(water.start_water_production())  # 长循环监听是否需要制水

        # asyncio.create_task(blink_led())

        while True:
            await asyncio.sleep(10)  # 主循环保持运行

    except KeyboardInterrupt:
        log.print_log("程序停止")


# 运行主程序
asyncio.run(main())
