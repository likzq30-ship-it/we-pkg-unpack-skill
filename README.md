# we-pkg-unpack

Wallpaper Engine (壁纸引擎) pkg 壁纸包接包/解包与转码管线。

处理 Steam Workshop 下载的壁纸包（`*.pkg`）：解包 `scene.pkg`、解码 `TEXV0005` 纹理、提取主视觉、批量转码为 Mac 壁纸（视频 + 静态图，双分辨率）。

> ⚠️ **免责声明**：本工具为独立逆向格式转换器，与 Wallpaper Engine 无任何关联。处理素材版权归原作者，转换结果**仅限个人自用，禁止再分发**。详见 [DISCLAIMER.md](DISCLAIMER.md)。

## 功能

- **pkg 解包**：正确解析 Wallpaper Engine `.pkg` 二进制格式（实测修正网络旧资料的错误）
- **tex 纹理解码**：`TEXV0005` 格式，支持内嵌 JPEG/PNG/GIF/MP4 提取 + BC1 软件解码（BC7 走 RePKG）
- **全自动接包**：解包 → 识别壁纸类型（video/scene/web/图片）→ 提取主视觉 → 双分辨率成品
- **转码**：`2560x1664` / `2880x1864`，4K/1080p 源自适应裁切，120fps 自动降 60fps

## 快速开始

```bash
# 依赖
pip install pillow        # 图片处理
brew install ffmpeg       # 视频转码

# 批量处理（输入：含多个壁纸 ID 目录的根目录）
python3 scripts/make_wallpapers.py ~/Downloads/壁纸包 ~/Desktop/壁纸成品

# 单步
python3 scripts/unpack_pkg.py <id>/scene.pkg <id>/unpacked   # 解包
python3 scripts/tex2image.py "<id>/unpacked/materials/x.tex" # tex → 媒体
```

## 安装为 Cursor / Claude 技能

```bash
# Cursor 技能
git clone https://github.com/likzq30-ship-it/we-pkg-unpack.git \
    ~/.cursor/skills-cursor/we-pkg-unpack

# Claude Code 技能（二选一）
git clone https://github.com/likzq30-ship-it/we-pkg-unpack.git \
    ~/.claude/skills/we-pkg-unpack
```

之后在对话中提及「壁纸引擎 pkg 接包」「解包 scene.pkg」「tex 转图片」等即可自动触发。

## 目录结构

```
we-pkg-unpack/
├── SKILL.md              # 技能定义 + 完整格式参考 + 踩坑记录
├── DISCLAIMER.md         # 免责声明（中英双语）
├── LICENSE               # MIT
└── scripts/
    ├── unpack_pkg.py     # pkg 解包
    ├── texlib.py         # TEXV0005 纹理解码库
    ├── tex2image.py      # tex → 图片/视频 CLI
    ├── make_wallpapers.py# 一键接包管线
    └── repkg_helper.sh   # RePKG 编译兜底（BC7）
```

## 许可证

[MIT](LICENSE) — 代码本身开源；处理素材的版权归原作者，使用须遵守 [DISCLAIMER.md](DISCLAIMER.md)。
