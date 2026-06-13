#!/usr/bin/env bash
# new-worktree.sh — 建立隔離 git worktree 並同步本地環境檔案
#
# Usage: scripts/new-worktree.sh <branch-name> [base-ref]
#   branch-name: 新 worktree 的本地分支名（也用作目錄名）
#   base-ref:    可選，基於哪個 ref 建立（如 origin/feature/xxx），預設 HEAD

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <branch-name> [base-ref]"
  echo "  branch-name: worktree 目錄名及本地分支名"
  echo "  base-ref:    基於哪個 ref 建立（預設 HEAD）"
  exit 1
fi

BRANCH_NAME="$1"
BASE_REF="${2:-HEAD}"
ROOT=$(git rev-parse --show-toplevel)
TARGET="$ROOT/.worktrees/$BRANCH_NAME"

# --- 建立 worktree ---
if [ -d "$TARGET" ]; then
  echo "✗ 目錄已存在: $TARGET"
  exit 1
fi

if [ "$BASE_REF" = "HEAD" ]; then
  git worktree add "$TARGET" -b "$BRANCH_NAME"
else
  git worktree add "$TARGET" --track -b "$BRANCH_NAME" "$BASE_REF"
fi
echo "✓ 已建立 worktree: $TARGET"

# --- 同步本地環境檔案 ---
echo ""
echo "同步本地環境檔案..."

# .claude/settings.local.json
if [ -f "$ROOT/.claude/settings.local.json" ]; then
  mkdir -p "$TARGET/.claude"
  cp "$ROOT/.claude/settings.local.json" "$TARGET/.claude/settings.local.json"
  echo "  ✓ .claude/settings.local.json"
else
  echo "  - .claude/settings.local.json 不存在，已跳過"
fi

# .env
if [ -f "$ROOT/.env" ]; then
  cp "$ROOT/.env" "$TARGET/.env"
  echo "  ✓ .env"
else
  echo "  - .env 不存在，已跳過"
fi

# projects/ — 符號連結共享資料
if [ -d "$ROOT/projects" ]; then
  rm -rf "$TARGET/projects"
  ln -s "$ROOT/projects" "$TARGET/projects"
  git -C "$TARGET" ls-files projects/ | xargs -r git -C "$TARGET" update-index --skip-worktree
  echo "  ✓ projects/ → $ROOT/projects (符號連結)"
else
  echo "  - projects/ 不存在，已跳過"
fi

# .vscode/
if [ -d "$ROOT/.vscode" ]; then
  cp -r "$ROOT/.vscode" "$TARGET/.vscode"
  echo "  ✓ .vscode/"
else
  echo "  - .vscode/ 不存在，已跳過"
fi

# --- 安裝依賴 ---
echo ""
echo "安裝專案依賴..."

if [ -f "$TARGET/pyproject.toml" ]; then
  (cd "$TARGET" && uv sync)
  echo "  ✓ Python 依賴 (uv sync)"
fi

if [ -f "$TARGET/frontend/package.json" ]; then
  (cd "$TARGET/frontend" && pnpm install)
  echo "  ✓ 前端依賴 (pnpm install)"
fi

# --- 完成 ---
echo ""
echo "========================================="
echo "Worktree 已就緒: $TARGET"
echo "分支: $BRANCH_NAME"
echo "========================================="
