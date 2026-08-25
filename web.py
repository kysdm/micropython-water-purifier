import asyncio
import os
import re

import log
import config
import cartridge_usage_time


ADDRESS = "0.0.0.0"
PORT = 80


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
    :param ssid: WiFi 名称，要求非空、不超过 32 个字符，且只能包含英文、数字及部分常见符号
    :param password: WiFi 密码，要求长度在 8 到 63 个字符之间
    :return: 合法返回 True，否则返回 False
    """
    # 检查 ssid 长度
    if not isinstance(ssid, str) or len(ssid) == 0 or len(ssid) > 32:
        return False

    # 允许的字符：英文、数字、空格，以及 !@#$%^&*()_+-=
    pattern = r"^[a-zA-Z0-9\s!@#$%^&*()_\+\-=]+$"
    if not re.match(pattern, ssid) or len(ssid) != len(re.match(pattern, ssid).group(0)):
        return False

    # 检查密码
    if not isinstance(password, str) or not (8 <= len(password) <= 63):
        return False

    return True


# def create_snapshot_file(file_path, snapshot_path):
#     """
#     创建快照文件。
#     """
#     with open(file_path, "rb") as src, open(snapshot_path, "wb") as dst:
#         while True:
#             chunk = src.read(512)
#             if not chunk:
#                 break
#             dst.write(chunk)


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
    log.print_log(f"WEB 设置 WIFI 值为 {new_ssid} | {new_password}")


async def handle_client(reader, writer):
    try:
        # 设置超时时间（例如 300 秒）
        await asyncio.wait_for(handle_request(reader, writer), timeout=300)
    except asyncio.TimeoutError:
        log.print_log("请求超时，关闭连接")
    except Exception as e:
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

        if path == "/":
            # 主菜单页面
            html = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
            html += "<html><head><meta charset='utf-8'><title>主菜单</title></head><body>"
            html += "<h1>主菜单</h1>"
            html += "<ul>"
            html += "<li><a href='/logs'>日志页面</a></li>"
            html += "<li><a href='/status'>滤芯状态页面</a></li>"
            html += "<li><a href='/wifi'>WIFI页面</a></li>"
            html += "</ul>"
            html += "</body></html>"
            await writer.awrite(html.encode("utf-8"))

        elif path == "/logs":
            # 日志列表页面
            files = os.listdir("/logs")
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
                html += f"<p>当前TDS: {tds} ppm</p>"
                html += "<form method='POST' action='/status' onsubmit=\"return confirm('确定更新TDS吗？');\">"
                html += "<input type='hidden' name='action' value='update_tds'>"
                html += "新TDS <5~30>: <input type='text' name='new_tds'>"
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
                        params[key] = value  # 这里未做URL解码处理

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

        elif path == "/wifi":
            if method == "GET":
                # 获取滤芯使用时间和倒计时时间
                html = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
                html += "<html><head><meta charset='utf-8'><title>WIFI配置</title></head><body>"
                html += "<h1>WIFI配置</h1>"
                html += f"<p>当前 WIFI 名称: {config.get_config_value('wifi_ssid')}</p>"
                html += f"<p>当前 WIFI 密码: {config.get_config_value('wifi_password')}</p>"
                html += "<form method='POST' action='/wifi' onsubmit=\"return confirm('确定更新WIFI吗？');\">"
                html += "<input type='hidden' name='action' value='update_wifi'>"
                html += "<br>"
                html += "新 WIFI 名称 (不支持中文): <input type='text' name='new_wifi_ssid'>"
                html += "<br>"
                html += "新 WIFI 密码: <input type='text' name='new_wifi_password'>"
                html += "<br>"
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
                        params[key] = value  # 这里未做URL解码处理

                html = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
                html += "<html><head><meta charset='utf-8'><title>Status Updated</title></head><body>"
                html += "<h1>WIFI配置</h1>"

                action = params.get("action", "")
                if action == "update_wifi" and "new_wifi_ssid" in params and "new_wifi_password" in params:
                    log.print_log(params)
                    new_ssid = params["new_wifi_ssid"]
                    new_password = params["new_wifi_password"]
                    if validate_wifi(new_ssid, new_password):
                        update_wifi(new_ssid, new_password)
                        html += "<p>更新成功。</p>"
                    else:
                        html += "<p>更新失败。</p>"
                        html += "<p>名称或密码不合法。</p>"

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
