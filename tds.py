import time

import threadsafe_context
import log

from pins import uart

TDS_INVALID = 999  # TDS 读取失败占位值（解析失败/无响应时返回，不代表真实水质）

# TDS 错误日志限流（避免传感器故障时每秒刷屏）
ERROR_LOG_INTERVAL_MS = 60000
_last_error_log_time = 0


def _should_log_error():
    """错误日志限流：两次记录至少间隔 ERROR_LOG_INTERVAL_MS"""
    global _last_error_log_time
    now = time.ticks_ms()
    if time.ticks_diff(now, _last_error_log_time) >= ERROR_LOG_INTERVAL_MS:
        _last_error_log_time = now
        return True
    return False


# 计算校验和函数
def calculate_checksum(data):
    return sum(data) & 0xFF


# 构造发送帧
def build_frame(command, channel=0x01, data=None):
    if data is None:
        data = [0x00] * 3  # 默认填充数据
    length = 1 + 1 + len(data) + 1  # Length + Command + Data + Checksum
    frame = [0x55, length, command] + [channel] + data
    checksum = calculate_checksum(frame)
    frame.append(checksum)
    return bytes(frame)


# 解析接收帧
def parse_frame(frame):
    if len(frame) < 5 or frame[0] != 0x55:
        return None, "Invalid frame"

    length = frame[1]
    expected_length = length + 1  # 帧总长度 = 长度字段 + 校验位
    if len(frame) != expected_length:
        return None, f"Length mismatch: Expected {expected_length}, Got {len(frame)}"

    checksum = calculate_checksum(frame[:-1])
    if checksum != frame[-1]:
        return None, "Checksum error"

    command = frame[2]
    data = frame[3:-1]
    return {"command": command, "data": data}, None


# 发送命令并读取响应
def send_command(command, channel=0x01, data=None):
    frame = build_frame(command, channel, data)
    # log.print_log_sync(f"发送帧: {[hex(b) for b in frame]} 长度: {len(frame)}")
    uart.write(frame)

    time.sleep(0.5)  # 等待响应

    if uart.any():
        response = uart.read()
        # log.print_log_sync(f"接收帧: {[hex(b) for b in response]} 长度: {len(response)}")
        parsed, error = parse_frame(response)
        # if error:
        #     log.print_log_sync(f"解析错误:, {error}")
        # else:
        #     log.print_log_sync(f"解析结果:, {parsed}")
        return parsed
    else:
        if _should_log_error():
            log.print_log("未收到TDS传感器响应")
        return None


def get_tds_and_temperature_sync():
    # 默认值（读取失败时的占位）
    default_tds1, default_tds2 = TDS_INVALID, TDS_INVALID
    default_temp1, default_temp2 = 99, 99

    def parse_channel_result(result, channel):
        """解析单个通道的数据"""
        if result and "data" in result:
            data = result["data"]
            if len(data) >= 6:
                conductivity = (data[1] << 8 | data[2]) / 10  # 电导率值
                tds = int(conductivity * 0.5)  # TDS值
                temperature = (data[3] << 8 | data[4]) / 10  # 温度值
                # log.print_log(f"通道{channel} -> 电导率: {conductivity} µs/cm, TDS: {tds} mg/l, 温度: {temperature} °C")
                return tds, temperature
        return None, None

    tds1, temp1 = parse_channel_result(send_command(0x05, channel=0x01), channel=1)
    tds2, temp2 = parse_channel_result(send_command(0x05, channel=0x02), channel=2)

    # 使用默认值填充可能解析失败的情况
    tds1 = tds1 if tds1 is not None else default_tds1
    temp1 = temp1 if temp1 is not None else default_temp1
    tds2 = tds2 if tds2 is not None else default_tds2
    temp2 = temp2 if temp2 is not None else default_temp2

    # 计算平均温度并四舍五入
    average_temperature = round((temp1 + temp2) / 2)
    return tds1, tds2, average_temperature


async def get_tds_and_temperature():
    return await threadsafe_context.external_hardware.assign(get_tds_and_temperature_sync)
