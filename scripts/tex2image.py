#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tex → 可编辑媒体 CLI（自动挑最大、最优的媒体）

用法:
    python3 tex2image.py <xxx.tex> [输出前缀]
    # 输出: <前缀>.<jpg|png|gif|mp4> 或 <前缀>.raw_bc1.bin

示例:
    python3 tex2image.py "materials/ellen 1.tex"
    # 生成 ellen 1.png (内嵌图片) 或 ellen 1.mp4 (视频纹理)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from texlib import tex2image_fast, bc1_to_png, parse_tex


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    tex = sys.argv[1]
    prefix = sys.argv[2] if len(sys.argv) > 2 else Path(tex).with_suffix("")
    media = tex2image_fast(tex)

    if not media:
        print(f"[!] {tex}: 无可提取媒体")
        sys.exit(1)

    # 优先级: mp4 > jpg/png > gif > webp > raw_bc1
    order = {"mp4": 0, "jpg": 1, "png": 1, "gif": 2, "webp": 3, "raw_bc1": 4}
    best = sorted(media, key=lambda x: (order.get(x[0], 9), -len(x[1])))[0]
    kind, blob = best

    if kind == "raw_bc1":
        info = parse_tex(Path(tex).read_bytes())
        w, h = info["image_size"]
        print(f"  BC1 无内嵌图: 尝试解码 {w}x{h} (仅 BC1，BC7 请用 RePKG)")
        png = bc1_to_png(blob[: w * h * 16 // 16 * 16], w, h) if w and h else b""
        if png:
            out = f"{prefix}.png"
            Path(out).write_bytes(png)
            print(f"  -> {out}")
    else:
        ext = kind
        out = f"{prefix}.{ext}"
        Path(out).write_bytes(blob)
        print(f"  -> {out} ({len(blob)} bytes, {kind})")


if __name__ == "__main__":
    main()
