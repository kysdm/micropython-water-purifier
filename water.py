import asyncio
import time

import pins
import watchdog
import oled
import time_utils
import config
import cartridge_usage_time
import countdown
import log

from pins import rgb_led
from tds import get_tds_and_temperature
from timer import Timer
from ws2812b import WS2812B


timer = Timer()  # 计时器
forced_flush_ro_task = None  # 强制冲洗RO膜任务事件
fill_pressure_drum_with_water_task = None  # 压力桶注水任务事件
led = WS2812B(1, rgb_led)  # 灯带对象

purified_water_tds_value = 0  # 纯水TDS值
wastewater_tds_value = 0  # 废水TDS值

# cmulative_running_time = 0  # 累计运行时间

water_running = False  # False 表示停止，True 表示正在制水


# async def start_water_production():
#     """制水程序"""
#     _status = 0  # 状态变量，0 表示停止，1 表示启动

#     while True:
#         try:
#             low_value = pins.low_pressure_switch.value()  # 读取低压开关状态 1 表示压力未达标，0 表示压力达标
#             high_value = pins.high_pressure_switch.value()  # 读取高压开关状态 0 表示压力未达标，1 表示压力达标
#             if low_value == 1:
#                 # 停水，停止制水
#                 _status = 0
#                 pins.pressure_bucket_to_water_outlet_solenoid_valve_switch.value(0)  # 关闭压力桶出水电磁阀
#                 pins.water_inlet_solenoid_valve_switch.value(0)  # 关闭进水电磁阀
#                 pins.booster_pump_solenoid_valve_switch.value(0)  # 关闭增压泵电磁阀
#                 pins.pressure_bucket_to_water_inlet_solenoid_valve_switch.value(0)  # 关闭压力桶进水电磁阀
#                 forced_flush_ro_task_stop_event.set()  # 停止强制冲洗RO膜任务
#                 fill_pressure_drum_with_water_task_stop_event.set()  # 停止压力桶注水任务
#                 log.print_log("缺水，停止制水.")
#                 await waiting_for_water_intake_to_recover()  # 等待进水恢复
#                 await oled.display_status("空闲")
#                 forced_flush_ro_task_stop_event.clear()  # 重置强制冲洗RO膜任务停止事件
#                 log.print_log("进水压力达标，可以开始制水。")
#             elif high_value == 0 and _status == 0:
#                 # 开始制水
#                 _status = 1
#                 countdown.stop_event.set()  # 停止倒计时
#                 fill_pressure_drum_with_water_task_stop_event.set()  # 停止压力桶注水任务
#                 pins.pressure_bucket_to_water_outlet_solenoid_valve_switch.value(0)  # 关闭压力桶出水电磁阀
#                 pins.water_inlet_solenoid_valve_switch.value(1)  # 打开进水电磁阀
#                 pins.booster_pump_solenoid_valve_switch.value(1)  # 打开增压泵电磁阀
#                 # pins.pressure_bucket_to_water_inlet_solenoid_valve_switch.value(1)  # 打开压力桶进水电磁阀
#                 timer.start()  # 开始计时
#                 led.set_color(0, 0, 255)  # 蓝色
#                 await oled.display_status("制水")
#                 log.print_log("开始制水.")
#             elif high_value == 1 and _status == 1:
#                 # 停止制水
#                 _status = 0
#                 countdown.stop_event.clear()  # 重置倒计时
#                 fill_pressure_drum_with_water_task_stop_event.clear()  # 重置压力桶注水任务
#                 pins.pressure_bucket_to_water_outlet_solenoid_valve_switch.value(0)  # 关闭压力桶出水电磁阀
#                 pins.water_inlet_solenoid_valve_switch.value(0)  # 关闭进水电磁阀
#                 pins.booster_pump_solenoid_valve_switch.value(0)  # 关闭增压泵电磁阀
#                 # pins.pressure_bucket_to_water_inlet_solenoid_valve_switch.value(0)  # 关闭压力桶进水电磁阀
#                 timer.stop()  # 停止计时
#                 led.clear()  # 灯光熄灭
#                 await oled.display_status("空闲")
#                 asyncio.create_task(fill_pressure_drum_with_water())  # 启动压力桶注水任务
#                 asyncio.create_task(countdown.start(pure_water_reflow_ro))
#                 asyncio.create_task(forced_flush_ro())
#                 log.print_log("停止制水.")
#                 log.print_log("开始倒计时，准备启动纯水泡膜")
#         except Exception as e:
#             _status = 0  # 发生异常，状态强制设为停止制水
#             log.print_log(f"制水程序发生错误: {e}")
#         finally:
#             await asyncio.sleep(0.5)
#             watchdog.feed()  # 喂狗


async def start_water_production():
    """制水程序主循环"""
    global water_running
    global forced_flush_ro_task

    # __pressure_drum_task_confirmation = False  # 压力桶注水任务确认标志位

    while True:
        watchdog.feed()  # 喂狗
        low_pressure = pins.low_pressure_switch.value()  # 1 表示压力不足
        high_pressure = pins.high_pressure_switch.value()  # 0 表示压力未达标

        if low_pressure == 1:
            # 缺水状态，无论是否在制水，都需要停止制水，并等待进水恢复
            if water_running:
                await stop_water_actions()
                water_running = False
                # __pressure_drum_task_confirmation = False  # 压力桶注水任务确认标志位
            log.print_log("缺水，停止制水.")
            forced_flush_ro_task_stop()  # 停止强制冲洗RO膜任务
            # fill_pressure_drum_with_water_task_stop()  # 停止压力桶注水任务
            await waiting_for_water_intake_to_recover()  # 等待进水恢复
            await oled.display_status("空闲")
            log.print_log("进水压力达标，可以开始制水。")

        elif high_pressure == 0 and not water_running:
            # 开始制水
            forced_flush_ro_task_stop()  # 停止强制冲洗RO膜任务
            await start_water_actions()
            water_running = True

        # elif high_pressure == 1 and water_running and not __pressure_drum_task_confirmation:
        #     # 水龙头关闭，高压开关打开，压力桶注水任务未执行
        #     await start_pressure_drum_with_water()  # 启动压力桶注水任务
        #     __pressure_drum_task_confirmation = True  # 压力桶注水任务确认标志位

        elif high_pressure == 1 and water_running:
            # 水龙头关闭，高压开关打开，压力桶注水任务已执行
            await stop_water_actions()
            water_running = False
            # __pressure_drum_task_confirmation = False  # 压力桶注水任务确认标志位
            # asyncio.create_task(fill_pressure_drum_with_water())  # 启动压力桶注水任务
            forced_flush_ro_task = asyncio.create_task(forced_flush_ro())  # 大流量强制冲洗RO膜
            asyncio.create_task(countdown.start(pure_water_reflow_ro))
            log.print_log("停止制水.")

        await asyncio.sleep(0.5)


async def start_water_actions():
    """启动制水的操作"""
    countdown.stop_event.set()  # 停止倒计时任务
    # fill_pressure_drum_with_water_task_stop()  # 停止压力桶注水任务3

    pins.water_inlet_solenoid_valve_switch.value(1)  # 打开进水电磁阀
    pins.pressure_bucket_to_water_outlet_solenoid_valve_switch.value(0)  # 关闭压力桶出水电磁阀
    pins.pressure_bucket_to_water_inlet_solenoid_valve_switch.value(1)  # 打开压力桶进水电磁阀
    pins.booster_pump_solenoid_valve_switch.value(1)  # 打开增压泵电磁阀

    timer.start()  # 开始计时
    led.set_color(199, 18, 184)  # 设置LED为紫色，表示制水中
    await oled.display_status("制水")
    log.print_log("开始制水.")


async def stop_water_actions():
    """停止制水的操作"""
    countdown.stop_event.clear()  # 重置倒计时停止事件

    pins.booster_pump_solenoid_valve_switch.value(0)  # 关闭增压泵电磁阀
    pins.pressure_bucket_to_water_outlet_solenoid_valve_switch.value(0)  # 关闭压力桶出水电磁阀
    pins.pressure_bucket_to_water_inlet_solenoid_valve_switch.value(0)  # 关闭压力桶进水电磁阀
    pins.water_inlet_solenoid_valve_switch.value(0)  # 关闭进水电磁阀

    timer.stop()  # 停止计时
    led.clear()  # 熄灭LED
    await oled.display_status("空闲")


async def start_pressure_drum_with_water():
    """启动压力桶注水的操作"""
    pins.pressure_bucket_to_water_inlet_solenoid_valve_switch.value(1)
    log.print_log("开始向压力桶注水.")
    await asyncio.sleep(1)  # 防止压力开关反应不及时
    log.print_log("[debug] 开始向压力桶注水. *等待了1秒*")


# def fill_pressure_drum_with_water():
#     """启动压力桶注水任务"""
#     global fill_pressure_drum_with_water_task

#     async def start():
#         """向压力桶中注水"""
#         pins.pressure_bucket_to_water_inlet_solenoid_valve_switch.value(1)  # 打开压力桶进水电磁阀
#         await asyncio.sleep(3)

#         while water_running:
#             # 等待压力桶中水量达到最大值
#             await asyncio.sleep(1)

#         pins.pressure_bucket_to_water_inlet_solenoid_valve_switch.value(0)  # 关闭压力桶进水电磁阀
#         log.print_log("压力桶中水量已达到最大值，停止注水。")

#     if fill_pressure_drum_with_water_task is not None and not fill_pressure_drum_with_water_task.done():
#         fill_pressure_drum_with_water_task.cancel()
#         fill_pressure_drum_with_water_task = asyncio.create_task(start())


async def fill_pressure_drum_with_water():
    """启动压力桶注水任务"""
    global fill_pressure_drum_with_water_task

    async def start():
        global forced_flush_ro_task
        try:
            # 打开压力桶进水电磁阀
            pins.pressure_bucket_to_water_inlet_solenoid_valve_switch.value(1)
            # 初始等待，确保开启状态已稳定
            await asyncio.sleep(3)
            while water_running:
                await asyncio.sleep(0.1)
            pins.pressure_bucket_to_water_inlet_solenoid_valve_switch.value(0)
            log.print_log("压力桶中水量已达到最大值，停止注水。")
            forced_flush_ro_task = asyncio.create_task(forced_flush_ro())  # 大流量强制冲洗RO膜

        except asyncio.CancelledError:
            pins.pressure_bucket_to_water_inlet_solenoid_valve_switch.value(0)
            # log.print_log("压力桶注水任务被取消。")
        except Exception as e:
            pins.pressure_bucket_to_water_inlet_solenoid_valve_switch.value(0)
            log.print_log(f"压力桶注水任务异常: {e}")

    # 如果任务存在且未完成，则取消任务
    if fill_pressure_drum_with_water_task is not None:
        if not fill_pressure_drum_with_water_task.done():
            fill_pressure_drum_with_water_task.cancel()
    # 创建新的任务
    fill_pressure_drum_with_water_task = asyncio.create_task(start())


def forced_flush_ro_task_stop():
    """强制冲洗RO膜任务停止"""
    global forced_flush_ro_task
    if forced_flush_ro_task is not None and not forced_flush_ro_task.done():
        forced_flush_ro_task.cancel()
        # log.print_log("强制冲洗RO膜任务已停止。")


async def forced_flush_ro():
    """强制冲洗RO膜"""
    # log.print_log(f"累计运行时间：{time_utils.ms_to_timestr_with_units(timer.elapsed())}")
    # 累计运行 x 分钟后才进行冲洗
    if timer.elapsed() < 1000 * 60 * config.get_config_value("ro_force_clean_time"):
        return

    try:
        # 开启冲洗前的准备
        led.set_color(255, 255, 0)  # 黄色
        pins.water_inlet_solenoid_valve_switch.value(1)  # 打开进水电磁阀
        pins.booster_pump_solenoid_valve_switch.value(1)  # 打开增压泵电磁阀
        await oled.display_status("冲洗")
        log.print_log("开始冲洗RO膜。")

        for _ in range(3):
            await asyncio.sleep(1.5)
            pins.wastewater_solenoid_valve_switch.value(1)  # 打开废水泵电磁阀
            await asyncio.sleep(1.5)
            pins.wastewater_solenoid_valve_switch.value(0)  # 关闭废水泵电磁阀
        else:
            pins.booster_pump_solenoid_valve_switch.value(0)  # 关闭增压泵电磁阀
            pins.water_inlet_solenoid_valve_switch.value(0)  # 关闭进水电磁阀
            timer.reset()  # 重置计时器
            led.clear()  # 灯光清除
            await oled.display_status("空闲")
            log.print_log("冲洗正常结束。")
    except asyncio.CancelledError:
        pins.pressure_bucket_to_water_inlet_solenoid_valve_switch.value(0)
        log.print_log("强制冲洗RO膜任务被取消。")
    except Exception as e:
        log.print_log(f"强制冲洗RO膜发生错误: {e}")
    finally:
        pins.wastewater_solenoid_valve_switch.value(0)  # 关闭废水泵电磁阀


async def after_booting_flush_ro():
    """开机时强制冲洗RO膜"""
    try:
        _done = False  # 程序是否完成标志位，True 表示完成，False 表示未完成
        while not _done:
            await waiting_for_water_intake_to_recover()  # 确保进水正常
            led.set_color(255, 255, 0)  # 黄色
            pins.water_inlet_solenoid_valve_switch.value(1)  # 打开进水电磁阀
            pins.booster_pump_solenoid_valve_switch.value(1)  # 打开增压泵电磁阀
            pins.wastewater_solenoid_valve_switch.value(1)  # 打开废水泵电磁阀
            await oled.display_status("冲洗")
            log.print_log("开机，开始冲洗RO膜。")
            for _ in range(18):  # 冲洗 18 秒
                if pins.low_pressure_switch.value() == 1:
                    log.print_log("冲洗过程中，进水压力不足，停止冲洗。")
                    pins.booster_pump_solenoid_valve_switch.value(0)  # 关闭增压泵电磁阀
                    pins.wastewater_solenoid_valve_switch.value(0)  # 关闭废水泵电磁阀
                    break
                await asyncio.sleep(1)
                watchdog.feed()  # 喂狗
            else:
                # 冲洗完成
                _done = True
                log.print_log("冲洗完成。")
    except Exception as e:
        log.print_log(f"开机时强制冲洗RO膜发生错误: {e}")
    finally:
        led.clear()  # 灯光清除
        pins.booster_pump_solenoid_valve_switch.value(0)  # 关闭增压泵电磁阀
        pins.wastewater_solenoid_valve_switch.value(0)  # 关闭废水泵电磁阀
        pins.water_inlet_solenoid_valve_switch.value(0)  # 关闭进水电磁阀
        await oled.display_status("空闲")


async def waiting_for_water_intake_to_recover():
    """等待进水恢复"""
    # 读取低压开关状态 1 表示压力未达标，0 表示压力达标
    while pins.low_pressure_switch.value() == 1:
        led.set_color(255, 0, 0)  # 红色
        await oled.display_status("缺水")
        await asyncio.sleep(2)  # 等待进水恢复
        watchdog.feed()  # 喂狗
    led.clear()  # 灯光清除


async def refresh_tds_value():
    # 刷新TDS值
    global purified_water_tds_value, wastewater_tds_value

    while True:
        try:
            # tds_value, temperature_vlaue = get_tds_and_temperature()
            purified_water_tds_value, wastewater_tds_value, temperature_vlaue = await get_tds_and_temperature()
            await oled.display_pure_water_tds_value(purified_water_tds_value)
            await oled.display_of_wastewater_tds_value(wastewater_tds_value)
            await oled.display_water_temperature(temperature_vlaue)
        except Exception as e:
            log.print_log(f"读取TDS传感器数据发生错误: {e}")
        finally:
            await asyncio.sleep(1)


async def timed_refresh_of_cartridge_usage_time():
    # 定时刷新滤芯使用时间
    while True:
        try:
            await oled.display_cartridge_pp_usage_time(cartridge_usage_time.get_pp_cartridge_usage_time())
            await oled.display_cartridge_udf_usage_time(cartridge_usage_time.get_udf_cartridge_usage_time())
            await oled.display_cartridge_cto_usage_time(cartridge_usage_time.get_cto_cartridge_usage_time())
            await oled.display_cartridge_ro_usage_time(cartridge_usage_time.get_ro_cartridge_usage_time())
            await oled.display_cartridge_t33_usage_time(cartridge_usage_time.get_t33_cartridge_usage_time())
        except Exception as e:
            log.print_log(f"定时刷新滤芯使用时间发生错误: {e}")
        finally:
            await asyncio.sleep(60)


async def pure_water_reflow_ro():
    # 启动纯水泡膜程序
    timeout = config.get_config_value("pure_water_ro_clean_timeout") * 60 * 1000  # 最大运行时间（单位：毫秒）
    start_time = time_utils.current_time_ms()

    target_tds = config.get_tds()  # 目标TDS值

    log.print_log(f"纯水洗膜程序启动，目标TDS值：{target_tds}")
    led.set_color(0, 255, 0)  # 绿色
    await oled.display_status("洗膜")

    # try:
    #     for _ in range(config.get_config_value("ro_pre_clean_time") * 2):  # 启动 10 秒,预冲洗RO膜
    #         pins.water_inlet_solenoid_valve_switch.value(1)  # 打开进水电磁阀
    #         pins.booster_pump_solenoid_valve_switch.value(1)  # 打开增压泵电磁阀
    #         pins.wastewater_solenoid_valve_switch.value(1)  # 打开废水泵电磁阀
    #         if pins.high_pressure_switch.value() == 0:
    #             # 开始制水，停止程序
    #             pins.wastewater_solenoid_valve_switch.value(0)  # 关闭废水泵电磁阀
    #             log.print_log("开始制水，预冲洗RO膜程序停止。")
    #             break
    #         if pins.low_pressure_switch.value() == 1:
    #             pins.water_inlet_solenoid_valve_switch.value(0)  # 关闭进水电磁阀
    #             pins.booster_pump_solenoid_valve_switch.value(0)  # 关闭增压泵电磁阀
    #             pins.wastewater_solenoid_valve_switch.value(0)  # 关闭废水泵电磁阀
    #             log.print_log("缺水，预冲洗RO膜程序停止。")
    #             break
    #         await asyncio.sleep(0.5)
    #     else:
    #         # 预冲洗RO膜完成
    #         pins.wastewater_solenoid_valve_switch.value(0)  # 关闭废水泵电磁阀
    #         pins.water_inlet_solenoid_valve_switch.value(0)  # 关闭进水电磁阀
    #         pins.booster_pump_solenoid_valve_switch.value(0)  # 关闭增压泵电磁阀
    #         log.print_log("预冲洗RO膜完成。")
    # except Exception as e:
    #     log.print_log(f"预冲洗RO膜任务发生错误: {e}")

    last_log_time = start_time

    try:
        pins.pressure_bucket_to_water_outlet_solenoid_valve_switch.value(1)  # 打开压力桶出水电磁阀

        while True:
            current_time = time_utils.current_time_ms()
            elapsed_time = time.ticks_diff(time_utils.current_time_ms(), start_time)

            # 每10秒输出当前TDS值的log，假设当前废水的TDS值存储在变量 wastewater_tds_value 中
            if time.ticks_diff(current_time, last_log_time) >= 10000:
                log.print_log("纯水回流中。")
                last_log_time = current_time

            if elapsed_time > timeout:
                # 超时，停止程序
                log.print_log("程序运行超时，程序停止。")
                await oled.display_status("超时")
                led.clear()  # 灯光清除
                break

            if wastewater_tds_value <= target_tds:
                # 废水的TDS值达到设定值，停止程序
                log.print_log("废水的TDS值达到设定值，程序停止。")
                await oled.display_status("完成")
                led.clear()  # 灯光清除
                break

            if pins.high_pressure_switch.value() == 0:
                # 开始制水，停止程序
                log.print_log("开始制水，纯水泡膜程序停止。")
                break

            await asyncio.sleep(1)  # 每 1 秒检查一次状态

    except Exception as e:
        log.print_log(f"纯水洗膜任务发生错误: {e}")
    finally:
        pins.pressure_bucket_to_water_outlet_solenoid_valve_switch.value(0)  # 关闭压力桶出水电磁阀
        final_time = time.ticks_diff(time_utils.current_time_ms(), start_time)
        log.print_log(f"程序结束，运行{final_time / 1000}秒.")
