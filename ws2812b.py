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
