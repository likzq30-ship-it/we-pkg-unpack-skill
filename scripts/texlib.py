#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wallpaper Engine .tex 纹理解码库（TEXV0005 格式）

结构:
    TEXV0005\\0         9B  magic1
    TEXI0001\\0         9B  magic2
    Header             28B  format(4) flags(4) texW(4) texH(4) imgW(4) imgH(4) unk(4)
    TEXBxxxx 数据段     按 magic 分类:
        TEXB0001/0002   BC1/BC2/BC3 压缩 mipmap 链（原始 block 数据）
        TEXB0003        FreeImage 内嵌图片 (JPEG/PNG/GIF), 4B format + 图片数据
        TEXB0004        内嵌图片或 MP4 视频, 4B format + 4B isVideo + 数据

解码架构（统一入口 decode_texture）:
    decode_texture(tex)
        ├─ 检测头部/格式
        ├─ 有内嵌媒体?  → 提取 (mp4/png/jpg/gif/webp)
        ├─ 无内嵌媒体?
        │    ├─ BC1    → 软件解码 (decode_bc1_block)
        │    └─ BC7    → 返回需要 RePKG 的信号（脚本不内置 BC7 解码）
        └─ 其他/未知   → None

TexFormat (FreeImage FIF):
    0=UNKNOWN 1=BMP 2=ICO 3=JPEG 4=JNG 5=KOALA 6=LBM 7=MNG 8=PBM 9=PBMRAW
    10=PCD 11=PCX 12=PGM 13=PGMRAW 14=PNG 15=PPM 16=PPMRAW 17=RAS 18=TARGA
    19=TIFF 20=WBMP 21=PSD 22=CUT 23=XBM 24=XPM 25=DDS 26=GIF 27=HDR 28=FAXG3
    29=SGI 30=EXR 31=J2K 32=JP2 33=PFM 34=PICT 35=RAW 36=WEBP 37=JXR 38=TGA
    39=JBIG 40=MP4 41=QOIF ...
"""
import re
import struct
from pathlib import Path

# FreeImage 常用格式常量（TEXB0003/0004 内嵌）
FIF_JPEG = 3
FIF_PNG = 14
FIF_TARGA = 18
FIF_DDS = 25
FIF_GIF = 26
FIF_WEBP = 36
FIF_MP4 = 40

MIN_TEX_SIZE = 16  # magic + magic + header 起码头
MAX_TEX_SIZE = 512 * 1024 * 1024  # 512MB 上限，防恶意超大文件


class TexError(Exception):
    """tex 解析错误（损坏/不支持）"""


def _ensure_valid(data: bytes):
    if len(data) < MIN_TEX_SIZE:
        raise TexError(f"tex 文件过小: {len(data)}B")
    if len(data) > MAX_TEX_SIZE:
        raise TexError(f"tex 文件过大: {len(data)}B > 512MB")
    if data[:8] != b"TEXV0005":
        raise TexError(f"不是 TEXV0005 纹理 (magic={data[:8]!r})")


def parse_tex(data: bytes) -> dict:
    """解析 tex 头部信息；损坏文件抛 TexError"""
    _ensure_valid(data)
    pos = 8
    if data[pos] == 0:
        pos += 1
    if data[pos:pos + 8] == b"TEXI0001":
        pos += 8
        if data[pos] == 0:
            pos += 1
    _check_bounds(data, pos, 28, "header")
    fmt, flags, tex_w, tex_h, img_w, img_h, unk = struct.unpack_from("<IIIIIII", data, pos)
    return {
        "format": fmt, "flags": flags,
        "texture_size": (tex_w, tex_h),
        "image_size": (img_w, img_h),
        "header_end": pos + 28,
    }


def _check_bounds(data: bytes, off: int, size: int, what: str):
    if off < 0 or size < 0 or off + size > len(data):
        raise TexError(f"越界: {what} @{off} size={size} (文件 {len(data)}B)")


def _split_texb(data: bytes) -> list:
    """把 TEXB 数据段切成 (magic, chunk) 列表（从第一个 TEXB 开始到文件尾）"""
    i = data.find(b"TEXB")
    if i < 0:
        return []
    seg = data[i:]
    results = []
    for m in re.finditer(b"TEXB", seg):
        start = m.start()
        magic = seg[start:start + 8]
        # 跳过非法 TEXB（magic 后跟随机数据也算）
        j = seg.find(b"TEXB", start + 8)
        end = j if j > 0 else len(seg)
        results.append((magic, seg[start + 8:end]))
        if j <= 0:
            break
    return results


def _cut_to_endmarker(data: bytes, marker: bytes, kind: str):
    """截取到结束标记（JPEG EOI / PNG IEND），避免混入后续数据"""
    end = data.rfind(marker)
    if end > 0:
        end += len(marker)
        # 检查结尾附近是否还有完整图像数据（防止截到错误位置）
        return data[:end]
    return data


def extract_inline_image(chunk: bytes):
    """从 TEXB0003/0004 chunk 中找内嵌图片 (kind, blob) 或 None
    注意: 一个 chunk 里可能 JPEG 后紧跟 PNG（多格式混合），需按结束标记精确截断"""
    # JPEG: 从 SOI 到最后一个 EOI（EXIF 内嵌缩略图也有 FFD8/FFD9，须取主图末尾）
    j = chunk.find(b"\xff\xd8\xff")
    if j >= 0:
        blob = chunk[j:]
        eoi = blob.rfind(b"\xff\xd9")
        if eoi > 0:
            blob = blob[: eoi + 2]
        # 仅当 PIL 能识别才返回，否则继续尝试 PNG
        if len(blob) > 1000:
            from PIL import Image
            import io
            try:
                Image.open(io.BytesIO(blob)).verify()
                return "jpg", blob
            except Exception:
                pass
    # PNG: 从签名到 IEND
    j = chunk.find(b"\x89PNG")
    if j >= 0:
        blob = chunk[j:]
        iend = blob.find(b"IEND")
        if iend > 0:
            blob = blob[: iend + 8]
        if len(blob) > 64:
            return "png", blob
    # GIF
    j = chunk.find(b"GIF8")
    if j >= 0:
        return "gif", chunk[j:]
    return None


def extract_inline_video(chunk: bytes):
    """从 TEXB0004 chunk 中提取 MP4（从 ftyp 的 size 字段开始）"""
    j = chunk.find(b"ftyp")
    if j >= 4:
        return "mp4", chunk[j - 4:]
    return None


def decode_bc1_block(block: bytes) -> list:
    """解码一个 BC1 16 字节块 → 16 个 (r,g,b)"""
    c0 = struct.unpack_from("<H", block, 0)[0]
    c1 = struct.unpack_from("<H", block, 2)[0]

    def rgb565(v):
        return ((v >> 11) & 0x1F) * 255 // 31, ((v >> 5) & 0x3F) * 255 // 63, (v & 0x1F) * 255 // 31

    col = [rgb565(c0), rgb565(c1)]
    if c0 > c1:  # 4 色模式
        col += [((2 * col[0][0] + col[1][0]) // 3, (2 * col[0][1] + col[1][1]) // 3, (2 * col[0][2] + col[1][2]) // 3),
                ((col[0][0] + 2 * col[1][0]) // 3, (col[0][1] + 2 * col[1][1]) // 3, (col[0][2] + 2 * col[1][2]) // 3)]
    else:  # 3 色 + 透明
        col += [((col[0][0] + col[1][0]) // 2, (col[0][1] + col[1][1]) // 2, (col[0][2] + col[1][2]) // 2), (0, 0, 0)]
    idx = struct.unpack_from("<I", block, 4)[0]
    pixels = []
    for p in range(16):
        code = (idx >> (p * 2)) & 3
        pixels.append(col[code])
    return pixels


def bc1_to_png(bc1_data: bytes, width: int, height: int) -> bytes:
    """BC1 mipmap 数据 → PNG 字节（用于 TEXB0001 无内嵌图时的兜底）"""
    from PIL import Image
    img = Image.new("RGB", (width, height))
    px = img.load()
    bw, bh = (width + 3) // 4, (height + 3) // 4
    for by in range(bh):
        for bx in range(bw):
            off = (by * bw + bx) * 16
            if off + 16 > len(bc1_data):
                break
            block = bc1_data[off:off + 16]
            pixels = decode_bc1_block(block)
            for py in range(4):
                for px_ in range(4):
                    x, y = bx * 4 + px_, by * 4 + py
                    if x < width and y < height:
                        px[x, y] = pixels[py * 4 + px_]
    buf = Path("/tmp/_bc1_tmp.png")
    img.save(buf)
    return buf.read_bytes()


def tex2image_fast(tex_path: str) -> list:
    """
    提取 tex 里的所有可用媒体，返回 [(kind, data)]:
      kind: raw_bc1 / jpg / png / gif / webp / mp4
    注意: TEXB0001(BC1) 的 chunk 是整个 mipmap 链，若 tex 无内嵌图片，取最大 mipmap
          用 decode_bc1_block 兜底；BC7(TEXB0001 高阶格式) 建议用 RePKG（见 SKILL.md）
    """
    data = Path(tex_path).read_bytes()
    _ensure_valid(data)
    info = parse_tex(data)
    results = []
    for magic, chunk in _split_texb(data):
        if magic == b"TEXB0001":
            # BC1/BC2/BC3 原始 mipmap 链（也可能含 BC7）
            results.append(("raw_bc1", chunk))
        elif magic in (b"TEXB0002",):
            results.append(("raw_texb2", chunk))
        elif magic == b"TEXB0003":
            found = extract_inline_image(chunk)
            if found:
                results.append(found)
        elif magic == b"TEXB0004":
            v = extract_inline_video(chunk)
            if v:
                results.append(v)
            found = extract_inline_image(chunk)
            if found:
                results.append(found)
    return results


MEDIA_PRIORITY = {"mp4": 0, "jpg": 1, "png": 1, "gif": 2, "webp": 3, "raw_bc1": 4}


def decode_texture(tex_path: str):
    """
    统一解码入口（Agent 主用 API）:
      返回 (kind, data) 最佳媒体；无可用媒体返回 None。
      选择优先级: mp4 > png/jpg > gif > webp > raw_bc1（按字节数取最大）。
      失败/损坏抛 TexError。
    """
    data = Path(tex_path).read_bytes()
    _ensure_valid(data)
    media = tex2image_fast(tex_path)
    if not media:
        return None
    best = sorted(media, key=lambda x: (MEDIA_PRIORITY.get(x[0], 9), -len(x[1])))[0]
    kind, blob = best

    # raw BC1: 尝试软件解码（BC7 无法解码时返回原样，由调用方决定走 RePKG）
    if kind == "raw_bc1":
        info = parse_tex(data)
        w, h = info["image_size"]
        if w and h:
            try:
                png = bc1_to_png(blob[: (w * h) // 4 * 16], w, h)
                if png:
                    return "png", png
            except Exception:
                pass
        # 解码失败或 BC7: 标记需要 RePKG
        return "needs_repkg", blob
    return kind, blob


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        print(f"=== {p} ===")
        try:
            for kind, blob in tex2image_fast(p):
                print(f"  {kind}: {len(blob)} bytes")
        except TexError as e:
            print(f"  [!] {e}")
