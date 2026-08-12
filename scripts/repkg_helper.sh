#!/bin/bash
# RePKG CLI（官方 tex/png 转换器）编译与使用
# 用途: BC7 / 复杂 BC1 tex 解码的兜底方案（python 内置解码只支持简单 BC1）
set -e

REPKG_REPO="https://github.com/notscuffed/repkg.git"
WORK_DIR="${1:-/tmp/repkg-build}"

build() {
    echo "[1/3] 克隆 RePKG..."
    if [ ! -d "$WORK_DIR/repkg-src" ]; then
        git clone --depth 1 "$REPKG_REPO" "$WORK_DIR/repkg-src"
    fi
    echo "[2/3] 改目标框架为 net10.0（macOS 可运行）..."
    sed -i '' 's|<TargetFramework>net472</TargetFramework>|<TargetFramework>net10.0</TargetFramework>|' \
        "$WORK_DIR/repkg-src/RePKG/RePKG.csproj" 2>/dev/null || true
    echo "[3/3] publish..."
    dotnet publish "$WORK_DIR/repkg-src/RePKG/RePKG.csproj" -c Release -o "$WORK_DIR/repkg-pub" \
        >/dev/null 2>&1
    echo "DLL: $WORK_DIR/repkg-pub/RePKG.dll"
}

convert_dir() {
    local dll="$WORK_DIR/repkg-pub/RePKG.dll"
    [ -f "$dll" ] || { echo "先 build"; exit 1; }
    local input="$1"; shift
    dotnet "$dll" extract -t -o "${2:-./repkg_out}" "$input"
}

case "${2:-build}" in
    build) build ;;
    convert) convert_dir "$3" "$4" ;;
    *) echo "用法: $0 [工作目录] build|convert <tex目录> [输出目录]" ;;
esac
