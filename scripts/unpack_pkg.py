#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wallpaper Engine .pkg 解包器（实测格式，2026-08 实测验证）

真实头部布局（重要！网上旧资料是错的，实测修正）:
    offset 0:  主版本   4B  小端（实测 = 8，pkg 格式版本）
    offset 4:  magic    4B  "PKGV"
    offset 8:  压缩标识 4B  ASCII 字符串 "0021"（21 = raw 数据段；旧格式 "0011" = gzip）
    offset 12: fileCount 4B  ← 不是 headerSize！实测 26 条
    offset 16: index: fileCount × [nameLen(4B) name offset(4B) size(4B)]
    之后:      数据段，offset 为【相对数据段起点】的偏移

坑: 把 offset 12 当 headerSize、把数据段当绝对偏移，都会解出错位垃圾文件
    （scene.json 变成 index 内容、tex 带 JSON 前缀）。已验证:
    末条目 offset+size = 数据段起点 + 文件尾，scene.json 合法 JSON，
    tex 以 TEXV0005 开头。

scene.pkg 的同名多版本条目（xxx 与 xxx_v1/_v2）取无后缀版本（画质最高）。

用法:
    python3 unpack_pkg.py <xxx.pkg> <输出目录> [--keep-named-versioned]
"""
import argparse
import gzip
import struct
import sys
from pathlib import Path


def unpack_pkg(pkg_path: str, out_dir: str, keep_versioned: bool = False) -> list:
    """解包 pkg，返回导出的文件列表"""
    data = Path(pkg_path).read_bytes()
    if data[4:8] != b"PKGV":
        print(f"[!] 不是 PKG 文件 (magic={data[4:8]!r})", file=sys.stderr)
        return []

    main_ver = struct.unpack_from("<I", data, 0)[0]
    compression = data[8:12]
    file_count = struct.unpack_from("<I", data, 12)[0]
    print(f"[pkg] mainVer={main_ver} compression={compression!r} fileCount={file_count}")

    off = 16
    entries = []
    for _ in range(file_count):
        name_len = struct.unpack_from("<I", data, off)[0]
        off += 4
        name = data[off:off + name_len].decode("utf-8", "replace")
        off += name_len
        entry_off, size = struct.unpack_from("<II", data, off)
        off += 8
        entries.append((name, entry_off, size))

    data_start = off  # 数据段起点 = index 结束
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    exported = []
    seen = set()
    gz = compression == b"0011"  # 旧格式 gzip
    for name, eoff, size in entries:
        # 同名多版本条目：xxx 和 xxx_v1/_v2，取无后缀版本
        if not keep_versioned:
            base = name.rsplit("_v", 1)[0] if "_v" in name and name.rsplit("_v", 1)[1].isdigit() else name
            if base in seen and base != name:
                continue
            seen.add(base)
            if base != name:
                name = base
        abs_off = data_start + eoff
        seg = data[abs_off:abs_off + size]
        if gz:
            try:
                seg = gzip.decompress(seg)
            except Exception as e:
                print(f"[!] 解压失败 {name}: {e}", file=sys.stderr)
                continue
        elif seg[:2] == b"\x1f\x8b":
            # 容错：个别段仍是 gzip
            try:
                seg = gzip.decompress(seg)
            except Exception:
                pass
        f = out / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(seg)
        exported.append(str(f))
        print(f"  -> {name} ({len(seg)} bytes)")
    return exported


def main():
    ap = argparse.ArgumentParser(description="Wallpaper Engine pkg 解包")
    ap.add_argument("pkg", help="输入 .pkg 文件")
    ap.add_argument("out", help="输出目录")
    ap.add_argument("--keep-named-versioned", action="store_true", help="保留 _v1/_v2 命名版本条目")
    args = ap.parse_args()
    unpack_pkg(args.pkg, args.out, args.keep_named_versioned)


if __name__ == "__main__":
    main()
