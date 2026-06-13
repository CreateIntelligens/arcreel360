"""一次性把專案內所有簡體中文用 OpenCC s2twp 轉成繁體（臺灣正體 + 慣用詞）。

用法：
    uv run --with opencc-python-reimplemented python scripts/convert_to_traditional.py [--dry-run]

掃描範圍見 INCLUDE_DIRS / ROOT_FILES，排除見 EXCLUDE_DIRS / EXCLUDE_FILES。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from opencc import OpenCC

ROOT = Path(__file__).resolve().parent.parent

INCLUDE_DIRS = [
    "frontend/src",
    "frontend/public",
    "frontend/index.html",
    "server",
    "lib",
    "tests",
    "scripts",
    "alembic",
    "docs",
    "agent_runtime_profile",
    "openspec",
    "deploy",
]

ROOT_FILES = [
    "README.md",
    "CHANGELOG.md",
    "CLAUDE.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "Dockerfile",
    "docker-compose.yml",
    "alembic.ini",
    "pyproject.toml",
    ".env.example",
]

EXCLUDE_DIRS = {
    "projects",
    "pgdata",
    "vertex_keys",
    "claude_data",
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".worktree",
    ".worktrees",
}

EXCLUDE_FILE_NAMES = {
    "uv.lock",
    "pnpm-lock.yaml",
    "package-lock.json",
    "yarn.lock",
    "skills-lock.json",
    "package.json",
    "tsconfig.json",
    "tsconfig.app.json",
    "tsconfig.node.json",
}

ALLOWED_SUFFIXES = {
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".md",
    ".mdx",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".sass",
    ".txt",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".sh",
    ".sql",
    ".json",  # JSON：只在白名單目錄下
    ".env",
    ".example",
}

JSON_ALLOWED_PARENTS = ("docs", "openspec", "agent_runtime_profile", "tests", "alembic")


def is_excluded_path(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDE_DIRS:
        return True
    if path.name in EXCLUDE_FILE_NAMES:
        return True
    return False


def should_process(path: Path) -> bool:
    if not path.is_file():
        return False
    if is_excluded_path(path.relative_to(ROOT)):
        return False
    name = path.name
    suffix = path.suffix.lower()

    if name in {"Dockerfile", "docker-compose.yml", ".env.example"}:
        return True
    if suffix not in ALLOWED_SUFFIXES and name not in ROOT_FILES:
        return False
    if suffix == ".json":
        rel = path.relative_to(ROOT)
        return any(part in JSON_ALLOWED_PARENTS for part in rel.parts)
    return True


def iter_targets():
    seen = set()
    for entry in INCLUDE_DIRS:
        p = ROOT / entry
        if not p.exists():
            continue
        if p.is_file():
            if should_process(p):
                seen.add(p.resolve())
            continue
        for f in p.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(ROOT)
            if is_excluded_path(rel):
                continue
            if should_process(f):
                seen.add(f.resolve())
    for name in ROOT_FILES:
        p = ROOT / name
        if p.exists() and should_process(p):
            seen.add(p.resolve())
    return sorted(seen)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只列出會修改的檔案，不寫入")
    args = ap.parse_args()

    cc = OpenCC("s2twp")
    targets = iter_targets()
    print(f"掃描 {len(targets)} 個檔案…")

    changed = []
    skipped_binary = 0
    for path in targets:
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            skipped_binary += 1
            continue
        converted = cc.convert(original)
        if converted != original:
            changed.append(path)
            if not args.dry_run:
                path.write_text(converted, encoding="utf-8")

    print(f"\n變更檔案：{len(changed)}")
    for p in changed:
        print(f"  {p.relative_to(ROOT)}")
    if skipped_binary:
        print(f"\n略過二進位/非 UTF-8：{skipped_binary}")
    if args.dry_run:
        print("\n(dry-run) 未實際寫入。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
