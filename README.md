# we-pkg-unpack-skill

Wallpaper Engine (壁纸引擎) pkg 壁纸包接包/解包与转码管线，作为 **Cursor / Claude Agent Skill** 使用。

处理 Steam Workshop 下载的壁纸包（`*.pkg`）：解包 `scene.pkg`、解码 `TEXV0005` 纹理、提取主视觉、批量转码为 Mac 壁纸（视频 + 静态图，双分辨率）。

> ⚠️ **免责声明**：本工具为独立逆向格式转换器，与 Wallpaper Engine 无任何关联。处理素材版权归原作者，转换结果**仅限个人自用，禁止再分发**。详见 [DISCLAIMER.md](DISCLAIMER.md)。

## 亮点

- **实测逆向格式**：`PKGV` / TEXV0005 结构为实测修正（网络旧资料有误，详见 [docs/format.md](docs/format.md)）
- **安全加固**：pkg 解包内置路径穿越防护 / fileCount 上限 / 越界检查，可安全处理不可信来源
- **优雅降级**：video / scene / web / 图片 四类全支持，web 类自动 `preview.jpg` 兜底
- **双引擎纹理解码**：统一入口 `decode_texture()`，内嵌媒体提取 / BC1 软件解码 / BC7 走 RePKG

## Agent 决策树

```
输入壁纸包目录 → 识别 type (video/scene/web) → scene 则解包 pkg
→ 找最大 .tex → decode_texture → mp4/png/jpg 或 RePKG(BC7)
→ 转码 2560x1664 / 2880x1864 → ffprobe 验证
```

完整决策树与失败恢复见 [SKILL.md](SKILL.md)。

## 快速开始

```bash
# 依赖
pip install pillow        # 图片处理
brew install ffmpeg       # 视频转码

# 批量处理（输入：含多个壁纸 ID 目录的根目录）
python3 scripts/make_wallpapers.py ~/Downloads/壁纸包 ~/Desktop/壁纸成品

# 单步
python3 scripts/unpack_pkg.py <id>/scene.pkg <id>/unpacked   # 解包（安全加固）
python3 scripts/tex2image.py "<id>/unpacked/materials/x.tex" # tex → 媒体
```

## 安装为 Cursor / Claude 技能

```bash
# Cursor 技能
git clone https://github.com/likzq30-ship-it/we-pkg-unpack-skill.git \
    ~/.cursor/skills-cursor/we-pkg-unpack

# Claude Code 技能（二选一）
git clone https://github.com/likzq30-ship-it/we-pkg-unpack-skill.git \
    ~/.claude/skills/we-pkg-unpack
```

之后在对话中提及「壁纸引擎 pkg 接包」「解包 scene.pkg」「tex 转图片」等即可自动触发。

## 目录结构

```
we-pkg-unpack/
├── SKILL.md              # Agent 决策树 + 命令 + 验证 + 失败恢复
├── docs/format.md        # pkg/TEXV0005 格式知识库 + 踩坑记录
├── README.md / DISCLAIMER.md / LICENSE
├── scripts/
│   ├── make_wallpapers.py# 一键接包管线（核心）
│   ├── unpack_pkg.py     # pkg 解包（安全加固版）
│   ├── texlib.py         # TEXV0005 解码库（统一入口 decode_texture）
│   ├── tex2image.py      # tex → 图片/视频 CLI
│   └── repkg_helper.sh   # RePKG 编译兜底（BC7）
├── tests/                # unittest：pkg/tex/安全 19 例
└── .github/workflows/ci.yml
```

## 测试

```bash
python3 -m unittest discover -s tests -v
```

覆盖：pkg 正常解包 / gzip 段 / 多版本按大小选优 / 恶意 fileCount / **路径穿越拒绝** / 数据越界 / index 截断 + tex 头部解析 / 内嵌 PNG 提取 / MP4 提取 / BC1 4色与3色解码。

CI：GitHub Actions（ubuntu + macos × Python 3.9/3.11，Pillow 依赖 + 语法检查 + 全量测试）。

## 许可证

[MIT](LICENSE) — 代码本身开源；处理素材的版权归原作者，使用须遵守 [DISCLAIMER.md](DISCLAIMER.md)。
