import asyncio
import time

import pins
import watchdog
import screen_ui
import time_utils
import config
import cartridge_usage_time
import countdown
import log

from pins import rgb_led
from tds import get_tds_and_temperature, TDS_INVALID, get_recent_pure_tds
from timer import Timer
from ws2812b import WS2812B


timer = Timer()  # 计时器
forced_flush_ro_task = None  # 强制冲洗RO膜任务事件
led = WS2812B(1, rgb_led)  # 灯带对象

purified_water_tds_value = 0  # 纯水TDS值
wastewater_tds_value = 0  # 废水TDS值
tds_values_ready = False  # 是否已成功读取到首批TDS数据
_last_tds_error_log = 0  # TDS 错误日志限流时间戳（ticks_ms）


water_running = False  # False 表示停止，True 表示正在制水
filling_bucket = False  # True = 压力桶进水阀已打开（制水期间纯水TDS达标时注水）

# 注水 TDS 防抖：超标需超过阈值+余量，并持续确认时长后才停止注水（避免阈值附近波动导致阀门频繁开关）
FILL_TDS_HYSTERESIS = 3  # 关阀超标余量（ppm）：TDS > 阈值+余量 才视为真超标
FILL_TDS_EXCEED_CONFIRM_MS = 3000  # 超标持续确认时长（毫秒）
_fill_exceed_since = 0  # 超标开始时刻（ticks_ms）


async def start_water_production():
    """制水程序主循环"""
    global water_running
    global forced_flush_ro_task
    global filling_bucket

    while True:
        watchdog.feed()  # 喂狗
        low_pressure = pins.low_pressure_switch.value()  # 1 表示压力不足
        high_pressure = pins.high_pressure_switch.value()  # 0 表示压力未达标

        if low_pressure == 1:
            # 缺水状态：停止制水（含停止注水），并等待进水恢复
            if water_running:
                await stop_water_actions()
                water_running = False
            filling_bucket = False
            log.print_log("缺水，停止制水.")
            forced_flush_ro_task_stop()  # 停止强制冲洗RO膜任务
            await waiting_for_water_intake_to_recover()  # 等待进水恢复
            await screen_ui.display_status("空闲")
            log.print_log("进水压力达标，可以开始制水。")

        elif high_pressure == 0 and not water_running:
            # 水龙头打开：开始制水（桶阀初始关闭，制水循环中按 TDS 决定是否注水）
            forced_flush_ro_task_stop()  # 停止强制冲洗RO膜任务
            filling_bucket = False
            await start_water_actions()
            water_running = True

        elif high_pressure == 1 and water_running:
            # 水龙头关闭：停止制水（含停止注水），进入强制冲洗 + 纯水泡膜流程
            await stop_water_actions()
            water_running = False
            filling_bucket = False
            forced_flush_ro_task = asyncio.create_task(forced_flush_ro())  # 大流量强制冲洗RO膜
            asyncio.create_task(countdown.start(pure_water_reflow_ro))
            log.print_log("水龙头关闭，停止制水.")

        elif water_running:
            # 制水中：纯水 TDS 达标则向压力桶注水，不达标/不可信则停止注水（带防抖）
            tds_ok = fill_tds_ok()
            if tds_ok is not None and tds_ok != filling_bucket:
                pins.pressure_bucket_to_water_inlet_solenoid_valve_switch.value(1 if tds_ok else 0)
                filling_bucket = tds_ok
                if tds_ok:
                    log.print_log("纯水TDS达标，开始向压力桶注水.")
                else:
                    log.print_log("纯水TDS不达标或不可信，停止向压力桶注水.")

        await asyncio.sleep(0.5)


async def start_water_actions():
    """启动制水的操作"""
    countdown.stop_event.set()  # 停止倒计时任务

    pins.water_inlet_solenoid_valve_switch.value(1)  # 打开进水电磁阀
    pins.pressure_bucket_to_water_outlet_solenoid_valve_switch.value(0)  # 关闭压力桶出水电磁阀
    pins.pressure_bucket_to_water_inlet_solenoid_valve_switch.value(0)  # 关闭压力桶进水电磁阀（制水循环中按纯水TDS决定是否注水）
    pins.booster_pump_solenoid_valve_switch.value(1)  # 打开增压泵电磁阀

    timer.start()  # 开始计时
    led.set_color(199, 18, 184)  # 设置LED为紫色，表示制水中
    await screen_ui.display_status("制水")
    log.print_log("开始制水.")


def fill_tds_ok():
    """制水期间判断纯水 TDS 是否达标注水（防抖版）：
    - ≤ 阈值：达标（立即开阀注水）
    - 阈值 ~ 阈值+余量（中性带）：保持当前状态，不动作
    - > 阈值+余量 且持续确认时长：不达标（停止注水）
    - 实时读取失败用最近可信值；无可信值视为不达标
    返回值：True=达标，False=不达标，None=保持现状"""
    global _fill_exceed_since
    fill_tds = config.get_fill_tds()
    tds_value = purified_water_tds_value
    if tds_value >= TDS_INVALID:
        tds_value = get_recent_pure_tds()
    if tds_value >= TDS_INVALID:
        # 无可信值：视为不达标（防抖计时复位，避免误算持续时长）
        _fill_exceed_since = 0
        return False
    if tds_value <= fill_tds:
        _fill_exceed_since = 0  # 已恢复达标：复位超标计时
        return True
    if tds_value <= fill_tds + FILL_TDS_HYSTERESIS:
        # 中性带：保持当前状态（不动作、不计时）
        return None
    # 真超标：持续确认后才停止注水
    if _fill_exceed_since == 0:
        _fill_exceed_since = time.ticks_ms()
    elif time.ticks_diff(time.ticks_ms(), _fill_exceed_since) >= FILL_TDS_EXCEED_CONFIRM_MS:
        _fill_exceed_since = 0
        return False
    return None


async def stop_water_actions():
    """停止制水的操作"""
    countdown.stop_event.clear()  # 重置倒计时停止事件

    pins.booster_pump_solenoid_valve_switch.value(0)  # 关闭增压泵电磁阀
    pins.pressure_bucket_to_water_outlet_solenoid_valve_switch.value(0)  # 关闭压力桶出水电磁阀
    pins.pressure_bucket_to_water_inlet_solenoid_valve_switch.value(0)  # 关闭压力桶进水电磁阀
    pins.water_inlet_solenoid_valve_switch.value(0)  # 关闭进水电磁阀

    timer.stop()  # 停止计时
    led.clear()  # 熄灭LED
    await screen_ui.display_status("空闲")


def forced_flush_ro_task_stop():
    """强制冲洗RO膜任务停止"""
    global forced_flush_ro_task
    if forced_flush_ro_task is not None and not forced_flush_ro_task.done():
        forced_flush_ro_task.cancel()
        # log.print_log("强制冲洗RO膜任务已停止。")


async def forced_flush_ro():
    """强制冲洗RO膜"""
    # 累计运行 x 分钟后才进行冲洗
    if timer.elapsed() < 1000 * 60 * config.get_config_value("ro_force_clean_time"):
        return

    try:
        # 开启冲洗前的准备
        led.set_color(255, 255, 0)  # 黄色
        pins.water_inlet_solenoid_valve_switch.value(1)  # 打开进水电磁阀
        pins.booster_pump_solenoid_valve_switch.value(1)  # 打开增压泵电磁阀
        await screen_ui.display_status("冲洗")
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
            await screen_ui.display_status("空闲")
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
            await screen_ui.display_status("冲洗")
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
        await screen_ui.display_status("空闲")


async def waiting_for_water_intake_to_recover():
    """等待进水恢复"""
    # 读取低压开关状态 1 表示压力未达标，0 表示压力达标
    while pins.low_pressure_switch.value() == 1:
        led.set_color(255, 0, 0)  # 红色
        await screen_ui.display_status("缺水")
        await asyncio.sleep(2)  # 等待进水恢复
        watchdog.feed()  # 喂狗
    led.clear()  # 灯光清除


async def refresh_tds_value():
    # 刷新TDS值
    global purified_water_tds_value, wastewater_tds_value, tds_values_ready, _last_tds_error_log

    while True:
        try:
            purified_water_tds_value, wastewater_tds_value, temperature_vlaue = await get_tds_and_temperature()
            tds_values_ready = True  # 首批 TDS 数据已就绪
            await screen_ui.display_pure_water_tds_value(purified_water_tds_value)
            await screen_ui.display_of_wastewater_tds_value(wastewater_tds_value)
            await screen_ui.display_water_temperature(temperature_vlaue)
        except Exception as e:
            # 限流：避免传感器故障时每秒刷屏日志
            now = time.ticks_ms()
            if time.ticks_diff(now, _last_tds_error_log) >= 60000:
                _last_tds_error_log = now
                log.print_log(f"读取TDS传感器数据发生错误: {e}")
        finally:
            await asyncio.sleep(1)


async def timed_refresh_of_cartridge_usage_time():
    # 定时刷新滤芯使用时间
    while True:
        try:
            await screen_ui.display_cartridge_pp_usage_time(cartridge_usage_time.get_pp_cartridge_usage_time())
            await screen_ui.display_cartridge_udf_usage_time(cartridge_usage_time.get_udf_cartridge_usage_time())
            await screen_ui.display_cartridge_cto_usage_time(cartridge_usage_time.get_cto_cartridge_usage_time())
            await screen_ui.display_cartridge_ro_usage_time(cartridge_usage_time.get_ro_cartridge_usage_time())
            await screen_ui.display_cartridge_t33_usage_time(cartridge_usage_time.get_t33_cartridge_usage_time())
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
    await screen_ui.display_status("洗膜")

    last_log_time = start_time

    try:
        pins.pressure_bucket_to_water_outlet_solenoid_valve_switch.value(1)  # 打开压力桶出水电磁阀

        # 等待首批 TDS 数据就绪（最多 30 秒），避免初值 0 被误判为“已达标”
        wait_start = time_utils.current_time_ms()
        while not tds_values_ready:
            if time.ticks_diff(time_utils.current_time_ms(), wait_start) > 30000:
                log.print_log("等待 TDS 数据超时，终止本次纯水泡膜。")
                return
            if pins.high_pressure_switch.value() == 0:
                log.print_log("开始制水，纯水泡膜程序停止。")
                return
            await asyncio.sleep(1)

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
                await screen_ui.display_status("超时")
                led.clear()  # 灯光清除
                break

            if wastewater_tds_value <= target_tds:
                # 废水的TDS值达到设定值，停止程序
                log.print_log("废水的TDS值达到设定值，程序停止。")
                await screen_ui.display_status("完成")
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
