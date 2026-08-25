import asyncio
import time

TIMEZONE_OFFSET = 8 * 3600  # 例如，UTC+8

# ---- 断电时钟备份（软件近似时钟） ----
TIME_STATE_FILE = "/time_state.txt"  # 上次已知的 UTC 时间戳（秒，自 2000-01-01 起）
MIN_VALID_TIMESTAMP = 365 * 24 * 3600  # 小于 1 年的时间戳视为未同步，不保存/不恢复
TIME_BACKUP_INTERVAL_S = 3600  # 时间备份周期（秒）


def current_time_ms():
    # 返回当前时间的毫秒数
    return time.ticks_ms()


def get_current_timestamp():
    """
    返回当前时间的时间戳。
    注意：根据您的MicroPython平台，time.time()可能采用不同的参考时间点（例如Unix纪元或其他）。
    """
    return time.time()


def calculate_time_difference(timestamp):
    """
    计算当前时间与给定时间戳之间的天数差值。

    参数:
        timestamp (float): 输入的时间戳

    返回:
        int: 当前时间与输入时间戳之间的天数差
    """
    current_timestamp = time.time()
    difference_seconds = current_timestamp - timestamp  # 计算秒数差值
    difference_days = difference_seconds / (24 * 3600)  # 将秒数转换为天数
    return int(difference_days)


def ms_to_timestr_with_units(milliseconds: int) -> str:
    """
    将毫秒转换为带单位的时间字符串。

    格式规则：
      - 如果小时 > 0，格式为 "Hh Mm Ss Mms"（例如 "1h 02m 03s 456ms"）
      - 如果小时为 0 且分钟 > 0，格式为 "Mm Ss Mms"（例如 "6m 12s 345ms"）
      - 如果小时和分钟都为 0，则格式为 "Ss Mms"（例如 "12s 345ms"）

    参数:
      milliseconds: 毫秒数（整数）

    返回:
      格式化后的时间字符串
    """
    total_seconds, ms = divmod(milliseconds, 1000)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)

    parts = []
    if hours:
        # 小时存在时，分钟和秒均采用两位数字格式
        parts.append(f"{hours}h")
        parts.append(f"{minutes:02}m")
        parts.append(f"{seconds:02}s")
    elif minutes:
        parts.append(f"{minutes}m")
        parts.append(f"{seconds:02}s")
    else:
        parts.append(f"{seconds}s")

    # parts.append(f"{ms:03}ms")
    return "".join(parts)


# 获取本地时间（带时区调整）
def get_local_time():
    # 获取当前时间戳并加上时区偏移
    current_time = time.localtime(time.time() + TIMEZONE_OFFSET)
    # 格式化时间
    formatted_time = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
        current_time[0],
        current_time[1],
        current_time[2],  # 年-月-日
        current_time[3],
        current_time[4],
        current_time[5],  # 时:分:秒
    )
    return formatted_time


def seconds_until_next_hour():
    """获取到下一个整点剩余的秒数"""
    current_time = time.localtime(time.time() + TIMEZONE_OFFSET)
    seconds_since_last_hour = current_time[4] * 60 + current_time[5]
    seconds_until_next_hour = 3600 - seconds_since_last_hour
    return seconds_until_next_hour


def seconds_until_4_am():
    """获取距离明天凌晨4点还有多少秒"""
    # 当前时间（加上时区偏移）
    now = time.time() + TIMEZONE_OFFSET
    lt = time.localtime(now)

    # 构造今天凌晨4点的时间元组，只取8个元素：(year, month, mday, hour, minute, second, weekday, yearday)
    target_today = (lt[0], lt[1], lt[2], 4, 0, 0, lt[6], lt[7])
    target_today_ts = time.mktime(target_today)

    if now < target_today_ts:
        # 当前时间还没到今天凌晨4点
        target_ts = target_today_ts
    else:
        # 当前时间已经过了今天凌晨4点，则目标为明天凌晨4点
        # 先构造明天的日期：给今天凌晨4点的时间戳加一天
        tomorrow = time.localtime(target_today_ts + 86400)
        target_tomorrow = (tomorrow[0], tomorrow[1], tomorrow[2], 4, 0, 0, tomorrow[6], tomorrow[7])
        target_ts = time.mktime(target_tomorrow)

    return int(target_ts - now)


# ---- 断电时钟备份（软件近似时钟） ----
def save_time_to_flash():
    """
    将当前 UTC 时间戳写入 flash，供断电后恢复近似时钟。
    未同步（时间异常小）时不保存，避免用垃圾值覆盖有效备份。
    """
    now = int(time.time())
    if now < MIN_VALID_TIMESTAMP:
        return
    try:
        with open(TIME_STATE_FILE, "w") as file:
            file.write(str(now))
    except OSError:
        pass  # flash 写入失败不影响主流程


def load_saved_time():
    """读取上次保存的 UTC 时间戳；文件缺失或值无效时返回 None"""
    try:
        with open(TIME_STATE_FILE, "r") as file:
            value = int(file.read().strip())
        return value if value >= MIN_VALID_TIMESTAMP else None
    except (OSError, ValueError):
        return None


def apply_saved_time():
    """
    断电后 RTC 丢失时，用上次保存的时间恢复近似时钟。
    适用场景：
      - RTC 已清零（上电复位等）：备份值 + 开机以来运行秒数；
      - RTC 值异常（与备份相差约 8 小时，疑似时区污染）：用备份纠正。
    近似误差 = 断电时长；NTP 同步成功后自动校准。返回是否已应用。
    """
    import machine

    def _set_rtc(approx):
        # 必须写入 UTC 分量：gmtime 与 ntptime 一致（纯 UTC）；
        # 个别固件的 localtime 会带本地时区偏移（如 UTC+8），写入后回读校验，失败则回退
        t = time.gmtime(approx)
        # 星期字段与 ntptime.settime() 保持一致
        machine.RTC().datetime((t[0], t[1], t[2], t[6] + 1, t[3], t[4], t[5], 0))
        if abs(time.time() - approx) > 3600:
            t = time.localtime(approx)
            machine.RTC().datetime((t[0], t[1], t[2], t[6] + 1, t[3], t[4], t[5], 0))
        return abs(time.time() - approx) <= 3600

    try:
        saved = load_saved_time()
        if saved is None:
            return False
        rtc_now = int(time.time())

        if rtc_now >= MIN_VALID_TIMESTAMP:
            # RTC 里已有"看起来有效"的时间：与备份比较判断是否被污染
            diff = abs(rtc_now - saved)
            if abs(diff - 8 * 3600) <= 2 * 3600:
                # 与备份相差约 8 小时 = 时区污染特征（备份每小时更新，正常差值不会接近 8h）
                import log  # 延迟导入，避免循环依赖（log 依赖 time_utils）
                log.print_log(f"检测到 RTC 时间异常（与备份相差约 8 小时），用备份纠正: {saved}")
                approx = saved
            else:
                return False  # RTC 正常（软复位等场景保留值有效），无需恢复
        else:
            # RTC 已清零（上电复位）：备份值 + 开机以来运行秒数
            approx = saved + rtc_now

        if not _set_rtc(approx):
            return False  # 写入后回读校验失败，放弃（等待 NTP 校准）
        return True
    except Exception:
        return False


async def periodic_time_backup():
    """
    周期备份当前时间到 flash（默认每小时一次），
    断电后时间误差 = 断电时长 + 最多一个备份周期。
    """
    while True:
        await asyncio.sleep(TIME_BACKUP_INTERVAL_S)
        save_time_to_flash()
