#!/usr/bin/env python3
"""
split_episode.py - 執行分集切分

使用目標字數 + 錨點文字配合定位切分位置，將小說切分為 episode_N.txt 和 _remaining.txt。
目標字數縮小搜尋視窗，錨點文字精確定位。

用法:
    # Dry run（僅預覽）
    python split_episode.py --source source/novel.txt --episode 1 --target 1000 --anchor "他轉身離開了。" --dry-run

    # 實際執行
    python split_episode.py --source source/novel.txt --episode 1 --target 1000 --anchor "他轉身離開了。"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _text_utils import find_anchor_near_target, find_char_offset


def main():
    parser = argparse.ArgumentParser(description="執行分集切分")
    parser.add_argument("--source", required=True, help="原始檔路徑")
    parser.add_argument("--episode", required=True, type=int, help="集數編號")
    parser.add_argument("--target", required=True, type=int, help="目標字數（與 peek 的 --target 一致）")
    parser.add_argument("--anchor", required=True, help="切分點前的文字片段（10-20 字元）")
    parser.add_argument("--context", default=500, type=int, help="搜尋視窗大小（預設 500 字元）")
    parser.add_argument("--dry-run", action="store_true", help="僅展示切分預覽，不寫檔案")
    args = parser.parse_args()

    source_path = Path(args.source).resolve()
    if not source_path.is_relative_to(Path.cwd().resolve()):
        print(f"錯誤：原始檔路徑超出當前專案目錄: {source_path}", file=sys.stderr)
        sys.exit(1)
    if not source_path.exists():
        print(f"錯誤：原始檔不存在: {source_path}", file=sys.stderr)
        sys.exit(1)

    text = source_path.read_text(encoding="utf-8")

    # 用目標字數計算大致偏移位置
    target_offset = find_char_offset(text, args.target)

    # 在目標偏移附近搜尋錨點
    positions = find_anchor_near_target(text, args.anchor, target_offset, window=args.context)

    if len(positions) == 0:
        print(
            f'錯誤：在目標字數 {args.target} 附近（±{args.context} 字元視窗）未找到錨點文字: "{args.anchor}"',
            file=sys.stderr,
        )
        sys.exit(1)

    if len(positions) > 1:
        print(
            f"警告：錨點文字在視窗內匹配到 {len(positions)} 處，使用距離目標最近的匹配。",
            file=sys.stderr,
        )
        for i, pos in enumerate(positions):
            ctx_start = max(0, pos - len(args.anchor) - 10)
            ctx_end = min(len(text), pos + 10)
            distance = abs(pos - target_offset)
            marker = " ← 選中" if i == 0 else ""
            print(f"  匹配 {i + 1} (距離 {distance}): ...{text[ctx_start:ctx_end]}...{marker}", file=sys.stderr)

    split_pos = positions[0]
    part_before = text[:split_pos]
    part_after = text[split_pos:]

    # 展示切分預覽
    preview_len = 50
    before_preview = part_before[-preview_len:] if len(part_before) > preview_len else part_before
    after_preview = part_after[:preview_len] if len(part_after) > preview_len else part_after

    print(f"目標字數: {args.target}，目標偏移: {target_offset}")
    print(f"切分位置: 第 {split_pos} 字元處")
    print(f"前文末尾: ...{before_preview}")
    print(f"後文開頭: {after_preview}...")
    print(f"前半部分: {len(part_before)} 字元")
    print(f"後半部分: {len(part_after)} 字元")

    if args.dry_run:
        print("\n[Dry Run] 未寫入檔案。確認無誤後去掉 --dry-run 引數執行。")
        return

    # 實際寫入檔案
    output_dir = source_path.parent
    episode_file = output_dir / f"episode_{args.episode}.txt"
    remaining_file = output_dir / "_remaining.txt"

    episode_file.write_text(part_before, encoding="utf-8")
    remaining_file.write_text(part_after, encoding="utf-8")

    print("\n已生成:")
    print(f"  {episode_file} ({len(part_before)} 字元)")
    print(f"  {remaining_file} ({len(part_after)} 字元)")
    print(f"  原檔案未修改: {source_path}")


if __name__ == "__main__":
    main()
