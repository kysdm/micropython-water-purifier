import asyncio
import time

import log
import font
import threadsafe_context
import ssd1306

from machine import Pin
from machine import SoftI2C

# from pins import i2c


# 屏幕的宽度和高度
width = 128
height = 64


# OLED 延迟初始化：模块导入时不访问 I2C，避免硬件缺失导致开机崩溃
i2c = None
display = None
_oled_ready = False
_last_oled_error_log = 0  # OLED 初始化失败日志限流时间戳


def _ensure_display():
    """确保 I2C 与 OLED 已初始化；硬件缺失时返回 False（不阻塞主流程）"""
    global i2c, display, _oled_ready, _last_oled_error_log
    if _oled_ready:
        return True
    try:
        i2c = SoftI2C(sda=Pin(1), scl=Pin(2))
        display = ssd1306.SSD1306_I2C(width, height, i2c)
        _oled_ready = True
        return True
    except OSError as e:
        now = time.ticks_ms()
        if time.ticks_diff(now, _last_oled_error_log) >= 60000:  # 限流：每分钟最多 1 条
            _last_oled_error_log = now
            log.print_log(f"OLED 初始化失败: {e}")
        return False


# 屏幕亮度降级标志（供 lower_screen_brightness 使用）
lower_screen_brightness_tag = False

# ---- OLED 防烧屏配置 ----
SCREEN_BRIGHTNESS = 0x4D  # 正常显示亮度（原 0x7F，降至约 30%，减缓像素老化）
IDLE_TIMEOUT_S = 5 * 60  # 纯空闲模式：无运行状态且空闲超过该时长（秒）后自动熄屏
ORBIT_INTERVAL_S = 5 * 60  # 像素偏移间隔（秒）
ORBIT_POSITIONS = [(0, 0), (1, 0), (2, 0), (2, 1), (1, 1), (0, 1)]  # 偏移循环位置（横向 3 档 x 纵向 2 档）
ACTIVE_STATUSES = ("制水", "冲洗", "洗膜", "缺水")  # 需要保持屏幕点亮的运行状态（自动点亮并保持）

_shift_x = 0  # 当前像素偏移量
_shift_y = 0
_screen_powered = True  # 屏幕供电状态
_screen_wake = False  # 是否因运行状态（制水/冲洗等）需要保持屏幕点亮
_screen_grace_until = 0  # 空闲后允许继续点亮的截止时刻（ticks_ms）
_last_values = {}  # 最近一次各显示项的值，偏移/唤醒后用于重绘


def reset_i2c_bus(scl_pin, sda_pin, num_clocks=9):
    """
    复位 SoftI2C 总线
    参数:
      scl_pin -- SCL 引脚号
      sda_pin -- SDA 引脚号
      num_clocks -- 产生时钟脉冲的数量，默认 9 个
    """
    # 将 SCL 和 SDA 设置为 GPIO 输出，并启用内部上拉电阻
    scl = Pin(scl_pin, Pin.OUT, Pin.PULL_UP)
    sda = Pin(sda_pin, Pin.OUT, Pin.PULL_UP)

    # 保证总线空闲状态（两线高电平）
    scl.value(1)
    sda.value(1)
    time.sleep_ms(5)

    # 产生时钟脉冲，尝试释放被卡住的设备
    for i in range(num_clocks):
        scl.value(0)
        time.sleep_us(5)
        scl.value(1)
        time.sleep_us(5)

    # 生成停止条件：在 SCL 为高时，让 SDA 从低到高变化
    scl.value(1)
    sda.value(0)
    time.sleep_us(5)
    sda.value(1)
    time.sleep_us(5)


def display_show():
    global i2c, display

    if not _ensure_display():
        return

    try:
        display.show()
        # 正常使用 oled
    except OSError as e:
        log.print_log(f"I2C 通信错误: {e}")
        reset_i2c_bus(2, 1)
        # 复位后重新初始化 SoftI2C 对象
        i2c = SoftI2C(sda=Pin(1), scl=Pin(2))
        display = ssd1306.SSD1306_I2C(width, height, i2c)


def draw_chinese(ch_str, x_axis, y_axis):
    if not _ensure_display():
        return
    offset_ = 0
    for k in ch_str:
        code = 0x00  # 将中文转成16进制编码
        data_code = k.encode("utf-8")

        # 根据编码长度处理
        if len(data_code) == 3:  # 中文字符（3 字节编码）
            code |= data_code[0] << 16
            code |= data_code[1] << 8
            code |= data_code[2]
        elif len(data_code) == 2:  # 特殊字符（如 °，2 字节编码）
            code |= data_code[0] << 8
            code |= data_code[1]

        byte_data = font.byte2[code]
        for y in range(0, 16):
            a_ = bin(byte_data[y]).replace("0b", "")
            while len(a_) < 8:
                a_ = "0" + a_

            b_ = bin(byte_data[y + 16]).replace("0b", "")
            while len(b_) < 8:
                b_ = "0" + b_
            for x in range(0, 8):
                display.pixel(x_axis + x + offset_ + _shift_x, y + y_axis + _shift_y, int(a_[x]))  # 文字的上半部分
                display.pixel(x_axis + x + offset_ + 8 + _shift_x, y + y_axis + _shift_y, int(b_[x]))  # 文字的下半部分

        offset_ += 16


def draw_chinese_small(ch_str, x_axis, y_axis):
    if not _ensure_display():
        return
    offset_ = 0
    for k in ch_str:
        code = 0x00  # 将中文转成16进制编码
        data_code = k.encode("utf-8")
        code |= data_code[0] << 16
        code |= data_code[1] << 8
        code |= data_code[2]
        byte_data = font.byte2[code]  # 获取12x12点阵数据

        for y in range(0, 12):  # 调整为12行
            a_ = bin(byte_data[y]).replace("0b", "")
            while len(a_) < 8:
                a_ = "0" + a_

            b_ = bin(byte_data[y + 12]).replace("0b", "")  # 每行2字节
            while len(b_) < 8:
                b_ = "0" + b_

            for x in range(0, 8):
                display.pixel(x_axis + x + offset_ + _shift_x, y + y_axis + _shift_y, int(a_[x]))  # 文字的左半部分
                display.pixel(x_axis + x + offset_ + 8 + _shift_x, y + y_axis + _shift_y, int(b_[x]))  # 文字的右半部分

        offset_ += 12  # 调整水平偏移量为12


def draw_english(text, x_axis, y_axis):
    """
    绘制英文字符。
    :param text: 英文字符串
    :param x_axis: 起始 x 坐标
    :param y_axis: 起始 y 坐标
    """
    if not _ensure_display():
        return
    offset_ = 0  # 用于字符之间的偏移量
    for char in text:
        ascii_code = ord(char)  # 获取字符的 ASCII 编码
        #       print(ascii_code)
        byte_data = font.byte2.get(ascii_code, [0] * 16)  # 获取字符点阵数据（8x16 位图）

        # 绘制每一行的像素
        for y in range(0, 16):  # 高度 16 行
            a_ = bin(byte_data[y]).replace("0b", "")  # 将字节转换为二进制
            while len(a_) < 8:  # 手动补齐至 8 位
                a_ = "0" + a_

            for x in range(0, 8):  # 宽度 8 列
                display.pixel(x_axis + x + offset_ + _shift_x, y + y_axis + _shift_y, int(a_[x]))  # 绘制上半部分的像素

        offset_ += 8  # 每个字符宽度为 8 像素


def draw_english_small(text, x_axis, y_axis):
    """
    绘制英文字符。
    :param text: 英文字符串
    :param x_axis: 起始 x 坐标
    :param y_axis: 起始 y 坐标
    """
    if not _ensure_display():
        return
    offset_ = 0  # 用于字符之间的偏移量
    for char in text:
        ascii_code = f"{ord(char)}-s"  # 获取字符的 ASCII 编码
        byte_data = font.byte2.get(ascii_code, [0] * 12)  # 获取字符点阵数据（8x16 位图）

        # 绘制每一行的像素
        for y in range(0, 12):  # 高度 12 行
            a_ = bin(byte_data[y]).replace("0b", "")  # 将字节转换为二进制
            while len(a_) < 8:  # 手动补齐至 8 位
                a_ = "0" + a_

            for x in range(0, 8):  # 宽度 8 列
                display.pixel(x_axis + x + offset_ + _shift_x, y + y_axis + _shift_y, int(a_[x]))  # 绘制上半部分的像素

        offset_ += 8  # 每个字符宽度为 8 像素


def draw_vertical_line(x, y_start, y_end):
    """
    绘制一条竖线。
    :param x: 竖线的 X 坐标
    :param y_start: 竖线的起始 Y 坐标
    :param y_end: 竖线的结束 Y 坐标
    """
    if not _ensure_display():
        return
    for y in range(y_start, y_end):
        display.pixel(x + _shift_x, y + _shift_y, 1)  # 设定竖线上的每个像素为亮


def _draw_static_layout():
    if not _ensure_display():
        return
    # 固定不变的部分（带偏移量，供像素偏移防烧屏）
    draw_english("PP", 2, 0)
    draw_english("UDF", 2, 12)
    draw_english("CTO", 2, 24)
    draw_english("RO", 2, 36)
    draw_english("T", 2, 49)
    draw_english_small("33", 9, 51)

    draw_english_small(":", 25, 0)
    draw_english_small(":", 25, 12)
    draw_english_small(":", 25, 24)
    draw_english_small(":", 25, 36)
    draw_english_small(":", 25, 49)

    draw_chinese_small("纯水", 67, 2)
    draw_chinese_small("废水", 67, 18)
    draw_chinese_small("温度", 67, 34)
    draw_chinese_small("状态", 67, 50)
    draw_english_small(":", 91, 2)
    draw_english_small(":", 91, 18)
    draw_english_small(":", 91, 34)
    draw_english_small(":", 91, 50)
    # 温度
    draw_chinese("°", 113, 32)
    draw_english("C", 119, 32)

    draw_vertical_line(65, 0, height)
    # 上边框（偏移后右侧/下侧边框会被裁剪 1~2 像素，属预期）
    display.hline(_shift_x, _shift_y, width, 1)
    display.hline(_shift_x, _shift_y + height - 1, width, 1)
    display.vline(_shift_x, _shift_y, height, 1)
    display.vline(_shift_x + width - 1, _shift_y, height, 1)


def init():
    if not _ensure_display():
        return
    _draw_static_layout()
    display.contrast(SCREEN_BRIGHTNESS)  # 降低默认亮度，减缓像素老化

    display_show()


async def display_cartridge_pp_usage_time(var):
    def display_cartridge_pp_usage_time_sync(var):
        """显示PP滤芯使用时间"""
        var = int(var)
        _last_values["pp"] = var
        draw_english_small(f"{var:4}", 31, 2)
        display_show()

    await threadsafe_context.external_hardware.assign(display_cartridge_pp_usage_time_sync, var=var)


async def display_cartridge_udf_usage_time(var):
    def display_cartridge_udf_usage_time_sync(var):
        """显示UDF滤芯使用时间"""
        var = int(var)
        _last_values["udf"] = var
        draw_english_small(f"{var:4}", 31, 14)
        display_show()

    await threadsafe_context.external_hardware.assign(display_cartridge_udf_usage_time_sync, var=var)


async def display_cartridge_cto_usage_time(var):
    def display_cartridge_cto_usage_time_sync(var):
        """显示CTO滤芯使用时间"""
        var = int(var)
        _last_values["cto"] = var
        draw_english_small(f"{var:4}", 31, 26)
        display_show()

    await threadsafe_context.external_hardware.assign(display_cartridge_cto_usage_time_sync, var=var)


async def display_cartridge_ro_usage_time(var):
    def display_cartridge_ro_usage_time_sync(var):
        """显示RO滤芯使用时间"""
        var = int(var)
        _last_values["ro"] = var
        draw_english_small(f"{var:4}", 31, 38)
        display_show()

    await threadsafe_context.external_hardware.assign(display_cartridge_ro_usage_time_sync, var=var)


async def display_cartridge_t33_usage_time(var):
    def display_cartridge_t33_usage_time_sync(var):
        """显示T33滤芯使用时间"""
        var = int(var)
        _last_values["t33"] = var
        draw_english_small(f"{var:4}", 31, 51)
        display_show()

    await threadsafe_context.external_hardware.assign(display_cartridge_t33_usage_time_sync, var=var)


async def display_pure_water_tds_value(var):
    def display_pure_water_tds_value_sync(var):
        """显示纯水TDS值"""
        var = int(var)
        var = min(var, 999)
        _last_values["pure_tds"] = var
        draw_english_small(f"{var:3}", 100, 4)
        display_show()

    await threadsafe_context.external_hardware.assign(display_pure_water_tds_value_sync, var=var)


async def display_of_wastewater_tds_value(var):
    def display_of_wastewater_tds_value_sync(var):
        """显示废水TDS值"""
        var = int(var)
        var = min(var, 999)
        _last_values["waste_tds"] = var
        draw_english_small(f"{var:3}", 100, 19)
        display_show()

    await threadsafe_context.external_hardware.assign(display_of_wastewater_tds_value_sync, var=var)


async def display_water_temperature(var):
    def display_water_temperature_sync(var):
        """显示水温"""
        var = int(var)
        _last_values["temp"] = var
        draw_english_small(f"{var:2}", 99, 35)
        display_show()

    await threadsafe_context.external_hardware.assign(display_water_temperature_sync, var=var)


async def display_countdown_time(var):
    def display_countdown_time_sync(var):
        """显示倒计时时间（纯数字：>= 60 秒时传分钟，< 60 秒时传秒）；倒计时期间点亮并保持屏幕"""
        global _screen_wake, _screen_powered

        var = int(var)
        _last_values["countdown"] = var
        # 倒计时进行中：保持屏幕点亮（倒计时结束后"洗膜"状态会继续接管）
        _screen_wake = True
        if not _screen_powered:
            power_on()
            log.print_log("屏幕已点亮（泡膜倒计时）")
        draw_english_small("   ", 99, 50)
        draw_english_small(f"{var:3}", 99, 51)
        display_show()

    await threadsafe_context.external_hardware.assign(display_countdown_time_sync, var=var)


async def display_status(var):
    def display_status_sync(var):
        """显示现在工作状态；制水等运行状态变化时点亮屏幕（夜间也亮）"""
        global _screen_wake, _screen_grace_until, _screen_powered

        _last_values["status"] = var
        if var in ACTIVE_STATUSES:
            # 运行中：保持屏幕点亮
            _screen_wake = True
            if not _screen_powered:
                power_on()  # 点亮并重绘全部内容（含最新状态）
                log.print_log(f"屏幕已点亮（{var}）")
                return
        elif _screen_wake:
            # 结束运行：进入空闲计时，超时后自动熄屏
            _screen_wake = False
            _screen_grace_until = time.ticks_ms() + IDLE_TIMEOUT_S * 1000
        draw_chinese_small(var, 99, 50)
        display_show()

    await threadsafe_context.external_hardware.assign(display_status_sync, var=var)


def _draw_value(key, var):
    """按 key 重绘某一个显示项（供像素偏移/唤醒后恢复画面）"""
    if key == "status":
        draw_chinese_small(str(var), 99, 50)
        return
    var = int(var)
    if key == "pp":
        draw_english_small(f"{var:4}", 31, 2)
    elif key == "udf":
        draw_english_small(f"{var:4}", 31, 14)
    elif key == "cto":
        draw_english_small(f"{var:4}", 31, 26)
    elif key == "ro":
        draw_english_small(f"{var:4}", 31, 38)
    elif key == "t33":
        draw_english_small(f"{var:4}", 31, 51)
    elif key == "pure_tds":
        draw_english_small(f"{min(var, 999):3}", 100, 4)
    elif key == "waste_tds":
        draw_english_small(f"{min(var, 999):3}", 100, 19)
    elif key == "temp":
        draw_english_small(f"{var:2}", 99, 35)
    elif key == "countdown":
        draw_english_small("   ", 99, 50)
        draw_english_small(f"{var:3}", 99, 51)


def redraw_all():
    """清屏并重绘静态布局与最近一次的全部动态值（像素偏移或唤醒时调用）"""
    if not _ensure_display():
        return
    display.fill(0)
    _draw_static_layout()
    for key in ("pp", "udf", "cto", "ro", "t33", "pure_tds", "waste_tds", "temp", "countdown", "status"):
        if key in _last_values:
            _draw_value(key, _last_values[key])
    display.contrast(SCREEN_BRIGHTNESS)
    display_show()


def power_off():
    # 关闭屏幕（像素停止发光，防止烧屏；显存内容保留）
    global _screen_powered
    if not _ensure_display():
        return
    display.poweroff()
    _screen_powered = False


def power_on():
    # 打开屏幕并重绘当前画面
    global _screen_powered
    if not _ensure_display():
        return
    display.poweron()
    redraw_all()
    _screen_powered = True


async def orbit_task():
    """像素偏移任务（防烧屏）：周期切换偏移位置并重绘，均摊固定元素的像素负载"""
    global _shift_x, _shift_y
    idx = 0
    while True:
        try:
            await asyncio.sleep(ORBIT_INTERVAL_S)
            idx = (idx + 1) % len(ORBIT_POSITIONS)
            _shift_x, _shift_y = ORBIT_POSITIONS[idx]
            if _screen_powered:
                redraw_all()
        except Exception as e:
            log.print_log(f"像素偏移任务错误: {e}")


async def auto_off_task():
    """纯空闲自动熄屏任务（防烧屏）：无运行状态且空闲超过 IDLE_TIMEOUT_S 后熄屏；运行状态/倒计时自动点亮"""
    while True:
        try:
            now = time.ticks_ms()
            keep_on = _screen_wake or time.ticks_diff(now, _screen_grace_until) < 0
            if keep_on and not _screen_powered:
                power_on()
                log.print_log("屏幕已点亮（运行状态）")
            elif not keep_on and _screen_powered:
                power_off()
                log.print_log("空闲超时，自动熄屏（防烧屏）")
        except Exception as e:
            log.print_log(f"自动熄屏任务错误: {e}")
        await asyncio.sleep(30)


def lower_screen_brightness():
    # 降低屏幕亮度到30%
    global lower_screen_brightness_tag

    if lower_screen_brightness_tag is False:
        display.contrast(0x4D)  # 30%亮度
        display_show()
        lower_screen_brightness_tag = True


def display_text(text, x, y):
    if not _ensure_display():
        return
    display.text(text, x, y, 1)
    display_show()


def display_fill():
    if not _ensure_display():
        return
    display.fill(0)


if __name__ == "__main__":
    import asyncio

    init()
    # display_text("Hello, world!", 0, 0)
    asyncio.run(display_pure_water_tds_value(123))
