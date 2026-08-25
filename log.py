import os
import time
import asyncio

from io import StringIO

import pins
import time_utils

LOG_SAVE_PATH = "/logs"
LOG_FILE_PATH = "/logs/log.txt"
MAX_LOG_SIZE = 1024 * 200  # 设置最大日志文件大小为200KB
MAX_LOG_HISTORY = 5  # 保留最近5个日志文件


# 确保日志目录存在（新烧录的设备没有 /logs，否则日志会静默丢失）
try:
    os.mkdir(LOG_SAVE_PATH)
except OSError:
    pass

from time_utils import TIMEZONE_OFFSET  # 统一时区偏移定义

current_log_buffer = StringIO()


def get_time():
    # 获取当前时间戳
    current_time = time.localtime(time.time() + TIMEZONE_OFFSET)  # 返回一个包含本地时间的元组

    # 获取当前的微秒部分
    micros = time.ticks_us() % 1000000  # 取当前时间戳的微秒部分

    # 格式化为人类可读的字符串（包括微秒）
    readable_time = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}.{:06d}".format(
        current_time[0],  # 年
        current_time[1],  # 月
        current_time[2],  # 日
        current_time[3],  # 时
        current_time[4],  # 分
        current_time[5],  # 秒
        micros,  # 微秒
    )
    return readable_time


def format_time(t):
    """
    将时间元组格式化为字符串。
    :param t: 时间元组 (year, month, day, hour, minute, second, weekday, yearday)
    :return: 格式化后的时间字符串，例如 "20250119235836"
    """
    return f"{t[0]:04d}{t[1]:02d}{t[2]:02d}{t[3]:02d}{t[4]:02d}{t[5]:02d}"


def file_exists(file_path):
    """
    检查文件是否存在。
    """
    try:
        os.stat(file_path)
        return True
    except OSError:
        return False


def get_state():
    # 延迟导入，避免与 water.py 形成循环依赖
    import water

    state_list = []

    state_list.append("进水√" if pins.low_pressure_switch.value() == 0 else "进水×")
    state_list.append("制水√" if pins.high_pressure_switch.value() == 0 else "制水×")
    state_list.append("压力桶进水√" if pins.pressure_bucket_to_water_inlet_solenoid_valve_switch.value() == 1 else "压力桶进水×")
    state_list.append("压力桶出水√" if pins.pressure_bucket_to_water_outlet_solenoid_valve_switch.value() == 1 else "压力桶出水×")
    state_list.append(f"纯水TDS:{water.purified_water_tds_value}")
    state_list.append(f"废水TDS:{water.wastewater_tds_value}")
    state_list.append(f"累计运行:{time_utils.ms_to_timestr_with_units(water.timer.elapsed())}")

    return "|".join(state_list)


async def cleanup_old_logs():
    """删除旧的日志文件，保持最大数量的日志文件"""
    # 获取所有日志文件
    log_files = [f for f in os.listdir(LOG_SAVE_PATH) if f.startswith("log_") and f.endswith(".txt")]

    # 按修改时间排序（从旧到新）
    log_files.sort(key=lambda x: os.stat(f"{LOG_SAVE_PATH}/{x}")[9])  # 使用 st_mtime（修改时间）

    # 删除多余的日志文件
    while len(log_files) > MAX_LOG_HISTORY:
        old_log = log_files.pop(0)  # 删除最旧的日志文件
        os.remove(f"{LOG_SAVE_PATH}/{old_log}")
        print_log(f"删除日志文件: {old_log}")


async def check_and_rotate_log():
    """
    定期检查闪存中的日志文件大小，超过阈值时进行轮换：
      1. 将当前日志文件重命名保存到历史中
      2. 生成新的日志文件
      3. 清理多余历史日志
    """
    while True:
        try:
            if file_exists(LOG_FILE_PATH):
                # 获取文件大小
                file_size = os.stat(LOG_FILE_PATH)[6]  # st_size 是元组的第 6 个元素
                if file_size >= MAX_LOG_SIZE:
                    timestamp = format_time(time.localtime(time.time() + TIMEZONE_OFFSET))
                    rotated_log_path = f"{LOG_SAVE_PATH}/log_{timestamp}.txt"
                    os.rename(LOG_FILE_PATH, rotated_log_path)
                    print_log(f"日志文件轮换: {LOG_FILE_PATH} -> {rotated_log_path}")
                    await cleanup_old_logs()  # 删除旧日志文件
        except Exception as e:
            print_log(f"日志轮换失败: {e}")
        finally:
            await asyncio.sleep(60)  # 每1分钟检查一次


def write_log(msg):
    """
    将日志消息写入内存中的日志缓冲区
    """
    global current_log_buffer
    current_log_buffer.write(f"{msg}\n")


def print_log(msg):
    """
    同步打印日志信息，并写入内存日志
    """
    msg = f"[{get_time()}] - [{get_state()}] - {msg}"
    print(msg)
    write_log(msg)


async def flush_logs_to_flash():
    """
    定期（每分钟）将内存日志缓冲区中的内容写入闪存，
    写入后清空内存日志缓冲区，从而避免因断电丢失日志
    """
    global current_log_buffer
    while True:
        try:
            log_content = current_log_buffer.getvalue()
            if log_content:
                # 以追加模式写入闪存
                with open(LOG_FILE_PATH, "a") as f:
                    f.write(log_content)
                # 清空内存日志缓冲区
                current_log_buffer = StringIO()
                # print(f"[{get_time()}] 已将内存日志写入闪存")
        except Exception as e:
            print(f"[{get_time()}] 写入闪存失败: {e}")
        await asyncio.sleep(15)  # 每15秒执行一次
