---
name: we-pkg-unpack
description: >
  Wallpaper Engine (壁纸引擎) pkg 壁纸包接包/解包与转码管线。
  处理 Steam Workshop 下载的壁纸包：解包 scene.pkg、解码 TEXV0005 纹理、
  提取主视觉、批量转码为 Mac 壁纸（视频+静态图双分辨率）。
  触发词: Wallpaper Engine, 壁纸引擎, pkg 解包, 接包, scene.pkg, tex 转图片,
  TEXV0005, TEXB0001, 壁纸包, workshop 壁纸, repkg, wallpaper pkg。
---

# WE pkg 接包（Wallpaper Engine → Mac 壁纸）

> ⚠️ 使用前先读 [DISCLAIMER.md](DISCLAIMER.md)：独立逆向格式转换器，与 Wallpaper Engine
> 无关联；素材版权归原作者，转换结果**仅限个人自用，禁止再分发**。
> 格式细节见 [docs/format.md](docs/format.md)，本文件只保留 Agent 决策规则。

## What this skill does

输入「壁纸包根目录」（含多个壁纸 ID 子目录，每个目录有 `project.json` + `scene.pkg` 或视频），
输出「成品根目录」：

```
<成品根>/
├── 2560x1664/视频/<名>_2560x1664.mp4    2880x1864/视频/<名>_2880x1864.mp4
└── 2560x1664/图片/<名>_2560x1664.jpg    2880x1864/图片/<名>_2880x1864.jpg
```

## When to trigger

- 用户有 Wallpaper Engine / Steam Workshop 壁纸文件（`.pkg` / 壁纸 ID 目录）要转成可用壁纸
- 用户说「接包」「解包壁纸」「tex 转图片」「壁纸引擎的包」

## Input detection（先识别，再动手）

1. 检查输入目录结构：`project.json` 存在？`scene.pkg` 还是 `.mp4`？
2. 读 `project.json` → `type` 字段（大小写不敏感）：
   - `video` → 直接找 `.mp4`（根目录或 `files/`）
   - `scene` / `3d` / `application` → 需要解包 `scene.pkg`
   - `web` → 无法离线复现 JS，用 `preview.jpg` 兜底出静态图
   - 无 type / unknown → 搜 `files/` 图片，再兜底 `preview.jpg`

## Decision tree

```
                 输入壁纸包目录
                        │
                        ▼
               project.json type?
        ┌───────────────┼────────────────┐
        ▼               ▼                ▼
      video          scene/3d           web/unknown
        │               │                │
        │          unpack_pkg.py    preview.jpg
        │               │                │
        │         找最大 .tex            │
        │               │                │
        │        decode_texture()        │
        │        ┌───────┼────────┐      │
        │        ▼       ▼        ▼      │
        │      mp4     png/jpg  needs_repkg
        │        │       │        │      │
        │        │       │    RePKG CLI  │
        │        └───────┼────────┘      │
        │                ▼               │
        └──────────► 媒体 (mp4/图) ◄──────┘
                        │
                        ▼
              make_wallpapers 转码
        （裁切 → 2560x1664 / 2880x1864）
                        │
                        ▼
              ffprobe 验证输出
```

## Commands（按需调用，不全部跑）

```bash
SCRIPTS=~/.cursor/skills-cursor/we-pkg-unpack/scripts

# 一键全自动（推荐：识别类型→解包→提取→转码→双分辨率）
python3 $SCRIPTS/make_wallpapers.py <壁纸包根目录> <成品根目录>
python3 $SCRIPTS/make_wallpapers.py <输入> <输出> --video-only   # 只转视频类
python3 $SCRIPTS/make_wallpapers.py <输入> <输出> --image-only   # 只出静态图

# 单步调试（失败时逐层排查）
python3 $SCRIPTS/unpack_pkg.py <id>/scene.pkg <id>/unpacked      # 解包（安全加固版）
python3 $SCRIPTS/tex2image.py "<id>/unpacked/materials/xxx.tex"  # tex → 媒体
bash $SCRIPTS/repkg_helper.sh /tmp/repkg-build build              # 编译 RePKG（BC7 用）
bash $SCRIPTS/repkg_helper.sh /tmp/repkg-build convert <tex目录> <输出>
```

## Validation（转码后必须验证）

```bash
# 视频分辨率
ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 <mp4>
# 应为 2560,1664 或 2880,1864
# 静态图分辨率
sips -g pixelWidth -g pixelHeight <jpg>
```

## Failure recovery（按顺序排查）

| 症状 | 处理 |
|---|---|
| `unpack_pkg` 报「不是 PKG / fileCount 异常 / 越界」 | 文件损坏或非 WE 包；换其他 ID 目录 |
| 解包成功但 `scene.json` 是乱码/index 内容 | pkg 解析偏移错（少见，已加固）；对照 docs/format.md |
| tex 提取为空 | 试前 3 大 tex；`decode_texture` 返回 `needs_repkg` → 走 RePKG |
| MP4 报 moov atom not found | 提取起点少了 4 字节，用 `texlib.extract_inline_video` 自动处理 |
| 单 ID 失败 | 记录 `[FAIL]` 继续处理其余，最后汇总 |
| 全部失败 | 检查依赖：`pip install pillow`、`brew install ffmpeg` |

## Tests

```bash
cd ~/.cursor/skills-cursor/we-pkg-unpack && python3 -m unittest discover -s tests
```
覆盖：pkg 正常/gzip/多版本/恶意 fileCount/路径穿越/越界/截断 + tex 头部/内嵌提取/BC1 解码。

## 依赖

Python 3.9+ / Pillow / ffmpeg / ffprobe；dotnet SDK（仅 RePKG 兜底路径）。
