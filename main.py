import asyncio

import screen_ui
import water
import log
import wifi
import ntp
import web
import config
import time_utils
import watchdog


NTP_SYNC_ATTEMPTS = 2  # 开机 NTP 同步尝试次数；失败后以本地保存的近似时间继续启动

# from log import print_log

# https://github.com/peterhinch/micropython-async/blob/master/v3/docs/THREADING.md
# http://mytju.com/classcode/tools/encode_utf8.asp


# 主程序
async def main():
    try:
        # 断电后 RTC 丢失：先用上次保存的时间恢复近似时钟（误差 = 断电时长）
        if time_utils.apply_saved_time():
            log.print_log("已恢复上次保存的时间（近似值），等待 NTP 校准")
        else:
            log.print_log("无已保存时间或 RTC 仍有效，等待 NTP 同步")
        log.print_log("程序启动")
        watchdog.start_feed_task()  # 独立喂狗任务：启动即开始，防止 WDT 超时复位
        asyncio.create_task(log.check_and_rotate_log())  # 启动日志轮换任务
        asyncio.create_task(log.flush_logs_to_flash())  # 启动每分钟写入闪存的任务
        asyncio.create_task(time_utils.periodic_time_backup())  # 每小时备份时间到 flash，供断电恢复

        # 连接WiFi（等待界面显示待连接的 WiFi 名称；framebuf 8x8 字体不支持中文，非 ASCII 转 ? 显示）
        # 异步版：阻塞等待在 network_hardware 线程执行，不卡 asyncio 事件循环
        screen_ui.display_text("wifi connection", 3, 30)
        ssid = str(config.get_config_value("wifi_ssid"))
        ssid_display = "".join(ch if ord(ch) < 128 else "?" for ch in ssid)
        screen_ui.display_text("SSID: " + ssid_display, 3, 46)
        wifi_connected = await wifi.connect_wifi()
        # 同步NTP时间（仅WiFi已连接时尝试；未连接则跳过，由定时任务在连网后重试）
        screen_ui.display_fill()  # 清空屏幕
        if wifi_connected:
            screen_ui.display_text("ntp time sync", 3, 30)
            time_synced = False
            for _ in range(NTP_SYNC_ATTEMPTS):
                if await ntp.sync_time() == "ok":
                    time_synced = True
                    break
                await asyncio.sleep(10)
            if not time_synced:
                log.print_log("NTP 同步失败，以本地近似时间继续启动（将每 10 分钟重试同步）")
        else:
            log.print_log("WiFi 未连接，跳过开机 NTP 同步（连网后由定时任务自动同步）")

        screen_ui.display_fill()  # 清空屏幕
        screen_ui.init()
        asyncio.create_task(screen_ui.orbit_task())  # 像素偏移，防止 OLED 烧屏
        asyncio.create_task(screen_ui.auto_off_task())  # 空闲自动熄屏，防止烧屏
        asyncio.create_task(screen_ui.refresh_bottom_bar())  # TFT 底部 WiFi 状态/IP 信息栏（OLED 自动跳过）
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
