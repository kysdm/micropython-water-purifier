from threadsafe import Context

# 用于屏幕显示（绘制/推送/开关等全部屏幕操作，串行执行避免总线并发冲突）
display_hardware = Context()
# 用于 TDS 传感器（独立线程：UART 读取会阻塞等待，避免占用显示线程导致屏幕刷新排队）
tds_hardware = Context()
# 用于网络硬件（WiFi 连接、NTP 校时等阻塞操作）
network_hardware = Context()
