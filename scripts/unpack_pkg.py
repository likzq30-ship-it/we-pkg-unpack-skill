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

安全设计（Agent 可安全解包不可信来源 pkg）:
    - 校验文件最小长度 / fileCount 上限 / nameLen 范围 / 条目边界
    - 数据段 offset+size 越界检查
    - 路径穿越防护: 解出的文件路径 resolve() 后必须仍在输出目录内，否则拒绝

同名多版本条目（xxx 与 xxx_v1/_v2）:
    - 不默认"无后缀 = 最好"，而是解出所有候选后按数据大小选最大

用法:
    python3 unpack_pkg.py <xxx.pkg> <输出目录> [--keep-named-versioned]
"""
import argparse
import gzip
import struct
import sys
from pathlib import Path

PKG_MAGIC = b"PKGV"
MAX_FILES = 65536          # fileCount 硬上限（防恶意构造）
MAX_NAME_LEN = 4096        # 单个文件名长度上限
MIN_PKG_SIZE = 16          # header 最小长度


class PkgError(Exception):
    """pkg 解析错误（损坏/恶意文件）"""


def _check_bounds(data: bytes, off: int, size: int, what: str):
    if off < 0 or size < 0 or off + size > len(data):
        raise PkgError(f"越界: {what} @{off} size={size} (文件 {len(data)}B)")


def _safe_target(out: Path, name: str) -> Path:
    """路径穿越防护: 目标必须位于 out 目录内，否则抛 PkgError"""
    out_resolved = out.resolve()
    target = (out / name).resolve()
    if target != out_resolved and out_resolved not in target.parents:
        raise PkgError(f"拒绝路径穿越: {name!r}")
    return target


def _parse_index(data: bytes) -> tuple:
    """解析 index 表，返回 (entries, data_start)；含全部边界校验"""
    if len(data) < MIN_PKG_SIZE:
        raise PkgError(f"文件过小: {len(data)}B < {MIN_PKG_SIZE}B")
    if data[4:8] != PKG_MAGIC:
        raise PkgError(f"不是 PKG 文件 (magic={data[4:8]!r})")

    main_ver = struct.unpack_from("<I", data, 0)[0]
    compression = data[8:12]
    file_count = struct.unpack_from("<I", data, 12)[0]
    if file_count == 0 or file_count > MAX_FILES:
        raise PkgError(f"fileCount 异常: {file_count} (上限 {MAX_FILES})")

    off = 16
    entries = []
    for i in range(file_count):
        _check_bounds(data, off, 4, f"entry[{i}] nameLen")
        name_len = struct.unpack_from("<I", data, off)[0]
        if name_len == 0 or name_len > MAX_NAME_LEN:
            raise PkgError(f"entry[{i}] nameLen 异常: {name_len}")
        off += 4
        _check_bounds(data, off, name_len + 8, f"entry[{i}] 剩余字段")
        name = data[off:off + name_len].decode("utf-8", "replace")
        off += name_len
        entry_off, size = struct.unpack_from("<II", data, off)
        off += 8
        entries.append((name, entry_off, size))
    return main_ver, compression, entries, off


def _select_best_versions(entries: list) -> list:
    """
    同名多版本选择: xxx / xxx_v1 / xxx_v2 → 按数据 size 选最大。
    返回去重后的 (name, entry_off, size) 列表。
    """
    grouped = {}
    for name, eoff, size in entries:
        base = name
        if "_v" in name:
            stem, _, tail = name.rpartition("_v")
            if tail.isdigit():
                base = stem
        grouped.setdefault(base, []).append((name, eoff, size))
    chosen = []
    for base, cands in grouped.items():
        best = max(cands, key=lambda c: c[2])  # 按数据大小选最大
        # 输出统一用基础名（去掉 _v 后缀），避免把版本号带进文件名
        chosen.append((base, best[1], best[2]))
    return chosen


def unpack_pkg(pkg_path: str, out_dir: str, keep_versioned: bool = False) -> list:
    """解包 pkg，返回导出的文件列表。损坏/恶意文件抛 PkgError。"""
    data = Path(pkg_path).read_bytes()
    main_ver, compression, entries, data_start = _parse_index(data)
    print(f"[pkg] mainVer={main_ver} compression={compression!r} "
          f"fileCount={len(entries)} dataStart={data_start}")

    if not keep_versioned:
        entries = _select_best_versions(entries)
        print(f"[pkg] 去重多版本后: {len(entries)} 个文件")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    out_resolved = out.resolve()
    exported = []
    gz = compression == b"0011"  # 旧格式 gzip

    for name, eoff, size in entries:
        # 数据段边界校验（offset 相对数据段起点）
        abs_off = data_start + eoff
        _check_bounds(data, abs_off, size, name)
        seg = data[abs_off:abs_off + size]

        if gz:
            try:
                seg = gzip.decompress(seg)
            except Exception as e:
                raise PkgError(f"gzip 解压失败 {name}: {e}")
        elif seg[:2] == b"\x1f\x8b":
            # 容错：个别段仍是 gzip
            try:
                seg = gzip.decompress(seg)
            except Exception:
                pass

        # 路径穿越防护 + 写入
        try:
            target = _safe_target(out_resolved, name)
        except PkgError as e:
            print(f"  [skip] {e}", file=sys.stderr)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(seg)
        exported.append(str(target))
        print(f"  -> {name} ({len(seg)} bytes)")
    return exported


def main():
    ap = argparse.ArgumentParser(description="Wallpaper Engine pkg 解包（安全加固版）")
    ap.add_argument("pkg", help="输入 .pkg 文件")
    ap.add_argument("out", help="输出目录")
    ap.add_argument("--keep-named-versioned", action="store_true",
                    help="保留所有 _v1/_v2 命名版本条目（默认按大小选最大）")
    args = ap.parse_args()
    try:
        unpack_pkg(args.pkg, args.out, args.keep_named_versioned)
    except PkgError as e:
        print(f"[!] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
