import config

from time_utils import calculate_time_difference


def get_pp_cartridge_usage_time():
    return calculate_time_difference(config.get_pp())


def get_udf_cartridge_usage_time():
    return calculate_time_difference(config.get_udf())


def get_cto_cartridge_usage_time():
    return calculate_time_difference(config.get_cto())


def get_ro_cartridge_usage_time():
    return calculate_time_difference(config.get_ro())


def get_t33_cartridge_usage_time():
    return calculate_time_difference(config.get_t33())
