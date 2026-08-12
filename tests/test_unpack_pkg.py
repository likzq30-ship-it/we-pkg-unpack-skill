#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pkg 解析器测试：正常解包 / gzip / 多版本选择 / 恶意输入 / 路径穿越"""
import gzip
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import unpack_pkg
from unpack_pkg import PkgError, unpack_pkg


def build_pkg(entries, main_ver=8, compression=b"0021"):
    """合成最小 pkg。entries: [(name, data_bytes)]"""
    index = b""
    offset = 0
    for name, _data in entries:
        nb = name.encode("utf-8")
        index += struct.pack("<I", len(nb)) + nb + struct.pack("<II", offset, len(_data))
        offset += len(_data)
    payload = b"".join(d for _n, d in entries)
    header = struct.pack("<I", main_ver) + b"PKGV" + compression + struct.pack("<I", len(entries))
    return header + index + payload


class TestPkgParser(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "out"

    def tearDown(self):
        self.tmp.cleanup()

    def test_basic_unpack(self):
        pkg = build_pkg([("scene.json", b'{"ok": true}'), ("materials/a.tex", b"TEXV0005\x00TEXI")])
        f = Path(self.tmp.name) / "t.pkg"
        f.write_bytes(pkg)
        exported = unpack_pkg(str(f), str(self.out))
        self.assertEqual(len(exported), 2)
        self.assertEqual((self.out / "scene.json").read_bytes(), b'{"ok": true}')
        self.assertEqual((self.out / "materials/a.tex").read_bytes(), b"TEXV0005\x00TEXI")

    def test_gzip_segment(self):
        comp = gzip.compress(b"hello gzip")
        pkg = build_pkg([("data.txt", comp)], compression=b"0011")
        f = Path(self.tmp.name) / "g.pkg"
        f.write_bytes(pkg)
        unpack_pkg(str(f), str(self.out))
        self.assertEqual((self.out / "data.txt").read_bytes(), b"hello gzip")

    def test_version_chooses_largest(self):
        """xxx / xxx_v1 → 选数据最大的（不默认无后缀）"""
        pkg = build_pkg([
            ("tex.png", b"small"),
            ("tex.png_v1", b"LARGER-DATA-1234567890"),
            ("tex.png_v2", b"mid"),
        ])
        f = Path(self.tmp.name) / "v.pkg"
        f.write_bytes(pkg)
        unpack_pkg(str(f), str(self.out))
        self.assertEqual((self.out / "tex.png").read_bytes(), b"LARGER-DATA-1234567890")

    def test_keep_versioned_flag(self):
        pkg = build_pkg([("a.bin", b"x"), ("a.bin_v1", b"yyyy")])
        f = Path(self.tmp.name) / "k.pkg"
        f.write_bytes(pkg)
        unpack_pkg(str(f), str(self.out), keep_versioned=True)
        self.assertTrue((self.out / "a.bin_v1").exists())
        self.assertTrue((self.out / "a.bin").exists())

    def test_path_traversal_rejected(self):
        """恶意文件名 ../evil.sh 必须被拒绝且不写出文件"""
        pkg = build_pkg([("../../evil.sh", b"rm -rf /")])
        f = Path(self.tmp.name) / "evil.pkg"
        f.write_bytes(pkg)
        exported = unpack_pkg(str(f), str(self.out))
        self.assertEqual(exported, [])
        self.assertFalse(Path(self.tmp.name, "evil.sh").exists())

    def test_tiny_file(self):
        f = Path(self.tmp.name) / "tiny.pkg"
        f.write_bytes(b"short")
        with self.assertRaises(PkgError):
            unpack_pkg(str(f), str(self.out))

    def test_bad_magic(self):
        f = Path(self.tmp.name) / "bad.pkg"
        f.write_bytes(b"\x00" * 32)
        with self.assertRaises(PkgError):
            unpack_pkg(str(f), str(self.out))

    def test_huge_file_count(self):
        """fileCount=0xFFFFFFFF 恶意值必须被拒"""
        pkg = struct.pack("<I", 8) + b"PKGV" + b"0021" + struct.pack("<I", 0xFFFFFFFF)
        f = Path(self.tmp.name) / "huge.pkg"
        f.write_bytes(pkg)
        with self.assertRaises(PkgError):
            unpack_pkg(str(f), str(self.out))

    def test_zero_file_count(self):
        pkg = struct.pack("<I", 8) + b"PKGV" + b"0021" + struct.pack("<I", 0)
        f = Path(self.tmp.name) / "zero.pkg"
        f.write_bytes(pkg)
        with self.assertRaises(PkgError):
            unpack_pkg(str(f), str(self.out))

    def test_out_of_bounds_data(self):
        """条目声明的数据越界文件尾 → 拒绝"""
        nb = b"a.bin"
        index = struct.pack("<I", len(nb)) + nb + struct.pack("<II", 0, 999999)
        pkg = struct.pack("<I", 8) + b"PKGV" + b"0021" + struct.pack("<I", 1) + index + b"data"
        f = Path(self.tmp.name) / "oob.pkg"
        f.write_bytes(pkg)
        with self.assertRaises(PkgError):
            unpack_pkg(str(f), str(self.out))

    def test_truncated_index(self):
        """index 条目截断 → 拒绝"""
        nb = b"a.bin"
        pkg = struct.pack("<I", 8) + b"PKGV" + b"0021" + struct.pack("<I", 2)
        pkg += struct.pack("<I", len(nb)) + nb + struct.pack("<II", 0, 4)
        pkg += b"\x05\x00"  # 第二个条目只有 2 字节
        f = Path(self.tmp.name) / "trunc.pkg"
        f.write_bytes(pkg)
        with self.assertRaises(PkgError):
            unpack_pkg(str(f), str(self.out))


if __name__ == "__main__":
    unittest.main()
