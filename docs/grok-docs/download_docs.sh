#!/bin/bash
# 下載 Grok API 文件到當前目錄
# 用法: cd docs/grok-docs && bash download_docs.sh

set -euo pipefail

BASE_URL="https://docs.x.ai/developers"
OUTPUT_DIR="$(cd "$(dirname "$0")" && pwd)"

# URL 路徑 → 本地檔名（用平行陣列相容 bash 3.x）
PATHS=(
  "models.md"
  "model-capabilities/images/generation.md"
  "model-capabilities/video/generation.md"
)
FILENAMES=(
  "models.md"
  "images-generation.md"
  "video-generation.md"
)

echo "下載目錄: $OUTPUT_DIR"
echo "共 ${#PATHS[@]} 個文件待下載"
echo "---"

success=0
fail=0

# 防止 ((x++)) 在 x=0 時因返回值 1 觸發 set -e
incr_success() { success=$((success + 1)); }
incr_fail() { fail=$((fail + 1)); }

for i in "${!PATHS[@]}"; do
  path="${PATHS[$i]}"
  filename="${FILENAMES[$i]}"
  url="${BASE_URL}/${path}"
  output="${OUTPUT_DIR}/${filename}"

  echo -n "下載 ${filename} ... "

  if curl -fsSL "$url" -o "$output" 2>/dev/null; then
    size=$(wc -c < "$output" | tr -d ' ')
    if [ "$size" -gt 0 ]; then
      echo "成功 (${size} bytes)"
      incr_success
    else
      echo "失敗 (空檔案)"
      rm -f "$output"
      incr_fail
    fi
  else
    echo "失敗，嘗試不帶 .md 字尾..."
    # 嘗試不帶 .md 的 URL
    alt_url="${BASE_URL}/${path%.md}"
    if curl -fsSL "$alt_url" -o "$output" 2>/dev/null; then
      size=$(wc -c < "$output" | tr -d ' ')
      if [ "$size" -gt 0 ]; then
        echo "已儲存 (${size} bytes)"
        incr_success
      else
        echo "失敗 (空檔案)"
        rm -f "$output"
        incr_fail
      fi
    else
      echo "失敗"
      incr_fail
    fi
  fi
done

echo "---"
echo "完成: ${success} 成功, ${fail} 失敗"
