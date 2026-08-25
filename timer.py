# timer.py
import time


class Timer:
    def __init__(self):
        self._elapsed = 0  # 已累计的时间（毫秒）
        self._start = None  # 开始计时的时间
        self._running = False  # 是否正在计时

    def start(self):
        """启动计时，如果已经在计时则不做处理。"""
        if not self._running:
            self._start = time.ticks_ms()
            self._running = True

    def stop(self):
        """停止计时，将这段时间累计到 _elapsed 中。"""
        if self._running:
            now = time.ticks_ms()
            self._elapsed += time.ticks_diff(now, self._start)
            self._running = False

    def reset(self):
        """重置计时器，清空累计时间。"""
        self._elapsed = 0
        self._start = time.ticks_ms()
        self._running = False

    def elapsed(self):
        """返回累计的运行时间（单位：毫秒）。"""
        if self._running:
            now = time.ticks_ms()
            return self._elapsed + time.ticks_diff(now, self._start)
        else:
            return self._elapsed
