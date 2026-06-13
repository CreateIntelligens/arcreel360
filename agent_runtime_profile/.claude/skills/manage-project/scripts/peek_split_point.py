#!/usr/bin/env python3
"""
peek_split_point.py - 切分點探測指令碼

展示目標字數附近的上下文，幫助 agent 和使用者決定自然斷點。

用法:
    python peek_split_point.py --source source/novel.txt --target 1000
    python peek_split_point.py --source source/novel.txt --target 1000 --context 300
"""

import argparse
import json
import sys
from pathlib import Path

# 匯入共享工具
sys.path.insert(0, str(Path(__file__).parent))
from _text_utils import count_chars, find_char_offset, find_natural_breakpoints


def main():
    parser = argparse.ArgumentParser(description="探測切分點附近上下文")
    parser.add_argument("--source", required=True, help="原始檔路徑")
    parser.add_argument("--target", required=True, type=int, help="目標字數（有效字數）")
    parser.add_argument("--context", default=200, type=int, help="上下文字數（預設 200）")
    args = parser.parse_args()

    source_path = Path(args.source).resolve()
    if not source_path.is_relative_to(Path.cwd().resolve()):
        print(f"錯誤：原始檔路徑超出當前專案目錄: {source_path}", file=sys.stderr)
        sys.exit(1)
    if not source_path.exists():
        print(f"錯誤：原始檔不存在: {source_path}", file=sys.stderr)
        sys.exit(1)

    text = source_path.read_text(encoding="utf-8")
    total_chars = count_chars(text)

    if args.target >= total_chars:
        print(f"錯誤：目標字數 ({args.target}) 超過或等於總有效字數 ({total_chars})", file=sys.stderr)
        sys.exit(1)

    # 定位目標字數對應的原文偏移
    target_offset = find_char_offset(text, args.target)

    # 查詢附近的自然斷點
    breakpoints = find_natural_breakpoints(text, target_offset, window=args.context)

    # 提取上下文
    ctx_start = max(0, target_offset - args.context)
    ctx_end = min(len(text), target_offset + args.context)
    before_context = text[ctx_start:target_offset]
    after_context = text[target_offset:ctx_end]

    # 輸出結果
    result = {
        "source": str(source_path),
        "total_chars": total_chars,
        "target_chars": args.target,
        "target_offset": target_offset,
        "context_before": before_context,
        "context_after": after_context,
        "nearby_breakpoints": breakpoints[:10],  # 只取最近的 10 個
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
