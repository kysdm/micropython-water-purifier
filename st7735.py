# st7735.py — ST7735S 1.8 寸 128×160 TFT 驱动（MicroPython）
#
# 第三方驱动：基于常见开源 MIT 实现整理（初始化时序为 ST7735S 标准流程，
# 参考 Adafruit ST7735 及多个 MicroPython 移植版），随本项目按 MIT 协议分发。
# 说明：使用 framebuf.RGB565，UI 仅用白/黑两色时字节序不影响显示。

from micropython import const
import framebuf
import time

_SWRESET = const(0x01)
_SLPOUT = const(0x11)
_NORON = const(0x13)
_INVOFF = const(0x20)
_DISPOFF = const(0x28)
_DISPON = const(0x29)
_CASET = const(0x2A)
_RASET = const(0x2B)
_RAMWR = const(0x2C)
_COLMOD = const(0x3A)
_MADCTL = const(0x36)
_FRMCTR1 = const(0xB1)
_FRMCTR2 = const(0xB2)
_FRMCTR3 = const(0xB3)
_INVCTR = const(0xB4)
_PWCTR1 = const(0xC0)
_PWCTR2 = const(0xC1)
_PWCTR3 = const(0xC2)
_PWCTR4 = const(0xC3)
_PWCTR5 = const(0xC4)
_VMCTR1 = const(0xC5)
_GMCTRP1 = const(0xE0)
_GMCTRN1 = const(0xE1)


class ST7735(framebuf.FrameBuffer):
    """ST7735S 128×160（RGB565）驱动，framebuf 兼容接口"""

    def __init__(self, spi, cs, dc, rst, width=128, height=160, x_offset=0, y_offset=0, bgr=False):
        self._spi = spi
        self._cs = cs
        self._dc = dc
        self._rst = rst
        self._width = width
        self._height = height
        self._x_offset = x_offset
        self._y_offset = y_offset
        # MADCTL：C0 = MY|MX（128×160 常规方向）；bgr=True 时加 BGR 位（0x08）
        self._madtctl = 0xC0 | (0x08 if bgr else 0x00)
        self._buffer = bytearray(width * height * 2)
        super().__init__(self._buffer, width, height, framebuf.RGB565)
        self.reset()
        self._init_display()

    def _write_cmd(self, cmd):
        self._dc.value(0)
        self._cs.value(0)
        self._spi.write(bytes((cmd,)))
        self._cs.value(1)

    def _write_data(self, data):
        self._dc.value(1)
        self._cs.value(0)
        self._spi.write(data)
        self._cs.value(1)

    def reset(self):
        self._rst.value(0)
        time.sleep_ms(50)
        self._rst.value(1)
        time.sleep_ms(150)
        self._write_cmd(_SWRESET)
        time.sleep_ms(150)

    def _init_display(self):
        # ST7735S 标准初始化时序
        self._write_cmd(_SLPOUT)
        time.sleep_ms(200)
        self._write_cmd(_FRMCTR1)
        self._write_data(b"\x01\x2C\x2D")
        self._write_cmd(_FRMCTR2)
        self._write_data(b"\x01\x2C\x2D")
        self._write_cmd(_FRMCTR3)
        self._write_data(b"\x01\x2C\x2D\x01\x2C\x2D")
        self._write_cmd(_INVCTR)
        self._write_data(b"\x07")
        self._write_cmd(_PWCTR1)
        self._write_data(b"\xA2\x02\x84")
        self._write_cmd(_PWCTR2)
        self._write_data(b"\xC5")
        self._write_cmd(_PWCTR3)
        self._write_data(b"\x0A\x00")
        self._write_cmd(_PWCTR4)
        self._write_data(b"\x8A\x2A")
        self._write_cmd(_PWCTR5)
        self._write_data(b"\x8A\xEE")
        self._write_cmd(_VMCTR1)
        self._write_data(b"\x0E")
        self._write_cmd(_INVOFF)
        self._write_cmd(_MADCTL)
        self._write_data(bytes((self._madtctl,)))
        self._write_cmd(_COLMOD)
        self._write_data(b"\x05")  # 16 位色
        self._write_cmd(_GMCTRP1)
        self._write_data(b"\x02\x1C\x07\x12\x37\x32\x29\x2D\x29\x25\x2B\x39\x00\x01\x03\x10")
        self._write_cmd(_GMCTRN1)
        self._write_data(b"\x03\x1D\x07\x06\x2E\x2C\x29\x2D\x2E\x2E\x37\x3F\x00\x00\x02\x10")
        self._write_cmd(_NORON)
        time.sleep_ms(10)
        self._write_cmd(_DISPON)
        time.sleep_ms(100)

    def show(self):
        """将 framebuffer 推送到屏幕（RGB565，含行列偏移）"""
        self._write_cmd(_CASET)
        self._write_data(bytes((0x00, self._x_offset, 0x00, self._x_offset + self._width - 1)))
        self._write_cmd(_RASET)
        self._write_data(bytes((0x00, self._y_offset, 0x00, self._y_offset + self._height - 1)))
        self._write_cmd(_RAMWR)
        self._write_data(self._buffer)

    def poweroff(self):
        self._write_cmd(_DISPOFF)

    def poweron(self):
        self._write_cmd(_DISPON)
