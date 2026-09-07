# ws2812b.py — WS2812B RGB LED 驱动（MicroPython）
#
# 参考教程实现：https://dmccreary.github.io/micropython/basics/05-neopixel/
#
# from pins import rgb_led
import neopixel
import time


class WS2812B:
    def __init__(self, num_leds, pin):
        self.num_leds = num_leds
        self.pin = pin
        self.np = neopixel.NeoPixel(pin, num_leds)

    def set_color(self, r, g, b):
        for i in range(self.num_leds):
            self.np[i] = (r, g, b)
        self.np.write()

    def set_colors(self, colors):
        for i in range(self.num_leds):
            self.np[i] = colors[i]
        self.np.write()

    def clear(self):
        self.np.fill((0, 0, 0))
        self.np.write()

    def rainbow(self, wait_ms=20, iterations=1):
        for j in range(256 * iterations):
            for i in range(self.num_leds):
                rc_index = (i * 256 // self.num_leds) + j
                self.np[i] = self.wheel(rc_index & 255)
            self.np.write()
            time.sleep_ms(wait_ms)

    def wheel(self, pos):
        if pos < 85:
            return (255 - pos * 3, pos * 3, 0)
        elif pos < 170:
            pos -= 85
            return (0, 255 - pos * 3, pos * 3)
        else:
            pos -= 170
            return (pos * 3, 0, 255 - pos * 3)


class PlainLed:
    """普通 LED 状态灯（非 WS2812B 的 GPIO48 板载灯）。

    接口与 WS2812B 一致（set_color/set_colors/clear），颜色信息被忽略：
    set_color → 点亮（表示有任务/非空闲），clear → 熄灭（空闲）。
    实测开发板为低电平点亮（GPIO 输出 0 点亮、1 熄灭）；
    若某板为高电平点亮，将 value(0)/value(1) 对调即可。
    """

    def __init__(self, pin):
        self._pin = pin
        self._pin.value(1)  # 初始置灭（低电平点亮板：输出 1=灭），避免启动早期误亮

    def set_color(self, r, g, b):
        self._pin.value(0)

    def set_colors(self, colors):
        self._pin.value(0)

    def clear(self):
        self._pin.value(1)
