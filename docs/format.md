# Wallpaper Engine 文件格式参考（实测逆向）

> 本文件为**格式知识库**，供开发/排错查阅。Agent 日常运行只需看 SKILL.md 的决策树。
> 所有结构均为实测验证（2026-08），与网络旧资料不同之处已标注。

---

## 1. pkg 文件

### 1.1 头部布局（**实测修正版，网上旧资料是错的**）

```
offset 0:  主版本   4B  小端（实测 = 8，pkg 格式版本）
offset 4:  magic    4B  "PKGV"
offset 8:  压缩标识 4B  ASCII 字符串 "0021"（21 = raw 数据段；旧格式 "0011" = gzip）
offset 12: fileCount 4B  ← 不是 headerSize！实测 26 条
offset 16: index: fileCount × [nameLen(4B) name offset(4B) size(4B)]
之后:      数据段，offset 为【相对数据段起点】的偏移
```

### 1.2 致命坑（实测踩过）

1. **`offset 12` 是 fileCount，不是 headerSize**——按旧资料读会把 26 当成 headerSize，解析全乱。
2. **数据段 offset 是相对 index 结束位置的**，不能当绝对偏移读。
   - 错误解析的症状：`scene.json` 解出来是 index 表内容（十六进制开头 `7e 0e 00 00 3a 00 00 00...`），
     `.tex` 带 JSON 前缀（好在前端 texlib 按 `TEXV0005` 定位仍能救回）。
3. **同名多版本条目**：`xxx` 与 `xxx_v1`/`xxx_v2`（不同分辨率/画质）。
   不要默认"无后缀 = 最好"——**按数据大小选最大**（`_select_best_versions` 已实现）。
4. 验证方法：末条目 `offset + size` 应等于 `数据段起点 + 文件大小`；`scene.json` 应为合法 JSON。

---

## 2. tex 文件（TEXV0005）

### 2.1 结构

```
TEXV0005\0   9B
TEXI0001\0   9B
Header      28B: format(4B) flags(4B) texW(4B) texH(4B) imgW(4B) imgH(4B) unk(4B)
TEXBxxxx 数据段:
  TEXB0001/0002:  BC1/BC2/BC3/BC7 压缩 mipmap 链（无内嵌图时用）
  TEXB0003:       4B FreeImage 格式 + 内嵌图片 (JPEG/PNG/GIF)
  TEXB0004:       4B 格式 + 4B isVideo + 内嵌图片或 MP4 视频
```

### 2.2 内嵌媒体提取

- 直接从 TEXB 段后字节里 `find` 签名提取：
  - JPEG `FF D8 FF`（EOI = `FF D9`，用 **rfind** 找最后一个——EXIF 缩略图也有 FFD8/FFD9）
  - PNG `\x89PNG`（截到 IEND 为止）
  - GIF `GIF8`
  - MP4 `ftyp`（**必须从 ftyp 前 4 字节 size 字段开始截取**，否则 moov atom 找不到）
- **JPEG 段可能混合多格式**（JPEG 尾部混 PNG）：提取后用 PIL `verify()` 验证，失败换下一格式。

### 2.3 BC1 软件解码（texlib.decode_bc1_block）

- 每块 16 字节 = 2×RGB565 颜色（c0, c1）+ 4 字节 2bit 索引（16 像素）。
- 颜色表：
  - `c0 > c1`：4 色模式 → c0, c1, (2c0+c1)/3, (c0+2c1)/3
  - `c0 <= c1`：3 色+透明 → c0, c1, (c0+c1)/2, 黑
- RGB565 解码：`r=(v>>11&31)*255//31, g=(v>>5&63)*255//63, b=(v&31)*255//31`
- 数据量：W×H 的 BC1 需要 `(W/4)*(H/4)*16` 字节。

### 2.4 BC7

- 8 种模式解码复杂，**Python 不内置**。统一入口 `decode_texture()` 对 BC7 返回
  `("needs_repkg", blob)`，调用方应转用 RePKG CLI（`scripts/repkg_helper.sh`）。

---

## 3. 壁纸类型（project.json `type` 字段）

| type（大小写不敏感） | 主视觉来源 |
|---|---|
| video | 目录/`files/` 下 `.mp4`（已转好的视频壁纸） |
| scene / 3d / application | `scene.pkg` → 解包 → 最大 `.tex` 提取内嵌媒体 |
| web | `preview.jpg` 兜底（canvas/JS 类壁纸无法离线复现） |
| 图片（无 type 或 unknown） | `files/` 下的 png/jpg，或 `preview.jpg` |

---

## 4. 转码参数（已验证）

- 目标分辨率：`2560x1664`（低）/ `2880x1864`（高），对应 MacBook Air 16:10.4 屏。
- **4K 源**（≥3000 宽）裁切：
  - `2560: crop=3324:2160:258:0,scale=2560:1664`
  - `2880: crop=3338:2160:251:0,scale=2880:1864`
- **1080p 源**裁切：
  - `2560: crop=1662:1080:129:0,scale=2560:1664`
  - `2880: crop=1668:1080:126:0,scale=2880:1864`
- 编码：`libx264 crf 18 preset medium yuv420p +faststart`，音频 `aac 192k`。
- **120fps 源强制 `-r 60`**（视觉无差别，体积减半）。
- 静态预览图：`ffmpeg -ss 3 -frames:v 1 -q:v 2`（3 秒帧）。
- 竖版/异形图转横屏：**模糊背景填充**（高斯模糊放大铺底 + 中央原图），见 `make_static`。

---

## 5. 其他踩坑

1. **RePKG 默认 target 是 net472（Windows）**，macOS 必须改成 `net10.0` 再 `dotnet publish`
   （`runtimeconfig.json` 只由 publish 生成）。
2. **scene.pkg 主图选择**：按文件大小降序取前 3 个 tex 依次尝试内嵌媒体提取，
   避免小图/alpha 通道图。
3. **视频纹理场景**：tex 提取出 mp4 后既能转动态壁纸也能 `-ss 3` 取帧做静态图。
4. **中文文件名**：macOS 下 zsh 通配符/`grep` 易乱码，脚本内用 Python `Path` 处理最稳。
5. **安全边界**：pkg 来自不可信来源时必须走安全解包（文件长度/fileCount/越界/路径穿越防护，
   已内置在 `unpack_pkg.py`，测试见 `tests/`）。
