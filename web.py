import asyncio
import os
import ubinascii

import log
import config
import ota
import cartridge_usage_time


ADDRESS = "0.0.0.0"
PORT = 80
AUTH_USER = "admin"  # Web 管理用户名（Basic Auth）


def file_exists(file_path):
    """
    检查文件是否存在。
    """
    try:
        os.stat(file_path)
        return True
    except OSError:
        return False


def validate_wifi(ssid: str, password: str) -> bool:
    """
    验证 WiFi 名称和密码是否合法
    :param ssid: WiFi 名称，要求非空、UTF-8 编码后不超过 32 字节（硬件上限）；
                 支持中文（1 汉字占 3 字节，最多约 10 个汉字），但不建议使用中文（老路由器 GBK 编码不兼容）
    :param password: WiFi 密码，要求长度在 8 到 63 个字符之间
    :return: 合法返回 True，否则返回 False
    """
    # 检查 ssid：非空、UTF-8 字节数不超过 32、不含控制字符
    if not isinstance(ssid, str) or len(ssid) == 0:
        return False
    try:
        ssid_bytes = ssid.encode("utf-8")
    except Exception:
        return False
    if len(ssid_bytes) > 32:
        return False
    if any(ord(ch) < 32 for ch in ssid):
        return False

    # 检查密码
    if not isinstance(password, str) or not (8 <= len(password) <= 63):
        return False

    return True


def get_web_password():
    """获取 Web 访问密码（config.json 的 web_password，缺省 admin）"""
    return config.get_web_password()


def is_authorized(request):
    """
    校验 HTTP Basic Auth 请求头（Authorization: Basic base64(用户名:密码)）。
    密码错误或缺失返回 False。
    """
    try:
        header_part = request.split("\r\n\r\n", 1)[0]
        for line in header_part.split("\r\n"):
            if line.lower().startswith("authorization:"):
                # 先去掉 "Authorization:" 前缀，再拆 scheme 与 token
                auth = line.partition(":")[2].strip()
                scheme, _, token = auth.partition(" ")
                if scheme.lower() != "basic" or not token:
                    return False
                decoded = ubinascii.a2b_base64(token).decode("utf-8")
                user, _, password = decoded.partition(":")
                return user == AUTH_USER and password == get_web_password()
    except Exception:
        pass
    return False


def url_decode(s):
    """
    简单的 URL 解码：+ 还原为空格，%XX 还原为原始字节（兼容 UTF-8 中文）。
    """
    s = s.replace("+", " ")
    out = bytearray()
    i = 0
    length = len(s)
    while i < length:
        ch = s[i]
        if ch == "%" and i + 2 < length:
            try:
                out.append(int(s[i + 1:i + 3], 16))
                i += 3
                continue
            except ValueError:
                pass
        out.extend(ch.encode("utf-8"))
        i += 1
    return out.decode("utf-8")


def mask_password(password):
    """
    掩码显示密码：仅保留前 2 位和后 2 位，中间用 * 代替。
    """
    if not password:
        return ""
    if len(password) <= 4:
        return "*" * len(password)
    return password[:2] + "*" * (len(password) - 4) + password[-2:]


# 获取滤芯使用时间（单位：天）
def get_filter_usage():
    """
    返回一个字典，包含净水机各滤芯使用时间（单位：天）。
    """
    return {
        "pp": cartridge_usage_time.get_pp_cartridge_usage_time(),
        "cto": cartridge_usage_time.get_cto_cartridge_usage_time(),
        "udf": cartridge_usage_time.get_udf_cartridge_usage_time(),
        "ro": cartridge_usage_time.get_ro_cartridge_usage_time(),
        "t33": cartridge_usage_time.get_t33_cartridge_usage_time(),
    }


# 获取滤芯安装日期（本地时间，仅页面显示参考）
def get_filter_install_date(timestamp):
    try:
        import time
        import time_utils

        t = time.localtime(timestamp + time_utils.TIMEZONE_OFFSET)
        return "{:04d}-{:02d}-{:02d}".format(t[0], t[1], t[2])
    except Exception:
        return "未知"


# 获取系统信息：CPU 型号、ROM（flash 文件系统）总量与可用、RAM 总量与可用
def get_system_info():
    info = {"cpu": "未知", "rom_total": 0, "rom_free": 0, "ram_total": 0, "ram_free": 0}
    try:
        import os

        machine = os.uname().machine
        info["cpu"] = machine.split(" with ", 1)[1] if " with " in machine else machine
        v = os.statvfs("/")
        info["rom_total"] = v[0] * v[2]  # 块大小 × 总块数
        info["rom_free"] = v[0] * v[4]  # 块大小 × 可用块数
    except Exception:
        pass
    try:
        import esp32

        heaps = esp32.idf_heap_info(0)  # 所有堆（含 PSRAM）
        info["ram_total"] = sum(h[0] for h in heaps)
        info["ram_free"] = sum(h[1] for h in heaps)
    except Exception:
        import gc

        gc.collect()
        info["ram_total"] = gc.mem_alloc() + gc.mem_free()
        info["ram_free"] = gc.mem_free()
    return info


def _format_mb(bytes_value):
    return "{:.1f} MB".format(bytes_value / 1024 / 1024)


# 获取倒计时时间（单位：分钟）
def get_countdown_time():
    """
    返回当前倒计时时间（单位：分钟）。
    """
    return config.get_countdown_time()


# 获取 TDS 值（单位：ppm）
def get_tds():
    """
    返回当前 TDS 值（单位：ppm）。
    """
    return config.get_tds()


# 重置指定滤芯的使用时间
def reset_filter_usage(filter_name):
    """
    重置指定滤芯的使用时间。
    """
    filter_name = filter_name.lower()
    if "pp" == filter_name:
        config.reset_pp_usage()
    elif "cto" == filter_name:
        config.reset_cto_usage()
    elif "udf" == filter_name:
        config.reset_udf_usage()
    elif "ro" == filter_name:
        config.reset_ro_usage()
    elif "t33" == filter_name:
        config.reset_t33_usage()
    else:
        log.print_log(f"滤芯 {filter_name.upper()} 不存在")
        return
    log.print_log(f"重置滤芯 {filter_name.upper()} 使用时间")


# 更新强制冲洗RO膜的时间
def update_ro_force_clean_time(new_time):
    """
    更新强制冲洗RO膜的时间。
    """
    config.set_ro_force_clean_time(new_time)
    log.print_log(f"更新强制冲洗RO膜的时间为 {new_time} 分钟")


# 更新纯水洗膜运行超时时间
def update_pure_water_ro_clean_timeout(new_time):
    """
    更新纯水洗膜运行超时时间
    """
    config.set_pure_water_ro_clean_timeout(new_time)
    log.print_log(f"更新纯水洗膜运行超时时间为 {new_time} 分钟")


# 更新倒计时时间
def update_countdown_time(new_minutes):
    """
    更新倒计时时间为新的秒数值。
    """
    config.set_countdown_time(new_minutes)
    log.print_log(f"WEB 设置倒计时时间为 {new_minutes} 秒")


def update_tds(new_tds):
    """
    更新 TDS 值。
    """
    config.set_tds(new_tds)
    log.print_log(f"WEB 设置 TDS 值为 {new_tds} ppm")


def update_wifi(new_ssid, new_password):
    """
    更新 WIFI 配置。
    """
    config.set_wifi(new_ssid, new_password)
    log.print_log(f"WEB 设置 WIFI 值为 {new_ssid} | {mask_password(new_password)}")


async def apply_wifi_reconnect():
    """
    修改 WiFi 配置后后台重连（不阻塞 Web 请求）。
    最多等待约 60 秒；仍失败时由 wifi.monitor_wifi 任务继续重试。
    """
    try:
        import wifi

        log.print_log("WiFi 配置已修改，正在重连...")
        if wifi.sta_if.isconnected():
            wifi.sta_if.disconnect()
        wifi.sta_if.connect(config.get_config_value("wifi_ssid"), config.get_config_value("wifi_password"))
        for _ in range(12):  # 最多等待 60 秒
            await asyncio.sleep(5)
            if wifi.sta_if.isconnected():
                log.print_log(f"WiFi 重连成功: {wifi.sta_if.ifconfig()}")
                return
        log.print_log("WiFi 重连超时，将由监控任务继续重试")
    except Exception as e:
        log.print_log(f"WiFi 重连失败: {e}")


def is_client_disconnect_error(e):
    """客户端主动断开/连接中止（ECONNRESET/ECONNABORTED/EPIPE）不是服务器错误，静默处理"""
    try:
        return e.errno in (104, 113, 32)
    except AttributeError:
        return False


async def handle_client(reader, writer):
    try:
        # 设置超时时间（例如 300 秒）
        await asyncio.wait_for(handle_request(reader, writer), timeout=300)
    except asyncio.TimeoutError:
        log.print_log("请求超时，关闭连接")
    except Exception as e:
        if not is_client_disconnect_error(e):
            log.print_log(f"处理客户端请求时出错: {e}")
    finally:
        await writer.aclose()
        # log.print_log("客户端断开")


async def handle_request(reader, writer):
    try:
        # log.print_log("客户端连接")
        request = await reader.read(1024)  # 缓冲区大小为1024字节
        request = request.decode("utf-8")
        # 简单解析请求行（例如："GET / HTTP/1.1"）
        parts = request.split()
        if len(parts) < 2:
            return
        method = parts[0]
        path = parts[1]
        # log.print_log(f"路径: {path}")

        # 所有页面都需要 Basic Auth 认证
        if not is_authorized(request):
            response = "HTTP/1.1 401 Unauthorized\r\nWWW-Authenticate: Basic realm=\"water-purifier\"\r\nContent-Type: text/html\r\n\r\n<h1>401 Unauthorized</h1>"
            await writer.awrite(response.encode("utf-8"))
            return

        if path == "/":
            # 主菜单页面
            html = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
            html += "<html><head><meta charset='utf-8'><title>主菜单</title></head><body>"
            html += "<h1>主菜单</h1>"
            html += "<ul>"
            html += "<li><a href='/logs'>日志页面</a></li>"
            html += "<li><a href='/status'>滤芯状态页面</a></li>"
            html += "<li><a href='/wifi'>WIFI页面</a></li>"
            html += "<li><a href='/system'>系统配置</a></li>"
            html += "<li><a href='/ota'>OTA升级</a></li>"
            html += "</ul>"
            html += "</body></html>"
            await writer.awrite(html.encode("utf-8"))

        elif path == "/logs":
            # 日志列表页面
            try:
                files = os.listdir("/logs")
            except OSError:
                files = []
            log_files = [f for f in files if f.endswith(".txt") and not f.startswith("snapshot_")]
            header = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
            header += "<html><head><meta charset='utf-8'><title>日志列表</title></head><body>"
            header += "<h1>Log Files</h1><ul>"
            for log_file in log_files:
                # 获取文件大小（字节）
                file_size_bytes = os.stat(f"/logs/{log_file}")[6]
                # 转换为 KB（保留两位小数）
                file_size_kb = round(file_size_bytes / 1024, 2)
                header += f'<li><a href="/logs/{log_file}">{log_file}</a> ({file_size_kb} KB)</li>'
            header += "</ul>"
            header += "<a href='/'>返回主菜单</a>"
            header += "</body></html>"
            await writer.awrite(header.encode("utf-8"))

        elif path.startswith("/logs/") and path != "/logs":
            # 下载单个日志文件
            file_name = path[len("/logs/") :]
            # 防路径穿越：仅允许 .txt 日志文件名
            if "/" in file_name or "\\" in file_name or ".." in file_name or not file_name.endswith(".txt"):
                response = "HTTP/1.1 404 Not Found\r\nContent-Type: text/html\r\n\r\n<h1>File not found</h1>"
                await writer.awrite(response.encode("utf-8"))
                return

            file_path = "/logs/" + file_name
            log.print_log(f"文件路径: {file_path}")

            # 删除旧的快照文件
            log_snapshot_files = [f for f in os.listdir("/logs") if f.startswith("snapshot_") and f.endswith(".txt")]
            for log_snapshot_file in log_snapshot_files:
                os.remove("/logs/" + log_snapshot_file)

            if file_exists(file_path):
                log.print_log(f"文件存在: {file_path}")
                # 获取文件大小
                file_size = os.stat(file_path)[6]

                # 发送响应头
                header = f'HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\nContent-Disposition: attachment; filename="{file_name}"\r\nContent-Length: {file_size}\r\n\r\n'
                await writer.awrite(header.encode("utf-8"))

                # 分块读取文件并发送
                try:
                    with open(file_path, "r") as f:
                        while True:
                            chunk = f.read(512)  # 每次读取 512 字节
                            if not chunk:
                                break
                            await writer.awrite(chunk.encode("utf-8"))
                            await writer.drain()  # 确保数据已发送
                except Exception as e:
                    log.print_log(f"文件读取错误: {e}")
                    response = "HTTP/1.1 500 Internal Server Error\r\nContent-Type: text/html\r\n\r\n<h1>500 Internal Server Error</h1>"
                    await writer.awrite(response.encode("utf-8"))

            else:
                response = "HTTP/1.1 404 Not Found\r\nContent-Type: text/html\r\n\r\n<h1>File not found</h1>"
                await writer.awrite(response.encode("utf-8"))

        elif path == "/status":
            if method == "GET":
                # 获取滤芯使用时间和倒计时时间
                usage = get_filter_usage()
                countdown = get_countdown_time()
                tds = get_tds()

                html = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
                html += "<html><head><meta charset='utf-8'><title>滤芯状态</title></head><body>"
                html += "<h1>净水器状态</h1>"
                html += "<h2>传感器</h2>"
                html += f"<p>{log.get_state()}</p>"
                html += "<h2>滤芯使用时间（单位：天）</h2>"
                html += "<table border='1' cellspacing='0' cellpadding='5'>"
                html += "<tr><th>滤芯</th><th>使用时间</th><th>操作</th></tr>"
                for filter_name in ["pp", "cto", "udf", "ro", "t33"]:
                    html += f"<tr><td>{filter_name.upper()}</td><td>{usage.get(filter_name, 'N/A')}</td>"
                    html += "<td>"
                    html += "<form method='POST' action='/status' style='display:inline;' onsubmit=\"return confirm('确定重置滤芯吗？');\">"
                    html += "<input type='hidden' name='action' value='reset'>"
                    html += f"<input type='hidden' name='filter' value='{filter_name}'>"
                    html += "<input type='submit' value='重置'>"
                    html += "</form>"
                    html += "</td></tr>"
                html += "</table>"

                html += "<h2>纯水洗膜倒计时设置（单位：秒）</h2>"
                html += f"<p>当前倒计时: {countdown} 秒</p>"
                html += "<form method='POST' action='/status' onsubmit=\"return confirm('确定更新倒计时吗？');\">"
                html += "<input type='hidden' name='action' value='update_countdown'>"
                html += "新倒计时（秒）<1~3600>: <input type='text' name='new_countdown'>"
                html += "<input type='submit' value='更新'>"
                html += "</form>"

                html += "<h2>纯水洗膜目标TDS设置 （单位：ppm）</h2>"
                html += f"<p>当前TDS: {tds} ppm（须 ≥ 注水TDS）</p>"
                html += "<form method='POST' action='/status' onsubmit=\"return confirm('确定更新TDS吗？');\">"
                html += "<input type='hidden' name='action' value='update_tds'>"
                html += "新TDS <5~30>: <input type='text' name='new_tds'>"
                html += "<input type='submit' value='更新'>"
                html += "</form>"

                html += "<h2>压力桶注水TDS设置 （单位：ppm）</h2>"
                html += f"<p>当前注水TDS: {config.get_fill_tds()} ppm（须 ≤ 洗膜目标TDS）</p>"
                html += "<form method='POST' action='/status' onsubmit=\"return confirm('确定更新注水TDS吗？');\">"
                html += "<input type='hidden' name='action' value='update_fill_tds'>"
                html += "新注水TDS <1~20>: <input type='text' name='new_fill_tds'>"
                html += "<input type='submit' value='更新'>"
                html += "</form>"

                html += "<h2>纯水洗膜目标超时时间设置（单位：分钟）</h2>"
                html += f"<p>当前纯水洗膜目标超时时间: {config.get_config_value('pure_water_ro_clean_timeout')} 分钟</p>"
                html += "<form method='POST' action='/status' onsubmit=\"return confirm('确定更新纯水洗膜目标超时时间吗？');\">"
                html += "<input type='hidden' name='action' value='update_pure_water_ro_clean_timeout'>"
                html += "新纯水洗膜目标超时时间 <1~10>: <input type='text' name='new_pure_water_ro_clean_timeout'>"
                html += "<input type='submit' value='更新'>"
                html += "</form>"

                html += "<h2>强制冲洗RO膜累计运行时间设置（单位：分钟）</h2>"
                html += f"<p>当前强制冲洗RO膜累计运行时间: {config.get_config_value('ro_force_clean_time')} 分钟</p>"
                html += "<form method='POST' action='/status' onsubmit=\"return confirm('确定更新强制冲洗RO膜累计运行时间吗？');\">"
                html += "<input type='hidden' name='action' value='update_ro_force_clean_time'>"
                html += "新强制冲洗RO膜累计运行时间 <1~60>: <input type='text' name='new_ro_force_clean_time'>"
                html += "<input type='submit' value='更新'>"
                html += "</form>"
                html += "<br><a href='/'>返回主菜单</a>"
                html += "</body></html>"

                await writer.awrite(html.encode("utf-8"))

            elif method == "POST":
                # 解析POST数据
                post_body = ""
                if "\r\n\r\n" in request:
                    post_body = request.split("\r\n\r\n", 1)[1]
                params = {}
                for pair in post_body.split("&"):
                    if "=" in pair:
                        key, value = pair.split("=", 1)
                        params[key] = url_decode(value)  # URL 解码（+ → 空格，%XX → 字节）

                html = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
                html += "<html><head><meta charset='utf-8'><title>Status Updated</title></head><body>"

                action = params.get("action", "")
                if action == "reset" and "filter" in params:
                    filter_name = params["filter"]
                    reset_filter_usage(filter_name)
                    html += "<h1>状态更新成功</h1>"
                    html += "<p>操作成功。</p>"
                    html += "<a href='/status'>返回滤芯状态页面</a><br>"
                    html += "<a href='/'>返回主菜单</a>"
                    html += "</body></html>"
                    await writer.awrite(html.encode("utf-8"))
                elif action == "update_countdown" and "new_countdown" in params:
                    try:
                        new_countdown = int(params["new_countdown"])
                        update_countdown_time(new_countdown)
                        html += "<h1>状态更新成功</h1>"
                        html += "<p>操作成功。</p>"
                    except ValueError:
                        log.print_log("无效的倒计时数值")
                        html += "<h1>状态更新失败</h1>"
                        html += "<p>无效的倒计时数值</p>"
                    html += "<a href='/status'>返回滤芯状态页面</a><br>"
                    html += "<a href='/'>返回主菜单</a>"
                    html += "</body></html>"
                    await writer.awrite(html.encode("utf-8"))
                elif action == "update_tds" and "new_tds" in params:
                    try:
                        new_tds = int(params["new_tds"])
                        update_tds(new_tds)
                        html += "<h1>状态更新成功</h1>"
                        html += "<p>操作成功。</p>"
                    except ValueError:
                        log.print_log("无效的TDS数值")
                        html += "<h1>状态更新失败</h1>"
                        html += "<p>无效的TDS数值</p>"
                    html += "<a href='/status'>返回滤芯状态页面</a><br>"
                    html += "<a href='/'>返回主菜单</a>"
                    html += "</body></html>"
                    await writer.awrite(html.encode("utf-8"))
                elif action == "update_fill_tds" and "new_fill_tds" in params:
                    try:
                        new_fill_tds = int(params["new_fill_tds"])
                        config.set_fill_tds(new_fill_tds)
                        html += "<h1>状态更新成功</h1>"
                        html += "<p>操作成功。</p>"
                    except ValueError:
                        log.print_log("无效的注水TDS数值")
                        html += "<h1>状态更新失败</h1>"
                        html += "<p>无效的注水TDS数值</p>"
                    html += "<a href='/status'>返回滤芯状态页面</a><br>"
                    html += "<a href='/'>返回主菜单</a>"
                    html += "</body></html>"
                    await writer.awrite(html.encode("utf-8"))
                elif action == "update_ro_force_clean_time" and "new_ro_force_clean_time" in params:
                    try:
                        new_ro_force_clean_time = int(params["new_ro_force_clean_time"])
                        update_ro_force_clean_time(new_ro_force_clean_time)
                        html += "<h1>状态更新成功</h1>"
                        html += "<p>操作成功。</p>"
                    except ValueError:
                        log.print_log("无效的强制冲洗RO膜时间数值")
                        html += "<h1>状态更新失败</h1>"
                        html += "<p>无效的强制冲洗RO膜时间数值</p>"
                    html += "<a href='/status'>返回滤芯状态页面</a><br>"
                    html += "<a href='/'>返回主菜单</a>"
                    html += "</body></html>"
                    await writer.awrite(html.encode("utf-8"))
                elif action == "update_pure_water_ro_clean_timeout" and "new_pure_water_ro_clean_timeout" in params:
                    try:
                        new_pure_water_ro_clean_timeout = int(params["new_pure_water_ro_clean_timeout"])
                        update_pure_water_ro_clean_timeout(new_pure_water_ro_clean_timeout)
                        html += "<h1>状态更新成功</h1>"
                        html += "<p>操作成功。</p>"
                    except ValueError:
                        log.print_log("无效的预冲洗RO膜时间数值")
                        html += "<h1>状态更新失败</h1>"
                        html += "<p>无效的预冲洗RO膜时间数值</p>"
                    html += "<a href='/status'>返回滤芯状态页面</a><br>"
                    html += "<a href='/'>返回主菜单</a>"
                    html += "</body></html>"
                    await writer.awrite(html.encode("utf-8"))
                else:
                    response = "HTTP/1.1 404 Not Found\r\nContent-Type: text/html\r\n\r\n<h1>not found</h1>"
                    await writer.awrite(response.encode("utf-8"))

        elif path == "/system":
            if method == "GET":
                html = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
                html += "<html><head><meta charset='utf-8'><title>系统配置</title></head><body>"
                html += "<h1>系统配置</h1>"
                sys_info = get_system_info()
                html += f"<p>CPU: {sys_info['cpu']} | ROM: {_format_mb(sys_info['rom_free'])} / {_format_mb(sys_info['rom_total'])} | RAM: {_format_mb(sys_info['ram_free'])} / {_format_mb(sys_info['ram_total'])}</p>"
                html += "<h2>屏幕类型（硬件上只接一块屏，重启生效）</h2>"
                html += f"<p>当前屏幕类型: {config.get_display_type() or '（未配置，使用默认）'}</p>"
                html += "<form method='POST' action='/system'>"
                html += "<input type='hidden' name='action' value='update_display_type'>"
                html += "<select name='new_display_type'>"
                html += "<option value='oled'>OLED（SSD1306）</option>"
                html += "<option value='tft'>TFT（ST7735）</option>"
                html += "</select>"
                html += "<input type='submit' value='保存'></form>"
                html += "<h2>滤芯使用时间校准</h2>"
                usage = get_filter_usage()
                for filter_name in ["pp", "cto", "udf", "ro", "t33"]:
                    install_ts = config.get_config_value(filter_name)
                    html += f"<p>{filter_name.upper()}：使用 {usage.get(filter_name, '?')} 天（安装于 {get_filter_install_date(install_ts)}）"
                    html += "<form method='POST' action='/system' style='display:inline;'>"
                    html += "<input type='hidden' name='action' value='set_filter_usage'>"
                    html += f"<input type='hidden' name='filter' value='{filter_name}'>"
                    html += "已使用天数: <input type='number' name='days' min='0' max='3650' required>"
                    html += "<input type='submit' value='保存'></form></p>"
                html += "<h2>系统操作</h2>"
                html += "<form method='POST' action='/system' onsubmit=\"return confirm('确定重启设备吗？');\">"
                html += "<input type='hidden' name='action' value='reboot'>"
                html += "<input type='submit' value='重启系统'></form>"
                html += "<br><a href='/'>返回主菜单</a>"
                html += "</body></html>"
                await writer.awrite(html.encode("utf-8"))

            elif method == "POST":
                post_body = ""
                if "\r\n\r\n" in request:
                    post_body = request.split("\r\n\r\n", 1)[1]
                params = {}
                for pair in post_body.split("&"):
                    if "=" in pair:
                        key, value = pair.split("=", 1)
                        params[key] = url_decode(value)

                action = params.get("action", "")
                if action == "update_display_type":
                    new_display_type = params.get("new_display_type", "")
                    if new_display_type in ("oled", "tft"):
                        config.set_display_type(new_display_type)
                        log.print_log(f"WEB 设置屏幕类型: {new_display_type}（重启后生效）")
                    html = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
                    html += "<html><head><meta charset='utf-8'><title>系统配置</title></head><body>"
                    html += "<h1>屏幕类型已保存</h1><p>重启设备后生效。</p>"
                elif action == "set_filter_usage" and "filter" in params and "days" in params:
                    try:
                        days = int(params["days"])
                    except ValueError:
                        days = -1
                    if config.set_filter_usage(params["filter"], days):
                        log.print_log(f"WEB 校准滤芯 {params['filter'].upper()} 使用时间: {days} 天")
                        html = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
                        html += "<html><head><meta charset='utf-8'><title>系统配置</title></head><body>"
                        html += f"<h1>校准成功</h1><p>{params['filter'].upper()} 已校准为 {days} 天。</p>"
                    else:
                        log.print_log(f"WEB 校准滤芯失败: filter={params.get('filter')} days={days}")
                        html = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
                        html += "<html><head><meta charset='utf-8'><title>系统配置</title></head><body>"
                        html += "<h1>校准失败</h1><p>无效的滤芯名称或天数（0~3650）。</p>"
                elif action == "reboot":
                    # 先完整响应浏览器（带 Content-Length，浏览器无需等连接关闭即可完成渲染，
                    # 避免设备 reset 导致连接中断后页面一直转圈）；
                    # 页面 20 秒后自动 GET 回 /system（设备重启+WiFi 重连需要时间）
                    body = ("<html><head><meta charset='utf-8'>"
                            "<meta http-equiv='refresh' content='20; url=/system'>"
                            "</head><body><h1>设备重启中...</h1>"
                            "<p>设备正在重启，约 20 秒后自动返回系统配置页面。</p>"
                            "<p>请勿刷新本页面（会重复发送重启命令）；"
                            "若未自动跳转，请稍后手动访问 <a href='/system'>系统配置</a>。</p>"
                            "</body></html>").encode("utf-8")
                    await writer.awrite(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: " + str(len(body)).encode("utf-8") + b"\r\n\r\n" + body)
                    await writer.drain()
                    log.print_log("用户触发系统重启")
                    await asyncio.sleep(0.5)
                    import machine

                    machine.reset()
                    return
                else:
                    html = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
                    html += "<h1>未知操作</h1>"
                html += "<a href='/system'>返回系统配置</a><br>"
                html += "<a href='/'>返回主菜单</a>"
                html += "</body></html>"
                await writer.awrite(html.encode("utf-8"))

        elif path == "/ota":
            if method == "GET":
                html = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
                html += "<html><head><meta charset='utf-8'><title>OTA升级</title>"
                st = ota.get_status()
                if st["state"] in ("checking", "downloading"):
                    # 检查/下载过程中每 3 秒自动刷新，实时显示进度
                    html += "<meta http-equiv='refresh' content='3'>"
                html += "</head><body>"
                html += "<h1>OTA 升级</h1>"
                html += f"<p>当前版本: {ota.get_local_version()}</p>"
                html += f"<p>状态: {st['state']} - {st['message']} {st['progress']}</p>"
                history = st.get("history") or []
                if history:
                    html += "<h2>本次记录</h2><ul>"
                    for line in history:
                        html += f"<li>{line}</li>"
                    html += "</ul>"
                html += "<h2>更新源设置</h2>"
                html += f"<p>更新源: {config.get_ota_url() or '（未配置）'}</p>"
                html += "<form method='POST' action='/ota'>"
                html += "<input type='hidden' name='action' value='update_ota_url'>"
                html += "更新源URL: <input type='text' name='new_ota_url'>"
                html += "<input type='submit' value='保存'></form>"
                html += "<h2>升级操作</h2>"
                html += "<form method='POST' action='/ota' style='display:inline;'>"
                html += "<input type='hidden' name='action' value='check'>"
                html += "<input type='submit' value='检查更新'></form>"
                if st["state"] == "ready":
                    # 升级完成：由用户决定何时重启生效
                    html += "<form method='POST' action='/ota' style='display:inline;' onsubmit=\"return confirm('确定现在重启设备吗？');\">"
                    html += "<input type='hidden' name='action' value='reboot'>"
                    html += "<input type='submit' value='重启设备'></form>"
                html += "<form method='POST' action='/ota' style='display:inline;' onsubmit=\"return confirm('确定升级吗？升级完成后需手动重启生效');\">"
                html += "<input type='hidden' name='action' value='upgrade'>"
                html += "<input type='submit' value='升级'></form>"
                html += "<br><a href='/'>返回主菜单</a>"
                html += "</body></html>"
                await writer.awrite(html.encode("utf-8"))

            elif method == "POST":
                post_body = ""
                if "\r\n\r\n" in request:
                    post_body = request.split("\r\n\r\n", 1)[1]
                params = {}
                for pair in post_body.split("&"):
                    if "=" in pair:
                        key, value = pair.split("=", 1)
                        params[key] = url_decode(value)

                action = params.get("action", "")
                if action == "update_ota_url":
                    config.set_ota_url(params.get("new_ota_url", ""))
                    log.print_log(f"WEB 设置 OTA 更新源: {config.get_ota_url()}")
                elif action == "check":
                    # 让浏览器等待后端检查完成（只拉 manifest，通常 1-2 秒），
                    # 完成后 302 回 /ota 直接显示最终状态，无需轮询刷新
                    await ota.check_update()
                elif action == "upgrade":
                    asyncio.create_task(ota.run_ota())
                elif action == "reboot":
                    # 防重复：仅升级完成（ready）状态下允许重启；重启完成后重复的 POST
                    # （浏览器刷新重发表单）只会被 302 回 /ota，不会再次重启设备
                    if ota.get_status()["state"] != "ready":
                        await writer.awrite(b"HTTP/1.1 302 Found\r\nLocation: /ota\r\n\r\n")
                        return
                    # 先完整响应浏览器（带 Content-Length，浏览器无需等连接关闭即可完成渲染，
                    # 避免设备 reset 导致连接中断后页面一直转圈）；
                    # 页面 20 秒后自动 GET 回 /ota（设备重启+WiFi 重连需要时间）
                    body = ("<html><head><meta charset='utf-8'>"
                            "<meta http-equiv='refresh' content='20; url=/ota'>"
                            "</head><body><h1>设备重启中...</h1>"
                            "<p>升级已生效，设备正在重启，约 20 秒后自动返回 OTA 页面。</p>"
                            "<p>请勿刷新本页面（会重复发送重启命令）；"
                            "若未自动跳转，请稍后手动访问 <a href='/ota'>OTA 页面</a>。</p>"
                            "</body></html>").encode("utf-8")
                    await writer.awrite(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: " + str(len(body)).encode("utf-8") + b"\r\n\r\n" + body)
                    await writer.drain()
                    log.print_log("OTA 升级完成，用户触发重启")
                    await asyncio.sleep(0.5)
                    ota.reboot_sync()
                    return
                # 统一 302 重定向回 /ota（浏览器自动回到当前页查看最新状态）
                await writer.awrite(b"HTTP/1.1 302 Found\r\nLocation: /ota\r\n\r\n")

        elif path == "/wifi":
            if method == "GET":
                # 获取滤芯使用时间和倒计时时间
                html = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
                html += "<html><head><meta charset='utf-8'><title>WIFI配置</title></head><body>"
                html += "<h1>WIFI配置</h1>"
                html += f"<p>当前 WIFI 名称: {config.get_config_value('wifi_ssid')}</p>"
                html += f"<p>当前 WIFI 密码: {mask_password(config.get_config_value('wifi_password'))}</p>"
                html += "<form method='POST' action='/wifi' onsubmit=\"return confirm('确定更新WIFI吗？');\">"
                html += "<input type='hidden' name='action' value='update_wifi'>"
                html += "<br>"
                html += "新 WIFI 名称（支持中文但不建议使用；≤32字节≈10个汉字）: <input type='text' name='new_wifi_ssid'>"
                html += "<br>"
                html += "新 WIFI 密码: <input type='text' name='new_wifi_password'>"
                html += "<br>"
                html += "<input type='submit' value='更新'>"
                html += "</form>"

                html += "<h2>修改 Web 访问密码</h2>"
                html += "<form method='POST' action='/wifi' onsubmit=\"return confirm('确定修改访问密码吗？');\">"
                html += "<input type='hidden' name='action' value='update_web_password'>"
                html += "新密码（4~32 位）: <input type='password' name='new_web_password'>"
                html += "<input type='submit' value='修改'>"
                html += "</form>"
                html += "<br><a href='/'>返回主菜单</a>"
                html += "</body></html>"

                await writer.awrite(html.encode("utf-8"))

            elif method == "POST":
                # 解析POST数据
                post_body = ""
                if "\r\n\r\n" in request:
                    post_body = request.split("\r\n\r\n", 1)[1]
                params = {}
                for pair in post_body.split("&"):
                    if "=" in pair:
                        key, value = pair.split("=", 1)
                        params[key] = url_decode(value)  # URL 解码（+ → 空格，%XX → 字节）

                html = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
                html += "<html><head><meta charset='utf-8'><title>Status Updated</title></head><body>"
                html += "<h1>WIFI配置</h1>"

                action = params.get("action", "")
                if action == "update_wifi" and "new_wifi_ssid" in params and "new_wifi_password" in params:
                    new_ssid = params["new_wifi_ssid"]
                    new_password = params["new_wifi_password"]
                    if validate_wifi(new_ssid, new_password):
                        update_wifi(new_ssid, new_password)
                        asyncio.create_task(apply_wifi_reconnect())  # 后台重连，无需重启
                        html += "<p>更新成功，正在重连...</p>"
                    else:
                        html += "<p>更新失败。</p>"
                        html += "<p>名称或密码不合法。</p>"

                    html += "<a href='/wifi'>返回WIFI配置页面</a><br>"
                    html += "<a href='/'>返回主菜单</a>"
                    html += "</body></html>"
                    await writer.awrite(html.encode("utf-8"))
                elif action == "update_web_password" and "new_web_password" in params:
                    new_password = params["new_web_password"]
                    if 4 <= len(new_password) <= 32:
                        config.set_web_password(new_password)
                        log.print_log("WEB 访问密码已修改")
                        html += "<p>访问密码修改成功，下次访问请使用新密码。</p>"
                    else:
                        html += "<p>密码长度需为 4~32 位。</p>"
                    html += "<a href='/wifi'>返回WIFI配置页面</a><br>"
                    html += "<a href='/'>返回主菜单</a>"
                    html += "</body></html>"
                    await writer.awrite(html.encode("utf-8"))
                else:
                    response = "HTTP/1.1 404 Not Found\r\nContent-Type: text/html\r\n\r\n<h1>not found</h1>"
                    await writer.awrite(response.encode("utf-8"))
        else:
            response = "HTTP/1.1 404 Not Found\r\nContent-Type: text/html\r\n\r\n<h1>404 Not Found</h1>"
            await writer.awrite(response.encode("utf-8"))

        await writer.aclose()
        # log.print_log("客户端断开")

    except MemoryError:
        log.print_log("内存不足，尝试释放资源...")
        import gc

        gc.collect()
        response = "HTTP/1.1 500 Internal Server Error\r\nContent-Type: text/html\r\n\r\n<h1>500 Internal Server Error</h1>"
        await writer.awrite(response.encode("utf-8"))
    except Exception as e:
        if not is_client_disconnect_error(e):
            log.print_log(f"处理客户端请求时出错: {e}")


# 启动Web服务器
async def start_web_server():
    while True:
        try:
            log.print_log("启动Web服务器")
            server = await asyncio.start_server(handle_client, ADDRESS, PORT)
            log.print_log(f"Web服务器启动成功 [http://{ADDRESS}:{PORT}]")
            await server.wait_closed()
        except Exception as e:
            log.print_log(f"Web服务器异常关闭: {e}")
        finally:
            await asyncio.sleep(1)
