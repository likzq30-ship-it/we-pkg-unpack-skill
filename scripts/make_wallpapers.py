#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wallpaper Engine pkg 接包 → MacBook Air 壁纸 全自动管线

输入: 包含多个壁纸 ID 目录的根目录（每个目录含 project.json + scene.pkg / 视频 / files 图片）
输出: <成品根目录>/<2560x1664|2880x1864>/<视频|图片>/<名字>_<分辨率>.mp4|jpg

流程:
  1. 解包 scene.pkg（若存在）到 <id>/unpacked/
  2. 识别壁纸类型 (video / scene / web / 图片)
  3. 提取主视觉:
     - scene: 最大 tex → 内嵌图片 / 内嵌视频 / BC1 解码
     - video: 直接取 mp4
     - 图片: files/ 内图片
     - web: preview.jpg
  4. 生成 2 分辨率静态图（横版中心裁切 / 竖版模糊填充）

用法:
    python3 make_wallpapers.py <壁纸包根目录> <成品根目录> [--video-only] [--image-only]
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from texlib import tex2image_fast, parse_tex
from unpack_pkg import unpack_pkg

RESOLUTIONS = {
    "2560x1664": (2560, 1664),
    "2880x1864": (2880, 1864),
}


def get_project_name(proj: dict) -> str:
    """从 project.json 取中文名（title 或 目录名清理）"""
    for k in ("title", "name"):
        if proj.get(k):
            return str(proj[k])
    return ""


def detect_type(proj: dict) -> str:
    t = str(proj.get("type", "")).lower()
    if "video" in t:
        return "video"
    if "scene" in t or t == "application" or "3d" in t:
        return "scene"
    if "web" in t:
        return "web"
    return "unknown"


def sanitize(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "", name).strip() or "unnamed"


def main_image_sources(id_dir: Path, wtype: str) -> list:
    """返回 [(kind, path)] 候选主视觉，已按优先级排序"""
    candidates = []
    if wtype == "scene":
        unpacked = id_dir / "unpacked"
        texs = sorted(unpacked.rglob("*.tex"), key=lambda p: p.stat().st_size, reverse=True)
        if texs:
            # 取最大 tex（一般为主图），提取内嵌媒体
            for t in texs[:3]:
                for kind, blob in tex2image_fast(str(t)):
                    # 跳过原始 BC 压缩块（无法直接当图片用；BC1 可用 RePKG 兜底）
                    if kind in ("raw_bc1", "raw_texb2"):
                        continue
                    p = id_dir / f"_extracted_{sanitize(t.stem)}.{kind}"
                    p.write_bytes(blob)
                    candidates.append((kind, p))
            # BC1 兜底: 无内嵌媒体的 tex
            if not candidates and texs:
                t = texs[0]
                try:
                    info = parse_tex(t.read_bytes())
                    w, h = info["image_size"]
                    if w and h:
                        print(f"  [i] BC1 兜底 {t.name} {w}x{h}（BC7 用 RePKG）")
                except Exception as e:
                    print(f"  [!] parse {t.name}: {e}")
    # 图片壁纸
    files_dir = id_dir / "files"
    if files_dir.exists():
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
            for f in sorted(files_dir.glob(ext), key=lambda p: p.stat().st_size, reverse=True):
                if not f.name.startswith("."):
                    candidates.append(("image", f))
    # web / 兜底: preview.jpg
    preview = id_dir / "preview.jpg"
    if preview.exists():
        candidates.append(("image", preview))
    return candidates


def make_static(src: str, out_w: int, out_h: int, out_path: str):
    """生成静态壁纸: 横版中心裁切 / 竖版模糊填充"""
    from PIL import Image, ImageFilter
    img = Image.open(src).convert("RGB")
    w, h = img.size
    ratio = w / h
    target = out_w / out_h
    if ratio > target * 1.05:
        new_w = int(h * target)
        x = (w - new_w) // 2
        img = img.crop((x, 0, x + new_w, h))
    elif ratio < target * 0.95:
        bg = img.resize((out_w, out_h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(30))
        scale = min(out_w / w, out_h / h)
        fw, fh = int(w * scale), int(h * scale)
        fg = img.resize((fw, fh), Image.LANCZOS)
        bg.paste(fg, ((out_w - fw) // 2, (out_h - fh) // 2))
        img = bg
    img = img.resize((out_w, out_h), Image.LANCZOS)
    img.save(out_path, "JPEG", quality=92)


def first_video_frame(src: str, vf: str, out_path: str, t: float = 3.0):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", src,
                    "-frames:v", "1", "-vf", vf, "-q:v", "2", out_path], check=True)
    print(f"  [OK] 帧图 {Path(out_path).name}")


def process_wallpaper(id_dir: Path, out_root: Path, only_video: bool, only_image: bool):
    proj_path = id_dir / "project.json"
    if not proj_path.exists():
        print(f"  [skip] 无 project.json: {id_dir.name}")
        return
    proj = json.loads(proj_path.read_text(encoding="utf-8"))
    name = sanitize(get_project_name(proj) or id_dir.name)
    wtype = detect_type(proj)
    print(f"=== {id_dir.name} [{wtype}] {name} ===")

    # 1. 解包 scene.pkg
    pkg = id_dir / "scene.pkg"
    if pkg.exists() and not (id_dir / "unpacked").exists():
        unpack_pkg(str(pkg), str(id_dir / "unpacked"))

    # 2. 找主视觉
    if wtype == "video":
        vids = list(id_dir.glob("*.mp4")) + list((id_dir / "files").glob("*.mp4"))
        if not vids:
            print("  [!] video 类型但无 mp4")
            return
        src = str(vids[0])
        if only_image:
            for res, (w, h) in RESOLUTIONS.items():
                vf = get_crop_vf(w, src)
                first_video_frame(src, vf, str(out_root / res / "图片" / f"{name}_{res}.jpg"))
            return
        make_video(src, name, out_root)
        return

    if only_video:
        return
    candidates = main_image_sources(id_dir, wtype)
    if not candidates:
        print("  [!] 未找到主视觉")
        return
    kind, src = candidates[0]
    print(f"  [主视觉] {kind}: {src.name}")
    if kind == "mp4":
        # 视频纹理场景 → 取帧 + 可选转视频
        if not only_image:
            make_video(str(src), name, out_root)
        for res, (w, h) in RESOLUTIONS.items():
            vf = get_crop_vf(w, str(src))
            first_video_frame(str(src), vf, str(out_root / res / "图片" / f"{name}_{res}.jpg"))
        return
    # 静态图
    for res, (w, h) in RESOLUTIONS.items():
        out = out_root / res / "图片" / f"{name}_{res}.jpg"
        make_static(str(src), w, h, str(out))
    print(f"  [OK] 静态图 2 分辨率")


def get_crop_vf(out_w: int, src: str) -> str:
    """自适应中心裁切: 按源实际分辨率取目标比例内最大区域，再缩放（兼容任意分辨率源）"""
    out_h = {2560: 1664, 2880: 1864}.get(out_w, out_w * 1664 // 2560)
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height", "-of", "csv=p=0", src],
                       capture_output=True, text=True)
    try:
        sw, sh = [int(x) for x in r.stdout.strip().split(",")]
    except (ValueError, IndexError):
        sw = sh = 0
    if sw <= 0 or sh <= 0:
        return f"scale={out_w}:{out_h}:flags=lanczos"
    target = out_w / out_h
    if sw / sh > target:  # 源更宽 → 裁宽
        cw = int(sh * target)
        cx = (sw - cw) // 2
        return f"crop={cw}:{sh}:{cx}:0,scale={out_w}:{out_h}:flags=lanczos"
    else:  # 源更高 → 裁高
        ch = int(sw / target)
        cy = (sh - ch) // 2
        return f"crop={sw}:{ch}:0:{cy},scale={out_w}:{out_h}:flags=lanczos"


def make_video(src: str, name: str, out_root: Path):
    for res, (w, h) in RESOLUTIONS.items():
        vf = get_crop_vf(w, src)
        fps = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                              "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", src],
                             capture_output=True, text=True).stdout.strip()
        fr = ["-r", "60"] if fps == "120/1" else []
        out = out_root / res / "视频" / f"{name}_{res}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", *fr, "-i", src, "-vf", vf,
                        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                        "-c:a", "aac", "-b:a", "192k", str(out)], check=True)
        # 静态预览图
        first_video_frame(src, vf, str(out_root / res / "图片" / f"{name}_{res}.jpg"))
        print(f"  [OK] {res} 视频+图")


def main():
    ap = argparse.ArgumentParser(description="WE pkg 接包 → 壁纸")
    ap.add_argument("input", help="壁纸包根目录（含多个 ID 子目录）")
    ap.add_argument("output", help="成品根目录")
    ap.add_argument("--video-only", action="store_true", help="只处理视频类型")
    ap.add_argument("--image-only", action="store_true", help="只生成静态图")
    args = ap.parse_args()

    root = Path(args.input)
    out_root = Path(args.output)
    for res in RESOLUTIONS:
        (out_root / res / "视频").mkdir(parents=True, exist_ok=True)
        (out_root / res / "图片").mkdir(parents=True, exist_ok=True)

    for d in sorted(root.iterdir()):
        if d.is_dir():
            try:
                process_wallpaper(d, out_root, args.video_only, args.image_only)
            except Exception as e:
                print(f"  [FAIL] {d.name}: {e}")
    print("=== 全部处理完成 ===")


if __name__ == "__main__":
    main()
