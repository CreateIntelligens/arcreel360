#!/bin/bash
# 下載 Claude Agent SDK 文件到當前目錄
# 用法: cd docs/claude-agent-sdk-docs && bash download_docs.sh

set -euo pipefail

BASE_URL="https://platform.claude.com/docs/en/agent-sdk"
OUTPUT_DIR="$(cd "$(dirname "$0")" && pwd)"

DOCS=(
  # 頂層
  "overview"
  "quickstart"
  "agent-loop"

  # Guides
  "streaming-vs-single-mode"
  "streaming-output"
  "permissions"
  "user-input"
  "hooks"
  "file-checkpointing"
  "structured-outputs"
  "hosting"
  "secure-deployment"
  "modifying-system-prompts"
  "mcp"
  "custom-tools"
  "subagents"
  "slash-commands"
  "skills"
  "cost-tracking"
  "todo-tracking"
  "plugins"

  "sessions"

  # SDK References
  "python"
)

echo "下載目錄: $OUTPUT_DIR"
echo "共 ${#DOCS[@]} 個文件待下載"
echo "---"

success=0
fail=0

for doc in "${DOCS[@]}"; do
  url="${BASE_URL}/${doc}.md"
  output="${OUTPUT_DIR}/${doc}.md"

  echo -n "下載 ${doc}.md ... "

  if curl -fsSL "$url" -o "$output" 2>/dev/null; then
    size=$(wc -c < "$output" | tr -d ' ')
    echo "成功 (${size} bytes)"
    ((success++))
  else
    echo "失敗，嘗試從頁面提取..."
    # 如果 .md 直接下載失敗，嘗試抓取 HTML 頁面
    page_url="${BASE_URL}/${doc}"
    if curl -fsSL "$page_url" -o "${output}.html" 2>/dev/null; then
      # 保留 HTML 備用，標記需要手動處理
      mv "${output}.html" "$output"
      size=$(wc -c < "$output" | tr -d ' ')
      echo "已儲存 HTML (${size} bytes)"
      ((success++))
    else
      echo "失敗"
      ((fail++))
    fi
  fi
done

echo "---"
echo "完成: ${success} 成功, ${fail} 失敗"
