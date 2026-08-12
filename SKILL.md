---
name: we-pkg-unpack
description: >
  Wallpaper Engine (壁纸引擎) pkg 壁纸包接包/解包与转码管线。
  用于处理 Steam Workshop 下载的壁纸包（*.pkg）：解包 scene.pkg、
  解码 TEXV0005 纹理（TEXB0001 BC1/BC7 压缩、TEXB0003 内嵌 JPEG/PNG/GIF、
  TEXB0004 内嵌 MP4 视频）、提取主视觉、转码为 Mac 壁纸（视频+静态图双分辨率）。
  触发词: Wallpaper Engine, 壁纸引擎, pkg 解包, 接包, scene.pkg, tex 转图片,
  TEXV0005, TEXB0001, 壁纸包, workshop 壁纸, repkg。
---

# Wallpaper Engine pkg 接包

把 Steam Workshop 的壁纸引擎壁纸包（一个目录 = 一个壁纸：`project.json` + `scene.pkg` 或视频文件）批量转成可直接用的壁纸成品。

## 成品组织

```
<成品根>/
├── 2560x1664/            # 低分辨率（Air 屏）
│   ├── 视频/<名字>_2560x1664.mp4
│   └── 图片/<名字>_2560x1664.jpg
└── 2880x1864/            # 高分辨率
    ├── 视频/<名字>_2880x1864.mp4
    └── 图片/<名字>_2880x1864.jpg
```

## 工作流（一条命令跑完）

```bash
# 1) 批量处理一个包含多个壁纸 ID 目录的根目录
python3 ~/.cursor/skills-cursor/we-pkg-unpack/scripts/make_wallpapers.py \
    ~/Downloads/壁纸包 ~/Desktop/壁纸成品

# 2) 只转视频类 / 只出静态图
python3 make_wallpapers.py <输入> <输出> --video-only
python3 make_wallpapers.py <输入> <输出> --image-only

# 3) 单步操作
python3 scripts/unpack_pkg.py <id>/scene.pkg <id>/unpacked      # 解包
python3 scripts/tex2image.py "<id>/unpacked/materials/xxx.tex"  # tex → 媒体
bash scripts/repkg_helper.sh /tmp/repkg-build build              # 编译 RePKG
bash scripts/repkg_helper.sh /tmp/repkg-build convert <tex目录> <输出>  # RePKG 批量转
```

## 格式参考（核心知识）

### pkg 文件（**实测格式，网上旧资料是错的**）

```
offset 0:  主版本  4B  小端（实测 = 8）
offset 4:  magic   4B  "PKGV"
offset 8:  压缩标识 4B  ASCII "0021"（21 = raw；旧格式 "0011" = gzip）
offset 12: fileCount 4B  ← 不是 headerSize！实测 26
offset 16: index: fileCount × [nameLen(4B) name offset(4B) size(4B)]
之后:      数据段，offset 为【相对数据段起点】的偏移
```

- `scene.pkg` 内含 `scene.json` + `materials/*.tex` + 音频/着色器等。
- 同名多版本条目：`xxx` 和 `xxx_v1`、`xxx_v2`（不同分辨率/画质），**取无后缀版本**（通常最大）。
- 场景主图一般在 `materials/` 下**最大的 tex**。
- **两个致命坑**（实测踩过）：① `offset 12` 是 fileCount 不是 headerSize；② 数据段 offset 是相对值，不能当绝对偏移读——按错误方式解出来的 scene.json 会变成 index 表内容、tex 会带 JSON 前缀（好在 texlib 按 TEXV0005 定位仍能救回）。

### tex 文件（TEXV0005）

```
TEXV0005\0   9B
TEXI0001\0   9B
Header      28B: format(4B) flags(4B) texW(4B) texH(4B) imgW(4B) imgH(4B) unk(4B)
TEXBxxxx 数据段:
  TEXB0001/0002:  BC1/BC2/BC3/BC7 压缩 mipmap 链（无内嵌图时用）
  TEXB0003:       4B FreeImage 格式 + 内嵌图片 (JPEG/PNG/GIF)
  TEXB0004:       4B 格式 + 4B isVideo + 内嵌图片或 MP4 视频
```

- **内嵌媒体**直接从 TEXB 段后字节里 `find` 签名提取（JPEG `FFD8FF`、PNG `\x89PNG`、GIF、MP4 `ftyp`）。
- **MP4 提取注意**：必须从 `ftyp` **前 4 字节（size 字段）** 开始截取，否则 moov atom 找不到。
- **BC1 解码**：16 字节块 = 2×RGB565 颜色 + 4 字节 2bit 索引，4 色/3 色+透明两种模式（见 `texlib.py:decode_bc1_block`）。
- **BC7 解码**复杂（8 种模式），Python 兜底不支持 → **用 RePKG CLI**（`repkg_helper.sh`），它会正确处理 BC7 和所有 mipmap。
- 竖版/异形图（如 2160x3840 手机壁纸）转横屏时用**模糊背景填充**（高斯模糊放大铺底 + 中央原图），见 `make_static`。

### 壁纸类型（project.json `type` 字段）

| type | 主视觉来源 |
|---|---|
| video | 目录/`files/` 下 `.mp4`（已转好的视频壁纸） |
| scene | `scene.pkg` → 解包 → 最大 `.tex` 提取内嵌媒体 |
| web | `preview.jpg` 兜底（canvas/JS 类壁纸无法离线复现） |
| 图片 | `files/` 下的 png/jpg |

## 转码参数（已验证）

- 目标分辨率：`2560x1664`（低） / `2880x1864`（高），对应 MacBook Air 16:10.4 屏。
- **4K 源**（≥3000 宽）裁切：
  - `2560: crop=3324:2160:258:0,scale=2560:1664`
  - `2880: crop=3338:2160:251:0,scale=2880:1864`
- **1080p 源**裁切：
  - `2560: crop=1662:1080:129:0,scale=2560:1664`
  - `2880: crop=1668:1080:126:0,scale=2880:1864`
- 编码：`libx264 crf 18 preset medium yuv420p +faststart`，音频 `aac 192k`。
- **120fps 源强制 `-r 60`**（视觉无差别，体积减半）。
- 静态预览图：`ffmpeg -ss 3 -frames:v 1 -q:v 2`（3 秒帧）。

## 踩坑记录

0. **pkg index 偏移**：数据段 offset 是相对 index 结束位置的，且 `offset 12` 是 fileCount——解包前先看 pkg 实测头（见上）。
1. **RePKG 默认 target 是 net472（Windows）**，macOS 上必须改成 `net10.0` 再 `dotnet publish`（`runtimeconfig.json` 只由 publish 生成）。
2. **MP4 内嵌在 tex 里常被截断显示为不完整**：提取后 `ffprobe` 报 "moov atom not found" 多半是截取起点少了 4 字节（从 `ftyp` 而不是 size 字段开始）。
3. **tex 无内嵌媒体时**（纯 TEXB0001）：BC1 用内置解码可救，BC7 用 RePKG。
4. **scene.pkg 主图选择**：按文件大小降序取前 3 个 tex 依次尝试内嵌媒体提取，避免小图/alpha 通道图。
5. **视频纹理场景**：tex 提取出 mp4 后既能转动态壁纸也能 `-ss 3` 取帧做静态图。
6. **中文文件名**：macOS 下 zsh 通配符/`grep` 易乱码，脚本内用 Python `Path` 处理最稳。
7. **同名 `_v1/_v2` 版本条目**：必须跳过，否则会提取出低画质图。
8. **JPEG 内嵌段可能含 EXIF 缩略图或多格式混合**（JPEG 尾部混 PNG）：EOI 用 `rfind`（最后一个 FFD9），并用 PIL `verify()` 验证后才采用；PNG 截到 IEND 为止。

## 依赖

- Python 3 + Pillow（`pip install pillow`）
- ffmpeg / ffprobe
- dotnet SDK（仅 RePKG 兜底路径需要）
