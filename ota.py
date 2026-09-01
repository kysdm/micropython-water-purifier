# ota.py — OTA 文件级升级（更新 .py 代码文件，不刷固件）
#
# 更新源结构（发布端用 tools/make_ota.py 生成）：
#   <base_url>/manifest.json   {"version": "...", "files": [{"path": "water.py", "sha256": "..."}]}
#   <base_url>/<path>          各代码文件
#
# 流程：检查版本 → 下载清单 → 逐个下载（临时文件 + SHA-256 校验）→ 覆盖 → 写本地版本 → 手动重启。
# 下载在 network_hardware 线程执行，不阻塞主事件循环。

import hashlib
import json
import os

import config
import log
import threadsafe_context
import urequests

OTA_VERSION_FILE = "ota_version.txt"
OTA_TMP_SUFFIX = ".ota_tmp"
_OTA_FILE_EXTS = (".py",)  # 只允许覆盖代码文件，防路径穿越/覆盖任意文件

# 状态记录（供 /ota 页面轮询显示）；history 保留本次操作的逐文件记录（跳过/下载/失败）
_ota_status = {"state": "idle", "message": "", "progress": "", "history": []}
_OTA_HISTORY_MAX = 50  # 历史记录条数上限，防止内存无限增长


def get_status():
    return dict(_ota_status)


def get_local_version():
    try:
        with open(OTA_VERSION_FILE, "r") as f:
            return f.read().strip()
    except OSError:
        return "0"


def _save_local_version(v):
    try:
        with open(OTA_VERSION_FILE, "w") as f:
            f.write(v)
    except OSError as e:
        log.print_log(f"OTA 保存版本号失败: {e}")


def _set_status(state, message="", progress=""):
    _ota_status["state"] = state
    _ota_status["message"] = message
    _ota_status["progress"] = progress


def _append_history(msg):
    """追加一条本次操作记录（/ota 页面显示所有记录用），超出上限丢弃最旧记录"""
    history = _ota_status.setdefault("history", [])
    history.append(msg)
    if len(history) > _OTA_HISTORY_MAX:
        del history[0]


def _fetch_text(url, timeout=10):
    """同步获取小文件文本（manifest 等）"""
    import gc

    gc.collect()  # TLS 握手解析证书链需较多内存，先释放缓存避免 MBEDTLS_ERR_X509_ALLOC_FAILED
    resp = urequests.get(url, timeout=timeout)
    try:
        return resp.text
    finally:
        resp.close()


def _fetch_manifest(base_url):
    """下载并解析 manifest.json；返回 (manifest, 错误消息)"""
    try:
        manifest = json.loads(_fetch_text(base_url + "manifest.json"))
        if not isinstance(manifest, dict) or not manifest.get("version"):
            return None, "清单格式错误（缺少 version）"
        return manifest, None
    except Exception as e:
        return None, f"获取清单失败: {e}"


def _local_sha256(path):
    """计算本地文件 SHA-256（hex）；文件不存在返回 None"""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(1024)
                if not chunk:
                    break
                h.update(chunk)
        return h.digest().hex()
    except OSError:
        return None


def _download_verify_overwrite(base_url, path, sha256):
    """分块下载 + SHA-256 校验 + 覆盖文件；返回错误消息（None=成功）"""
    tmp = path + OTA_TMP_SUFFIX
    h = hashlib.sha256()
    try:
        resp = urequests.get(base_url + path, timeout=30)
        try:
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.raw.read(1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    h.update(chunk)
        finally:
            resp.close()
    except Exception as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return f"下载 {path} 失败: {e}"
    if h.digest().hex() != sha256:  # MicroPython hashlib 无 hexdigest，用 digest().hex()
        try:
            os.remove(tmp)
        except OSError:
            pass
        return f"{path} 校验失败（哈希不符）"
    os.rename(tmp, path)  # 覆盖原文件（先完整下载校验，失败不影响旧文件）
    return None


def ota_sync():
    """OTA 主流程（在 network_hardware 线程同步执行）。返回提示文本"""
    import gc

    gc.collect()
    base_url = config.get_ota_url()
    if not base_url:
        return "OTA 未配置（config.json 的 ota_url）"
    if not base_url.endswith("/"):
        base_url += "/"

    _ota_status["history"] = []  # 清空上一次操作记录
    _set_status("checking", "正在检查更新...", "")
    manifest, err = _fetch_manifest(base_url)
    if err:
        _set_status("error", err, "")
        _append_history(f"获取清单失败: {err}")
        log.print_log(f"OTA 升级失败（获取清单）: {err}")
        return err
    version = manifest.get("version", "")

    local = get_local_version()
    if version == local:
        _set_status("idle", f"已是最新版本（{local}）", "")
        _append_history(f"已是最新版本（{local}）")
        return f"已是最新版本（{local}）"

    _set_status("checking", f"发现新版本 {version}（当前 {local}），准备升级...", "")
    _append_history(f"发现新版本 {version}（当前 {local}）")
    files = manifest.get("files", [])
    if not files:
        _set_status("error", "清单中没有文件", "")
        _append_history("清单中没有文件")
        return "清单中没有文件"

    total = len(files)
    for i, entry in enumerate(files):
        path = entry.get("path", "") if isinstance(entry, dict) else ""
        sha = entry.get("sha256", "") if isinstance(entry, dict) else ""
        # 安全校验：只允许 .py 文件，拒绝路径穿越（.. / 反斜杠）
        if ".." in path or "\\" in path or not path.endswith(_OTA_FILE_EXTS):
            _set_status("error", f"非法文件路径: {path}", "")
            _append_history(f"非法文件路径: {path}")
            return f"非法文件路径: {path}"
        # 本地文件哈希一致则跳过（只下载变更文件，加快更新）
        if _local_sha256(path) == sha:
            _set_status("downloading", f"{path} 已是最新，跳过", f"{i + 1}/{total}")
            _append_history(f"{path} 已是最新，跳过")
            continue
        _set_status("downloading", f"下载 {path}...", f"{i + 1}/{total}")
        _append_history(f"下载 {path}...")
        err = _download_verify_overwrite(base_url, path, sha)
        if err:
            _set_status("error", err, f"{i + 1}/{total}")
            _append_history(f"{path} 失败: {err}")
            return err

    _save_local_version(version)
    log.print_log(f"OTA 升级完成，当前版本 {version}，等待用户重启")
    _set_status("ready", f"升级完成（{version}），请点击重启生效", f"{total}/{total}")
    _append_history(f"升级完成（{version}），请点击重启生效")
    return f"升级完成（{version}），请点击重启生效"
 

def check_sync():
    """只检查远端是否有新版本（不下载）。返回提示文本"""
    import gc

    gc.collect()
    base_url = config.get_ota_url()
    if not base_url:
        return "OTA 未配置（config.json 的 ota_url）"
    if not base_url.endswith("/"):
        base_url += "/"
    _ota_status["history"] = []  # 清空上一次操作记录
    manifest, err = _fetch_manifest(base_url)
    if err:
        _set_status("error", err, "")
        _append_history(f"获取清单失败: {err}")
        log.print_log(f"OTA 检查更新失败: {err}")
        return err
    version = manifest.get("version", "")
    local = get_local_version()
    if version == local:
        msg = f"已是最新版本（{local}）"
    else:
        msg = f"发现新版本 {version}（当前 {local}），可执行升级"
    _set_status("idle", msg, "")
    _append_history(msg)
    return msg

 
async def check_update():
    """异步检查更新（network_hardware 线程）"""
    return await threadsafe_context.network_hardware.assign(check_sync)


def reboot_sync():
    """立即重启设备（OTA 升级完成后由用户触发）"""
    import machine

    machine.reset()


async def run_ota():
    """异步入口：在 network_hardware 线程执行，不阻塞主事件循环"""
    return await threadsafe_context.network_hardware.assign(ota_sync)
