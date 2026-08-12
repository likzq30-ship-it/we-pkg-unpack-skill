#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tex 解码库测试：头部解析 / 内嵌媒体提取 / BC1 解码 / 损坏文件"""
import io
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from texlib import (TexError, decode_bc1_block, decode_texture, extract_inline_image,
                    extract_inline_video, parse_tex, tex2image_fast)

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


def make_png_bytes(w=2, h=2):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 40)).save(buf, "PNG")
    return buf.getvalue()


def make_tex(texb_magic=b"TEXB0003", embedded=None, fmt=14, w=64, h=64):
    """合成最小 TEXV0005 纹理。
    embedded=None → 只有空 TEXB 段；否则 embedded 字节拼进段。
    """
    header = struct.pack("<IIIIIII", fmt, 0, w, h, w, h, 0)
    seg = texb_magic + struct.pack("<I", fmt)
    if embedded:
        seg += embedded
    return b"TEXV0005\x00" + b"TEXI0001\x00" + header + seg


class TestTexParser(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_header(self):
        data = make_tex(w=64, h=32)
        info = parse_tex(data)
        self.assertEqual(info["texture_size"], (64, 32))
        self.assertEqual(info["image_size"], (64, 32))
        self.assertEqual(info["format"], 14)

    def test_parse_short_file(self):
        with self.assertRaises(TexError):
            parse_tex(b"\x00" * 8)

    def test_parse_bad_magic(self):
        with self.assertRaises(TexError):
            parse_tex(b"NOTATEXV" + b"\x00" * 64)

    @unittest.skipUnless(HAVE_PIL, "需要 Pillow")
    def test_extract_embedded_png(self):
        png = make_png_bytes()
        tex = make_tex(embedded=png, fmt=14)
        f = Path(self.tmp.name) / "t.tex"
        f.write_bytes(tex)
        media = tex2image_fast(str(f))
        self.assertTrue(any(k == "png" for k, _ in media))

    @unittest.skipUnless(HAVE_PIL, "需要 Pillow")
    def test_decode_texture_embedded(self):
        png = make_png_bytes()
        tex = make_tex(embedded=png, fmt=14)
        f = Path(self.tmp.name) / "t2.tex"
        f.write_bytes(tex)
        kind, data = decode_texture(str(f))
        self.assertEqual(kind, "png")
        img = Image.open(io.BytesIO(data))
        self.assertEqual(img.size, (2, 2))

    def test_extract_inline_video(self):
        # 构造 MP4 片段: [size][ftyp....]
        ftyp = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"
        kind, blob = extract_inline_video(ftyp)
        self.assertEqual(kind, "mp4")
        self.assertTrue(blob.startswith(b"\x00\x00\x00\x18ftyp"))

    def test_decode_bc1_4color(self):
        """BC1 4 色模式块: 白/黑两色 + 2bit 索引"""
        c0 = struct.pack("<H", 0xFFFF)  # 白色 RGB565
        c1 = struct.pack("<H", 0x0000)  # 黑色
        indices = 0xE4  # 像素0=00 像素1=01 像素2=10 像素3=11 ...
        block = c0 + c1 + struct.pack("<I", indices)
        px = decode_bc1_block(block)
        self.assertEqual(len(px), 16)
        self.assertEqual(px[0], (255, 255, 255))
        self.assertEqual(px[1], (0, 0, 0))
        # 插值色: (170,170,170) 和 (85,85,85)
        self.assertEqual(px[2], (170, 170, 170))
        self.assertEqual(px[3], (85, 85, 85))

    def test_decode_bc1_3color(self):
        """BC1 3 色+透明模式: c0 < c1 时第 3 色为黑(透明)"""
        c0 = struct.pack("<H", 0x0000)  # 黑
        c1 = struct.pack("<H", 0xFFFF)  # 白, c0<c1 → 3色模式
        indices = 0x0  # 全 00 → 全用 c0
        block = c0 + c1 + struct.pack("<I", indices)
        px = decode_bc1_block(block)
        self.assertEqual(px[0], (0, 0, 0))
        self.assertEqual(px[8], (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
