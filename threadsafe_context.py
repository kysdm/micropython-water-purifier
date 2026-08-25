from threadsafe import Context

# 用于外置硬件（OLED、TDS 等阻塞外设）
external_hardware = Context()
# 用于内部硬件（WiFi、NTP 等阻塞操作）
internal_hardware = Context()
