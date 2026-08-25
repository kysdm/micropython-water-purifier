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
