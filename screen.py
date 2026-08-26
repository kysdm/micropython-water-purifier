# screen.py — 屏幕抽象层：按 config 选择 SSD1306 OLED 或 ST7735 TFT
#
# 对外统一接口：pixel / fill / hline / vline / text / show / contrast /
#               poweroff / poweron / reinit
# 单色绘制值 1/0 自动映射为前景白 / 背景黑（TFT RGB565 用 0xFFFF / 0x0000）。

import time

# ---- 屏幕选择（烧录固件前在此决定，硬件上只接一块屏）----
DISPLAY_TYPE = "tft"  # "oled" = SSD1306 I2C；"tft" = ST7735 SPI（1.8 寸 128×160）
OLED_PINS = {"sda": 1, "scl": 2}  # OLED I2C 引脚，按实际接线修改
# TFT SPI 引脚。模块丝印习惯标 SCL/SDA，即 SPI 的 SCK/MOSI；
# 与模块丝印对照：SCL=sclk(7) SDA=mosi(8) CS=14 DC=15 RST=16 BLK=bl(21)，VCC 接 3.3V、GND 接地
TFT_PINS = {"sclk": 7, "mosi": 8, "cs": 14, "dc": 15, "rst": 16, "bl": 21}  # TFT SPI 引脚，按实际接线修改
TFT_X_OFFSET = 0  # 部分 1.8 寸模块显示左移/上移时需要 1~2 像素偏移
TFT_Y_OFFSET = 0
TFT_BGR = True  # 颜色红蓝互换时改 True（白字界面通常无感，但建议按屏幕实际调）

_TFT_FG = 0xFFFF  # TFT 前景色（白）


def _tft_color(c):
    """TFT 颜色映射：1 = 默认前景白；0 = 黑；其他值 = 具体 RGB565 颜色"""
    return _TFT_FG if c == 1 else c


class OLEDScreen:
    """SSD1306 OLED（0.96 寸 128×64，I2C）"""

    def __init__(self):
        import ssd1306
        from machine import Pin, SoftI2C

        self.width = 128
        self.height = 64
        self.i2c = SoftI2C(sda=Pin(OLED_PINS["sda"]), scl=Pin(OLED_PINS["scl"]))
        self.dev = ssd1306.SSD1306_I2C(self.width, self.height, self.i2c)

    def reset_bus(self):
        """复位 SoftI2C 总线（OLED 专用，释放被卡住的从机）"""
        from machine import Pin

        scl = Pin(OLED_PINS["scl"], Pin.OUT, Pin.PULL_UP)
        sda = Pin(OLED_PINS["sda"], Pin.OUT, Pin.PULL_UP)
        scl.value(1)
        sda.value(1)
        time.sleep_ms(5)
        for _ in range(9):
            scl.value(0)
            time.sleep_us(5)
            scl.value(1)
            time.sleep_us(5)
        scl.value(1)
        sda.value(0)
        time.sleep_us(5)
        sda.value(1)
        time.sleep_us(5)

    def reinit(self):
        self.reset_bus()
        self.__init__()

    def pixel(self, x, y, c):
        self.dev.pixel(x, y, c)

    def fill(self, c):
        self.dev.fill(c)

    def hline(self, x, y, w, c):
        self.dev.hline(x, y, w, c)

    def vline(self, x, y, h, c):
        self.dev.vline(x, y, h, c)

    def fill_rect(self, x, y, w, h, c):
        self.dev.fill_rect(x, y, w, h, c)

    def text(self, s, x, y, c=1):
        self.dev.text(s, x, y, c)

    def show(self):
        self.dev.show()

    def contrast(self, v):
        self.dev.contrast(v)

    def poweroff(self):
        self.dev.poweroff()

    def poweron(self):
        self.dev.poweron()


class TFTScreen:
    """ST7735 TFT（1.8 寸 128×160，SPI，RGB565）"""

    def __init__(self, pins):
        import st7735
        from machine import Pin, SPI

        self.width = 128
        self.height = 160
        self._pins = pins
        self.spi = SPI(2, baudrate=40000000, polarity=0, phase=0,
                       sck=Pin(pins["sclk"]), mosi=Pin(pins["mosi"]))
        self.cs = Pin(pins["cs"], Pin.OUT, value=1)
        self.dc = Pin(pins["dc"], Pin.OUT, value=0)
        self.rst = Pin(pins["rst"], Pin.OUT, value=1)
        self.bl = Pin(pins["bl"], Pin.OUT, value=1) if pins["bl"] is not None else None
        self.dev = st7735.ST7735(self.spi, cs=self.cs, dc=self.dc, rst=self.rst,
                                 width=self.width, height=self.height,
                                 x_offset=TFT_X_OFFSET, y_offset=TFT_Y_OFFSET, bgr=TFT_BGR)

    def reinit(self):
        self.__init__(self._pins)

    def pixel(self, x, y, c):
        self.dev.pixel(x, y, _tft_color(c))

    def fill(self, c):
        self.dev.fill(_tft_color(c))

    def hline(self, x, y, w, c):
        self.dev.hline(x, y, w, _tft_color(c))

    def vline(self, x, y, h, c):
        self.dev.vline(x, y, h, _tft_color(c))

    def fill_rect(self, x, y, w, h, c):
        self.dev.fill_rect(x, y, w, h, _tft_color(c))

    def text(self, s, x, y, c=1):
        self.dev.text(s, x, y, _tft_color(c))

    def show(self):
        self.dev.show()

    def contrast(self, v):
        pass  # TFT 无对比度控制

    def poweroff(self):
        if self.bl is not None:
            self.bl.value(0)
        self.dev.poweroff()

    def poweron(self):
        if self.bl is not None:
            self.bl.value(1)
        self.dev.poweron()


_screen = None


def get_type():
    """当前固件使用的屏幕类型：oled / tft"""
    return DISPLAY_TYPE


def get_screen(force_reinit=False):
    """获取屏幕对象；force_reinit 用于通信故障后的重建"""
    global _screen
    if _screen is None or force_reinit:
        if DISPLAY_TYPE == "tft":
            _screen = TFTScreen(TFT_PINS)
        else:
            _screen = OLEDScreen()
    return _screen
