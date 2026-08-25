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


# 初始化 I2C 和 OLED 屏幕
i2c = SoftI2C(sda=Pin(1), scl=Pin(2))
display = ssd1306.SSD1306_I2C(width, height, i2c)

# 屏幕亮度降级标志（供 lower_screen_brightness 使用）
lower_screen_brightness_tag = False


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
                display.pixel(x_axis + x + offset_, y + y_axis, int(a_[x]))  # 文字的上半部分
                display.pixel(x_axis + x + offset_ + 8, y + y_axis, int(b_[x]))  # 文字的下半部分

        offset_ += 16


def draw_chinese_small(ch_str, x_axis, y_axis):
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
                display.pixel(x_axis + x + offset_, y + y_axis, int(a_[x]))  # 文字的左半部分
                display.pixel(x_axis + x + offset_ + 8, y + y_axis, int(b_[x]))  # 文字的右半部分

        offset_ += 12  # 调整水平偏移量为12


def draw_english(text, x_axis, y_axis):
    """
    绘制英文字符。
    :param text: 英文字符串
    :param x_axis: 起始 x 坐标
    :param y_axis: 起始 y 坐标
    """
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
                display.pixel(x_axis + x + offset_, y + y_axis, int(a_[x]))  # 绘制上半部分的像素

        offset_ += 8  # 每个字符宽度为 8 像素


def draw_english_small(text, x_axis, y_axis):
    """
    绘制英文字符。
    :param text: 英文字符串
    :param x_axis: 起始 x 坐标
    :param y_axis: 起始 y 坐标
    """
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
                display.pixel(x_axis + x + offset_, y + y_axis, int(a_[x]))  # 绘制上半部分的像素

        offset_ += 8  # 每个字符宽度为 8 像素


def draw_vertical_line(x, y_start, y_end):
    """
    绘制一条竖线。
    :param x: 竖线的 X 坐标
    :param y_start: 竖线的起始 Y 坐标
    :param y_end: 竖线的结束 Y 坐标
    """
    for y in range(y_start, y_end):
        display.pixel(x, y, 1)  # 设定竖线上的每个像素为亮


def init():
    # 固定不变的部分
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
    # 上边框
    display.hline(0, 0, width, 1)
    # 下边框
    display.hline(0, height - 1, width, 1)
    # 左边框
    display.vline(0, 0, height, 1)
    # 右边框
    display.vline(width - 1, 0, height, 1)

    display.contrast(0x7F)  # 80%亮度

    display_show()


async def display_cartridge_pp_usage_time(var):
    def display_cartridge_pp_usage_time_sync(var):
        """显示PP滤芯使用时间"""
        var = int(var)
        draw_english_small(f"{var:4}", 31, 2)
        display_show()

    await threadsafe_context.external_hardware.assign(display_cartridge_pp_usage_time_sync, var=var)


async def display_cartridge_udf_usage_time(var):
    def display_cartridge_udf_usage_time_sync(var):
        """显示UDF滤芯使用时间"""
        var = int(var)
        draw_english_small(f"{var:4}", 31, 14)
        display_show()

    await threadsafe_context.external_hardware.assign(display_cartridge_udf_usage_time_sync, var=var)


async def display_cartridge_cto_usage_time(var):
    def display_cartridge_cto_usage_time_sync(var):
        """显示CTO滤芯使用时间"""
        var = int(var)
        draw_english_small(f"{var:4}", 31, 26)
        display_show()

    await threadsafe_context.external_hardware.assign(display_cartridge_cto_usage_time_sync, var=var)


async def display_cartridge_ro_usage_time(var):
    def display_cartridge_ro_usage_time_sync(var):
        """显示RO滤芯使用时间"""
        var = int(var)
        draw_english_small(f"{var:4}", 31, 38)
        display_show()

    await threadsafe_context.external_hardware.assign(display_cartridge_ro_usage_time_sync, var=var)


async def display_cartridge_t33_usage_time(var):
    def display_cartridge_t33_usage_time_sync(var):
        """显示T33滤芯使用时间"""
        var = int(var)
        draw_english_small(f"{var:4}", 31, 51)
        display_show()

    await threadsafe_context.external_hardware.assign(display_cartridge_t33_usage_time_sync, var=var)


async def display_pure_water_tds_value(var):
    def display_pure_water_tds_value_sync(var):
        """显示纯水TDS值"""
        var = int(var)
        var = min(var, 999)
        draw_english_small(f"{var:3}", 100, 4)
        display_show()

    await threadsafe_context.external_hardware.assign(display_pure_water_tds_value_sync, var=var)


async def display_of_wastewater_tds_value(var):
    def display_of_wastewater_tds_value_sync(var):
        """显示废水TDS值"""
        var = int(var)
        var = min(var, 999)
        draw_english_small(f"{var:3}", 100, 19)
        display_show()

    await threadsafe_context.external_hardware.assign(display_of_wastewater_tds_value_sync, var=var)


async def display_water_temperature(var):
    def display_water_temperature_sync(var):
        """显示水温"""
        var = int(var)
        draw_english_small(f"{var:2}", 99, 35)
        display_show()

    await threadsafe_context.external_hardware.assign(display_water_temperature_sync, var=var)


async def display_countdown_time(var):
    def display_countdown_time_sync(var):
        """显示倒计时时间"""
        var = int(var)
        draw_english_small("   ", 99, 50)
        draw_english_small(f"{var:3}", 99, 51)
        display_show()

    await threadsafe_context.external_hardware.assign(display_countdown_time_sync, var=var)


async def display_status(var):
    def display_status_sync(var):
        """显示现在工作状态"""
        draw_chinese_small(var, 99, 50)
        display_show()

    await threadsafe_context.external_hardware.assign(display_status_sync, var=var)


def power_off():
    # 关闭屏幕
    display.poweroff()


def lower_screen_brightness():
    # 降低屏幕亮度到30%
    global lower_screen_brightness_tag

    if lower_screen_brightness_tag is False:
        display.contrast(0x4D)  # 30%亮度
        display_show()
        lower_screen_brightness_tag = True


def display_text(text, x, y):
    display.text(text, x, y, 1)
    display_show()


def display_fill():
    display.fill(0)


if __name__ == "__main__":
    import asyncio

    init()
    # display_text("Hello, world!", 0, 0)
    asyncio.run(display_pure_water_tds_value(123))
