from machine import Pin
from machine import UART


# 状态指示灯 (闪烁)
# state_led = Pin(2, Pin.OUT, value=0)

# 高压开关 检测是否在制水
high_pressure_switch = Pin(4, Pin.IN, Pin.PULL_UP)
# 低压开关 检测是否缺水
low_pressure_switch = Pin(5, Pin.IN, Pin.PULL_UP)

# 压力桶进水电磁阀
pressure_bucket_to_water_inlet_solenoid_valve_switch = Pin(11, Pin.OUT, value=0)
# 压力桶出水电磁阀
pressure_bucket_to_water_outlet_solenoid_valve_switch = Pin(12, Pin.OUT, value=0)


# 增压泵开关
booster_pump_solenoid_valve_switch = Pin(9, Pin.OUT, value=0)

# 废水阀开关
wastewater_solenoid_valve_switch = Pin(10, Pin.OUT, value=0)

# 入水电磁阀
water_inlet_solenoid_valve_switch = Pin(13, Pin.OUT, value=0)


# OLED屏幕
# i2c = SoftI2C(sda=Pin(1), scl=Pin(2))

# 初始化UART
uart = UART(1, baudrate=9600, tx=Pin(17), rx=Pin(18))

# RGB LED
rgb_led = Pin(48, Pin.OUT)

# 屏幕引脚（屏幕类型在 screen.py 的 DISPLAY_TYPE 决定，两块屏硬件只接一块）
# OLED：SSD1306 I2C
OLED_PINS = {"sda": 1, "scl": 2}  # OLED I2C 引脚，按实际接线修改
# TFT：ST7735 SPI。模块丝印习惯标 SCL/SDA，即 SPI 的 SCK/MOSI；
# 与模块丝印对照：SCL=sclk(7) SDA=mosi(8) CS=14 DC=15 RST=16 BLK=bl(21)，VCC 接 3.3V、GND 接地
# miso=3 为哑引脚（无实际接线）：TFT 只写不读，但硬件 SPI 必须显式指定 MISO，
# 省略时固件会启用该 host 的默认 MISO（实测占用 GPIO13 进水电磁阀，导致进水阀无反应）。
# 取值须避开项目已用引脚。
TFT_PINS = {"sclk": 7, "mosi": 8, "cs": 14, "dc": 15, "rst": 16, "bl": 21, "miso": 3}  # TFT SPI 引脚，按实际接线修改
