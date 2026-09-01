#!/usr/bin/env python3
# tools/make_ota.py — 生成 OTA 更新包（在电脑上运行）
#
# 用法: python3 tools/make_ota.py [输出目录] [版本号]
# 无参数（默认）：在仓库根目录生成 manifest.json——仓库本身即更新源，
#   配合 raw.githubusercontent.com 或本地 http.server 使用，不复制文件；
# 带输出目录：复制模式——生成 <输出目录>/ 更新包（文件副本 + manifest.json），
#   适合把更新包放到独立目录/服务器。
# 版本号默认为生成时刻时间戳（如 202609011832，与本地版本不同即触发升级；
# 每次生成都不同，无需手动打版本号）
#
# 生成内容：
#   manifest.json    版本号 + 文件清单（路径 + SHA-256）
#   （复制模式）各 .py 文件  更新文件副本

import hashlib
import json
import os
import shutil
import sys
import time


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def collect_files(project):
    """收集顶层 .py 与 lib/threadsafe/*.py"""
    files = []
    for name in sorted(os.listdir(project)):
        if name.endswith(".py") and os.path.isfile(os.path.join(project, name)):
            files.append(name)
    lib_dir = os.path.join(project, "lib")
    ts_dir = os.path.join(lib_dir, "threadsafe")
    if os.path.isdir(ts_dir):
        for name in sorted(os.listdir(ts_dir)):
            if name.endswith(".py"):
                files.append(os.path.join("lib", "threadsafe", name))
    return files


def build_manifest(project, files, version, dest_dir, copy_files):
    """生成 manifest.json；copy_files=True 时同时复制文件副本到 dest_dir"""
    os.makedirs(dest_dir, exist_ok=True)
    manifest = {"version": version, "files": []}
    for rel in files:
        src = os.path.join(project, rel)
        if copy_files:
            dst = os.path.join(dest_dir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        manifest["files"].append({"path": rel, "sha256": sha256_file(src)})
    with open(os.path.join(dest_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def main():
    project = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files = collect_files(project)
    version = time.strftime("%Y%m%d%H%M%S")

    if len(sys.argv) > 1:
        # 复制模式：生成 <输出目录>/ 更新包
        out_dir = sys.argv[1]
        version = sys.argv[2] if len(sys.argv) > 2 else version
        build_manifest(project, files, version, out_dir, copy_files=True)
        print(f"OTA 更新包已生成: {out_dir}/（版本 {version}，{len(files)} 个文件）")
        print("上传该目录到 HTTP 服务器，然后设备 /ota 页面填写更新源 URL 即可升级。")
    else:
        # 根目录模式（默认）：仓库根目录即更新源，只生成 manifest.json
        build_manifest(project, files, version, project, copy_files=False)
        print(f"manifest.json 已生成（版本 {version}，{len(files)} 个文件），"
              "提交并推送后设备即可升级。")


if __name__ == "__main__":
    main()
