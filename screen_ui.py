import asyncio
import time

import log
import font
import threadsafe_context
import screen

from time_utils import TIMEZONE_OFFSET


# 逻辑布局宽度：128（SSD1306 全屏；ST7735 纵向布局见 _layout()）
width = 128


# 屏幕延迟初始化：模块导入时不访问硬件，避免屏幕缺失导致开机崩溃
display = None
_ui_ready = False
_last_ui_error_log = 0  # 屏幕初始化失败日志限流时间戳


def _ensure_display():
    """确保屏幕已初始化（按 config 选择 SSD1306 或 ST7735）；硬件缺失时返回 False"""
    global display, _ui_ready, _last_ui_error_log
    if _ui_ready:
        return True
    try:
        display = screen.get_screen()
        _ui_ready = True
        return True
    except Exception as e:
        now = time.ticks_ms()
        if time.ticks_diff(now, _last_ui_error_log) >= 60000:  # 限流：每分钟最多 1 条
            _last_ui_error_log = now
            log.print_log(f"屏幕初始化失败: {e}")
        return False


# 屏幕亮度降级标志（供 lower_screen_brightness 使用）
lower_screen_brightness_tag = False

# ---- OLED 防烧屏配置 ----
SCREEN_BRIGHTNESS = 0x4D  # 正常显示亮度（原 0x7F，降至约 30%，减缓像素老化）
IDLE_TIMEOUT_S = 5 * 60  # 纯空闲模式：无运行状态且空闲超过该时长（秒）后自动熄屏
ORBIT_INTERVAL_S = 5 * 60  # 像素偏移间隔（秒）
ORBIT_POSITIONS = [(0, 0), (1, 0), (2, 0), (2, 1), (1, 1), (0, 1)]  # 偏移循环位置（横向 3 档 x 纵向 2 档）
ACTIVE_STATUSES = ("制水", "冲洗", "洗膜", "缺水")  # 需要保持屏幕点亮的运行状态（自动点亮并保持）

# TFT 状态文字颜色（RGB565；OLED 单色屏自动忽略，统一白色）
STATUS_COLORS = {
    "制水": 0x07E0,  # 绿
    "冲洗": 0xFFE0,  # 黄
    "缺水": 0xF800,  # 红
    "洗膜": 0x001F,  # 蓝
    "空闲": 0xFFFF,  # 白
    "超时": 0xFD20,  # 橙
    "完成": 0x07FF,  # 青
}

_shift_x = 0  # 当前像素偏移量
_shift_y = 0
_screen_powered = True  # 屏幕供电状态
_screen_wake = False  # 是否因运行状态（制水/冲洗等）需要保持屏幕点亮
_screen_grace_until = 0  # 空闲后允许继续点亮的截止时刻（ticks_ms）
_last_values = {}  # 最近一次各显示项的值，偏移/唤醒后用于重绘


def display_show():
    global display

    if not _ensure_display():
        return

    try:
        display.show()
        # 正常使用
    except OSError as e:
        log.print_log(f"屏幕通信错误: {e}")
        # 复位总线并重建显示对象（OLED：复位 I2C；TFT：重新初始化 SPI）
        try:
            display = screen.get_screen(force_reinit=True)
        except Exception as e2:
            log.print_log(f"屏幕重建失败: {e2}")


def draw_chinese(ch_str, x_axis, y_axis, color=1):
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
                display.pixel(x_axis + x + offset_ + _shift_x, y + y_axis + _shift_y, color if int(a_[x]) else 0)  # 文字的上半部分
                display.pixel(x_axis + x + offset_ + 8 + _shift_x, y + y_axis + _shift_y, color if int(b_[x]) else 0)  # 文字的下半部分

        offset_ += 16


def draw_chinese_small(ch_str, x_axis, y_axis, color=1):
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
                display.pixel(x_axis + x + offset_ + _shift_x, y + y_axis + _shift_y, color if int(a_[x]) else 0)  # 文字的左半部分
                display.pixel(x_axis + x + offset_ + 8 + _shift_x, y + y_axis + _shift_y, color if int(b_[x]) else 0)  # 文字的右半部分

        offset_ += 12  # 调整水平偏移量为12


def draw_english(text, x_axis, y_axis, color=1):
    """
    绘制英文字符。
    :param text: 英文字符串
    :param x_axis: 起始 x 坐标
    :param y_axis: 起始 y 坐标
    :param color: 颜色（TFT RGB565；OLED 单色屏忽略）
    """
    if not _ensure_display():
        return
    offset_ = 0  # 用于字符之间的偏移量
    for char in text:
        ascii_code = ord(char)  # 获取字符的 ASCII 编码
        byte_data = font.byte2.get(ascii_code, [0] * 16)  # 获取字符点阵数据（8x16 位图）

        # 绘制每一行的像素
        for y in range(0, 16):  # 高度 16 行
            a_ = bin(byte_data[y]).replace("0b", "")  # 将字节转换为二进制
            while len(a_) < 8:  # 手动补齐至 8 位
                a_ = "0" + a_

            for x in range(0, 8):  # 宽度 8 列
                display.pixel(x_axis + x + offset_ + _shift_x, y + y_axis + _shift_y, color if int(a_[x]) else 0)  # 绘制上半部分的像素

        offset_ += 8  # 每个字符宽度为 8 像素


def draw_english_small(text, x_axis, y_axis, color=1):
    """
    绘制英文字符。
    :param text: 英文字符串
    :param x_axis: 起始 x 坐标
    :param y_axis: 起始 y 坐标
    :param color: 颜色（TFT RGB565；OLED 单色屏忽略）
    """
    if not _ensure_display():
        return
    offset_ = 0  # 用于字符之间的偏移量
    for char in text:
        code = ord(char)
        ascii_code = f"{code}-s"  # 小字号字库键
        byte_data = font.byte2.get(ascii_code)
        if byte_data is None:
            # 小字号缺字时回退：取 16px 大字号字模的前 12 行
            big = font.byte2.get(code)
            byte_data = big[:12] if big else [0] * 12

        # 绘制每一行的像素
        for y in range(0, 12):  # 高度 12 行
            a_ = bin(byte_data[y]).replace("0b", "")  # 将字节转换为二进制
            while len(a_) < 8:  # 手动补齐至 8 位
                a_ = "0" + a_

            for x in range(0, 8):  # 宽度 8 列
                display.pixel(x_axis + x + offset_ + _shift_x, y + y_axis + _shift_y, color if int(a_[x]) else 0)  # 绘制上半部分的像素

        offset_ += 8  # 每个字符宽度为 8 像素


def draw_vertical_line(x, y_start, y_end, color=1):
    """
    绘制一条竖线。
    :param x: 竖线的 X 坐标
    :param y_start: 竖线的起始 Y 坐标
    :param y_end: 竖线的结束 Y 坐标
    """
    if not _ensure_display():
        return
    for y in range(y_start, y_end):
        display.pixel(x + _shift_x, y + _shift_y, color)  # 设定竖线上的每个像素为亮


def _layout():
    """按屏幕类型返回布局坐标（y 轴）。"""
    if screen.get_type() == "tft":
        return {
            "filter_y": [0, 12, 24, 36, 49],       # PP/UDF/CTO/RO/T33 标签
            "filter_val_y": [2, 14, 26, 38, 51],   # 对应数值
            "right_y": [2, 18, 34, 50],            # 纯水/废水/温度/状态 标签
            "right_val_y": [4, 19, 35, 50],        # 对应数值
            "temp_unit_y": 32,                     # °C 位置
            # TFT 底部信息栏（最终绘制坐标，OLED 无此栏）
            "bar": {
                "line_y": 64,      # 与主区分隔的横线
                "clear_y": 65,     # 清空区域顶边
                "clear_h": 94,     # 清空区域高度（到底边）
                "time_y": 74,      # 日期时间行
                "signal_y": 104,   # 信号强度行
                "ip_y": 130,       # IP 行
                "time_x": 6,       # 日期时间 x（独立可调）
                "ip_x": 4,         # IP x（独立可调）
                "signal_x": 8,     # 信号文字 x
                "icon_x": 104,     # 信号图标 x（右对齐）
            },
        }
    return {
        "filter_y": [0, 12, 24, 36, 49],
        "filter_val_y": [2, 14, 26, 38, 51],
        "right_y": [2, 18, 34, 50],
        "right_val_y": [4, 19, 35, 50],
        "temp_unit_y": 32,
        "bar": None,  # OLED 无底部信息栏
    }


def _draw_static_layout():
    if not _ensure_display():
        return
    ly = _layout()
    screen_h = display.height
    # 固定不变的部分（带偏移量，供像素偏移防烧屏）
    for i, label in enumerate(("PP :", "UDF:", "CTO:", "RO :", "T  :")):
        draw_english(label, 2, ly["filter_y"][i])
    # T33 数字用 12px 小字号，下移 2px 与 16px 标签底边对齐
    draw_english_small("33", 9, ly["filter_y"][4] + 2)

    draw_chinese_small("纯水", 67, ly["right_y"][0])
    draw_chinese_small("废水", 67, ly["right_y"][1])
    draw_chinese_small("温度", 67, ly["right_y"][2])
    draw_chinese_small("状态", 67, ly["right_y"][3])
    for i in range(4):
        draw_english_small(":", 91, ly["right_y"][i])
    # 温度
    draw_chinese("°", 113, ly["temp_unit_y"])
    draw_english("C", 119, ly["temp_unit_y"])

    draw_vertical_line(65, 0, screen_h)
    # 边框（偏移后右侧/下侧边框会被裁剪 1~2 像素，属预期）
    display.hline(_shift_x, _shift_y, width, 1)
    display.hline(_shift_x, _shift_y + screen_h - 1, width, 1)
    display.vline(_shift_x, _shift_y, screen_h, 1)
    display.vline(_shift_x + width - 1, _shift_y, screen_h, 1)

    if ly["bar"]:
        # TFT 底部信息栏分隔横线（OLED 无此栏）
        display.hline(_shift_x, ly["bar"]["line_y"], width, 1)


def init():
    global _screen_grace_until
    if not _ensure_display():
        return
    # 开机宽限期：NTP 同步完成后 auto_off_task 与开机冲洗存在调度竞争，
    # 避免 auto_off_task 首次检查（grace 仍为 0）立即误熄屏
    _screen_grace_until = time.ticks_add(time.ticks_ms(), IDLE_TIMEOUT_S * 1000)
    _draw_static_layout()
    display.contrast(SCREEN_BRIGHTNESS)  # 降低默认亮度，减缓像素老化

    display_show()


async def display_cartridge_pp_usage_time(var):
    def display_cartridge_pp_usage_time_sync(var):
        """显示PP滤芯使用时间"""
        var = int(var)
        _last_values["pp"] = var
        draw_english_small(f"{var:4}", 31, _layout()["filter_val_y"][0])
        display_show()

    await threadsafe_context.external_hardware.assign(display_cartridge_pp_usage_time_sync, var=var)


async def display_cartridge_udf_usage_time(var):
    def display_cartridge_udf_usage_time_sync(var):
        """显示UDF滤芯使用时间"""
        var = int(var)
        _last_values["udf"] = var
        draw_english_small(f"{var:4}", 31, _layout()["filter_val_y"][1])
        display_show()

    await threadsafe_context.external_hardware.assign(display_cartridge_udf_usage_time_sync, var=var)


async def display_cartridge_cto_usage_time(var):
    def display_cartridge_cto_usage_time_sync(var):
        """显示CTO滤芯使用时间"""
        var = int(var)
        _last_values["cto"] = var
        draw_english_small(f"{var:4}", 31, _layout()["filter_val_y"][2])
        display_show()

    await threadsafe_context.external_hardware.assign(display_cartridge_cto_usage_time_sync, var=var)


async def display_cartridge_ro_usage_time(var):
    def display_cartridge_ro_usage_time_sync(var):
        """显示RO滤芯使用时间"""
        var = int(var)
        _last_values["ro"] = var
        draw_english_small(f"{var:4}", 31, _layout()["filter_val_y"][3])
        display_show()

    await threadsafe_context.external_hardware.assign(display_cartridge_ro_usage_time_sync, var=var)


async def display_cartridge_t33_usage_time(var):
    def display_cartridge_t33_usage_time_sync(var):
        """显示T33滤芯使用时间"""
        var = int(var)
        _last_values["t33"] = var
        draw_english_small(f"{var:4}", 31, _layout()["filter_val_y"][4])
        display_show()

    await threadsafe_context.external_hardware.assign(display_cartridge_t33_usage_time_sync, var=var)


async def display_pure_water_tds_value(var):
    def display_pure_water_tds_value_sync(var):
        """显示纯水TDS值"""
        var = int(var)
        var = min(var, 999)
        _last_values["pure_tds"] = var
        draw_english_small(f"{var:3}", 100, _layout()["right_val_y"][0])
        display_show()

    await threadsafe_context.external_hardware.assign(display_pure_water_tds_value_sync, var=var)


async def display_of_wastewater_tds_value(var):
    def display_of_wastewater_tds_value_sync(var):
        """显示废水TDS值"""
        var = int(var)
        var = min(var, 999)
        _last_values["waste_tds"] = var
        draw_english_small(f"{var:3}", 100, _layout()["right_val_y"][1])
        display_show()

    await threadsafe_context.external_hardware.assign(display_of_wastewater_tds_value_sync, var=var)


async def display_water_temperature(var):
    def display_water_temperature_sync(var):
        """显示水温"""
        var = int(var)
        _last_values["temp"] = var
        draw_english_small(f"{var:2}", 99, _layout()["right_val_y"][2])
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
            # 先在显存画上倒计时数字再点亮（全屏重绘较慢，避免点亮瞬间显示熄灭前的旧画面）
            draw_english_small("   ", 99, _layout()["right_val_y"][3])
            draw_english_small(f"{var:3}", 99, _layout()["right_val_y"][3] + 1)
            display_show()
            power_on()
            log.print_log("屏幕已点亮（泡膜倒计时）")
            return
        draw_english_small("   ", 99, _layout()["right_val_y"][3])
        draw_english_small(f"{var:3}", 99, _layout()["right_val_y"][3] + 1)
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
                # 先在显存画上最新状态再点亮（全屏重绘较慢，避免点亮瞬间显示熄灭前的旧状态）
                draw_chinese_small(var, 99, _layout()["right_val_y"][3], color=STATUS_COLORS.get(var, 0xFFFF))
                display_show()
                power_on()  # 点亮并重绘全部内容（状态已正确）
                log.print_log(f"屏幕已点亮（{var}）")
                return
        elif _screen_wake:
            # 结束运行：进入空闲计时，超时后自动熄屏
            _screen_wake = False
            _screen_grace_until = time.ticks_ms() + IDLE_TIMEOUT_S * 1000
        draw_chinese_small(var, 99, _layout()["right_val_y"][3], color=STATUS_COLORS.get(var, 0xFFFF))
        display_show()

    await threadsafe_context.external_hardware.assign(display_status_sync, var=var)


def _draw_value(key, var):
    """按 key 重绘某一个显示项（供像素偏移/唤醒后恢复画面）"""
    ly = _layout()
    if key == "status":
        draw_chinese_small(str(var), 99, ly["right_val_y"][3], color=STATUS_COLORS.get(str(var), 0xFFFF))
        return
    var = int(var)
    if key == "pp":
        draw_english_small(f"{var:4}", 31, ly["filter_val_y"][0])
    elif key == "udf":
        draw_english_small(f"{var:4}", 31, ly["filter_val_y"][1])
    elif key == "cto":
        draw_english_small(f"{var:4}", 31, ly["filter_val_y"][2])
    elif key == "ro":
        draw_english_small(f"{var:4}", 31, ly["filter_val_y"][3])
    elif key == "t33":
        draw_english_small(f"{var:4}", 31, ly["filter_val_y"][4])
    elif key == "pure_tds":
        draw_english_small(f"{min(var, 999):3}", 100, ly["right_val_y"][0])
    elif key == "waste_tds":
        draw_english_small(f"{min(var, 999):3}", 100, ly["right_val_y"][1])
    elif key == "temp":
        draw_english_small(f"{var:2}", 99, ly["right_val_y"][2])
    elif key == "countdown":
        draw_english_small("   ", 99, ly["right_val_y"][3])
        draw_english_small(f"{var:3}", 99, ly["right_val_y"][3] + 1)


_SIGNAL_ICON_W = 4 * 3 + 3 * 2  # 4 格信号图标总宽度（每格 3px + 2px 间隙）


def _draw_signal_icon(x, y, color):
    """绘制 4 格信号强度图标（左低右高，梯形），返回图标占用宽度"""
    bar_w = 3
    gap = 2
    heights = [4, 7, 10, 12]
    for i, h in enumerate(heights):
        display.fill_rect(x + i * (bar_w + gap), y + 12 - h, bar_w, h, color)
    return _SIGNAL_ICON_W


def _draw_bottom_bar_sync():
    """TFT 底部信息栏：时间|星期 / 信号强度 / IP（OLED 无此栏）"""
    if not _ensure_display():
        return
    ly = _layout()
    bar = ly["bar"]
    if not bar:
        return
    import wifi

    if wifi.sta_if.isconnected():
        try:
            rssi = wifi.sta_if.status("rssi")  # 信号强度（dBm，负值）
            status = f"WIFI:{rssi}dBm"
            if rssi >= -60:
                bar_color = 0x07E0  # 绿：信号好
            elif rssi >= -80:
                bar_color = 0xFFE0  # 黄：信号一般
            else:
                bar_color = 0xF800  # 红：信号差
        except Exception:
            status = "WIFI ON"
            bar_color = 1
        ip = wifi.sta_if.ifconfig()[0]
    else:
        status = "WIFI OFF"
        ip = "--"
        bar_color = 1

    # 日期+时间：异常时也照常显示（如时间未同步会显示 00-01-01 00:00 的真实值）
    try:
        now = time.localtime(time.time() + TIMEZONE_OFFSET)
        # 两位年份格式（完整年份会超出 128px 宽度）
        date_time_str = "{:02d}-{:02d}-{:02d} {:02d}:{:02d}".format(
            now[0] % 100, now[1], now[2], now[3], now[4]
        )
    except Exception:
        date_time_str = "--/--/-- --:--"

    # 清空三行区域并重绘
    display.fill_rect(1, bar["clear_y"], width - 2, bar["clear_h"], 0)
    # 第一行：日期 + 时间（8px）
    draw_english(date_time_str, bar["time_x"], bar["time_y"])
    # 第二行：信号强度（彩色，左侧）+ 信号图标（右侧）
    draw_english(status, bar["signal_x"], bar["signal_y"], color=bar_color)
    _draw_signal_icon(bar["icon_x"], bar["signal_y"], bar_color)
    # 第三行：IP 地址
    draw_english(ip, bar["ip_x"], bar["ip_y"])
    display_show()


def redraw_all():
    """清屏并重绘静态布局与最近一次的全部动态值（像素偏移或唤醒时调用）"""
    if not _ensure_display():
        return
    display.fill(0)
    _draw_static_layout()
    for key in ("pp", "udf", "cto", "ro", "t33", "pure_tds", "waste_tds", "temp", "countdown", "status"):
        if key in _last_values:
            _draw_value(key, _last_values[key])
    if _layout()["bar"]:
        _draw_bottom_bar_sync()  # TFT 底部信息栏（自带 display_show）
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
    """像素偏移任务（防烧屏，仅 OLED 需要）：周期切换偏移位置并重绘，均摊固定元素的像素负载"""
    global _shift_x, _shift_y
    idx = 0
    while True:
        try:
            await asyncio.sleep(ORBIT_INTERVAL_S)
            if screen.get_type() != "oled":
                continue  # TFT 为 LCD，无烧屏问题，不需要像素偏移
            idx = (idx + 1) % len(ORBIT_POSITIONS)
            _shift_x, _shift_y = ORBIT_POSITIONS[idx]
            if _screen_powered:
                await threadsafe_context.external_hardware.assign(redraw_all)
        except Exception as e:
            log.print_log(f"像素偏移任务错误: {e}")


async def auto_off_task():
    """纯空闲自动熄屏任务（防烧屏）：无运行状态且空闲超过 IDLE_TIMEOUT_S 后熄屏；运行状态/倒计时自动点亮"""
    while True:
        try:
            now = time.ticks_ms()
            keep_on = _screen_wake or time.ticks_diff(now, _screen_grace_until) < 0
            if keep_on and not _screen_powered:
                # 走工作线程串行操作屏幕总线，避免与显示任务并发导致死机
                await threadsafe_context.external_hardware.assign(power_on)
                log.print_log("屏幕已点亮（运行状态）")
            elif not keep_on and _screen_powered:
                await threadsafe_context.external_hardware.assign(power_off)
                log.print_log("空闲超时，自动熄屏（防烧屏）")
        except Exception as e:
            log.print_log(f"自动熄屏任务错误: {e}")
        await asyncio.sleep(30)


async def refresh_bottom_bar():
    """刷新 TFT 底部 WiFi 状态/IP 信息栏（OLED 无此栏，直接跳过）"""
    while True:
        try:
            if screen.get_type() == "tft" and _screen_powered:
                await threadsafe_context.external_hardware.assign(_draw_bottom_bar_sync)
        except Exception as e:
            log.print_log(f"底部信息栏刷新失败: {e}")
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
