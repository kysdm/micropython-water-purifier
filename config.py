import json

import log

from time_utils import get_current_timestamp

# 配置文件名、默认配置和必需字段
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {"pure_water_ro_clean_timeout": 5, "ro_force_clean_time": 30, "countdown_time": 45, "tds": 10, "fill_tds": 10, "pp": 795584368, "cto": 795584368, "udf": 795584368, "ro": 795584368, "t33": 795584368, "wifi_ssid": "esp32", "wifi_password": "12345678", "web_password": "admin", "ota_url": ""}
REQUIRED_KEYS = {"pure_water_ro_clean_timeout", "ro_force_clean_time", "tds", "countdown_time", "pp", "cto", "udf", "ro", "t33", "wifi_ssid", "wifi_password"}

# 缓存配置数据
_config_cache = None


def load_config(force_reload=False):
    """
    加载配置文件并验证配置的有效性。
    如果已经缓存且不要求强制重载，则直接返回缓存数据。
    若出现问题则使用默认配置。
    """
    global _config_cache

    if _config_cache is not None and not force_reload:
        return _config_cache

    try:
        with open(CONFIG_FILE, "r") as file:
            config = json.load(file)

        if config is None:
            log.print_log("配置文件为空，使用默认配置")
            raise ValueError("配置为空")

        # 验证必需字段是否齐全
        if not REQUIRED_KEYS.issubset(config.keys()):
            log.print_log("配置文件缺少必需字段")
            raise ValueError("Missing required fields")

        # 检查所有字段对应的值是否为整数
        for key in REQUIRED_KEYS:
            if "wifi_" in key:
                if not isinstance(config.get(key), str):
                    log.print_log(f"{key} 必须为字符串")
                    raise ValueError(f"Invalid field type for {key}")
            elif not isinstance(config.get(key), int):
                log.print_log(f"{key} 必须为整数")
                raise ValueError(f"Invalid field type for {key}")

        _config_cache = config
        return config

    except (OSError, ValueError) as e:
        log.print_log(f"加载配置失败: {str(e)}，使用默认配置")
        _config_cache = DEFAULT_CONFIG.copy()
        save_config(_config_cache)
        return _config_cache

    except Exception as e:
        log.print_log(f"加载配置时发生未知错误: {str(e)}，使用默认配置")
        _config_cache = DEFAULT_CONFIG.copy()
        save_config(_config_cache)
        return _config_cache


def save_config(config):
    """
    保存配置到文件，并更新缓存数据
    """
    global _config_cache
    try:
        with open(CONFIG_FILE, "w") as file:
            json.dump(config, file)
        _config_cache = config
    except Exception as e:
        log.print_log(f"保存配置时出错: {str(e)}")


def update_config(key, value):
    """
    更新配置文件中的某个参数。
    """
    config = load_config()
    config[key] = value
    save_config(config)


def get_config_value(key):
    """
    获取配置中指定键的值
    """
    config = load_config()
    return config.get(key)


def get_tds():
    return get_config_value("tds")


def get_countdown_time():
    return get_config_value("countdown_time")


def get_pp():
    return get_config_value("pp")


def get_cto():
    return get_config_value("cto")


def get_udf():
    return get_config_value("udf")


def get_ro():
    return get_config_value("ro")


def get_t33():
    return get_config_value("t33")


def set_tds(tds):
    # 限定 tds 的取值范围在 5 到 30 之间
    tds = max(5, min(tds, 30))
    # 互斥：洗膜目标TDS 不能低于注水TDS（注水水质不高于洗膜完成标准）
    tds = max(tds, get_fill_tds())
    update_config("tds", tds)


def get_fill_tds():
    # 压力桶注水纯水 TDS 阈值；旧配置无此字段时使用默认值
    value = get_config_value("fill_tds")
    return value if isinstance(value, int) else DEFAULT_CONFIG["fill_tds"]


def set_fill_tds(new_tds):
    # 限定 fill_tds 的取值范围在 1 到 20 之间
    new_tds = max(1, min(new_tds, 20))
    # 互斥：注水TDS 不能高于洗膜目标TDS（纯水应比洗膜完成的废水更干净）
    new_tds = min(new_tds, get_tds())
    update_config("fill_tds", new_tds)


def set_countdown_time(countdown_time):
    # 限定 countdown_time 的取值范围在 1 到 3600 之间
    countdown_time = max(1, min(countdown_time, 3600))
    update_config("countdown_time", countdown_time)


def reset_pp_usage():
    update_config("pp", get_current_timestamp())


def reset_cto_usage():
    update_config("cto", get_current_timestamp())


def reset_udf_usage():
    update_config("udf", get_current_timestamp())


def reset_ro_usage():
    update_config("ro", get_current_timestamp())


def reset_t33_usage():
    update_config("t33", get_current_timestamp())


def set_wifi(wifi_ssid, wifi_password):
    update_config("wifi_ssid", wifi_ssid)
    update_config("wifi_password", wifi_password)


def get_display_type():
    # 屏幕类型（"oled"/"tft"）；未配置返回 None，由 screen.py 使用默认值
    value = get_config_value("display_type")
    return value if value in ("oled", "tft") else None


def set_display_type(new_type):
    if new_type in ("oled", "tft"):
        update_config("display_type", new_type)


def get_ota_url():
    # OTA 更新源基础 URL；空字符串表示未启用
    value = get_config_value("ota_url")
    return value if isinstance(value, str) else ""


def set_ota_url(new_url):
    update_config("ota_url", new_url.strip() if isinstance(new_url, str) else "")


def get_web_password():
    # Web 访问密码；未配置时使用默认值
    value = get_config_value("web_password")
    return value if isinstance(value, str) and value else "admin"


def set_web_password(new_password):
    update_config("web_password", new_password)


def set_pure_water_ro_clean_timeout(new_time):
    # 限定 pure_water_ro_clean_timeout 的取值范围在 1 到 10 之间
    new_time = max(1, min(new_time, 10))
    update_config("pure_water_ro_clean_timeout", new_time)


def set_ro_force_clean_time(new_time):
    # 限定 ro_force_clean_time 的取值范围在 1 到 60 之间
    new_time = max(1, min(new_time, 60))
    update_config("ro_force_clean_time", new_time)
