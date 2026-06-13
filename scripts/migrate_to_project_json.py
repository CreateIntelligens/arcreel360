#!/usr/bin/env python3
"""
資料遷移指令碼：將現有專案的 characters 從劇本遷移到 project.json

使用方法：
    python scripts/migrate_to_project_json.py <專案名>
    python scripts/migrate_to_project_json.py --all  # 遷移所有專案
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 新增 lib 目錄到 Python 路徑
lib_path = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(lib_path))

from project_manager import ProjectManager


def migrate_project(pm: ProjectManager, project_name: str, dry_run: bool = False) -> bool:
    """
    遷移單個專案

    Args:
        pm: ProjectManager 例項
        project_name: 專案名稱
        dry_run: 是否只預覽不執行

    Returns:
        是否成功
    """
    print(f"\n{'=' * 50}")
    print(f"遷移專案: {project_name}")
    print("=" * 50)

    try:
        project_dir = pm.get_project_path(project_name)
    except FileNotFoundError:
        print(f"  ❌ 專案不存在: {project_name}")
        return False

    # 檢查是否已有 project.json
    project_file = project_dir / "project.json"
    if project_file.exists():
        print("  ⚠️  project.json 已存在，跳過遷移")
        print(f"  如需重新遷移，請先刪除 {project_file}")
        return True

    # 收集所有劇本中的角色
    scripts_dir = project_dir / "scripts"
    all_characters = {}
    episodes = []
    script_files = list(scripts_dir.glob("*.json")) if scripts_dir.exists() else []

    if not script_files:
        print("  ⚠️  未找到劇本檔案")

    for script_file in sorted(script_files):
        print(f"\n  📖 處理劇本: {script_file.name}")

        with open(script_file, encoding="utf-8") as f:
            script = json.load(f)

        # 提取角色
        characters = script.get("characters", {})
        for name, char_data in characters.items():
            if name not in all_characters:
                all_characters[name] = char_data.copy()
                print(f"      👤 發現角色: {name}")
            else:
                # 合併資料（優先保留有設計圖的版本）
                if char_data.get("character_sheet") and not all_characters[name].get("character_sheet"):
                    all_characters[name] = char_data.copy()
                    print(f"      👤 更新角色: {name} (有設計圖)")

        # 提取劇集資訊
        novel_info = script.get("novel", {})
        scenes_count = len(script.get("scenes", []))

        # 嘗試從檔名或內容推斷集數
        episode_num = 1
        filename_lower = script_file.stem.lower()
        for i in range(1, 100):
            if f"episode_{i:02d}" in filename_lower or f"episode{i}" in filename_lower:
                episode_num = i
                break
            if f"chapter_{i:02d}" in filename_lower or f"chapter{i}" in filename_lower:
                episode_num = i
                break
            if f"_{i:02d}_" in filename_lower or f"_{i}_" in filename_lower:
                episode_num = i
                break

        # 新增劇集資訊（不包含統計欄位，由 StatusCalculator 讀時計算）
        episodes.append(
            {
                "episode": episode_num,
                "title": novel_info.get("chapter", script_file.stem),
                "script_file": f"scripts/{script_file.name}",
            }
        )
        print(f"      📺 劇集 {episode_num}: {scenes_count} 個場景")

    # 去重並排序劇集
    seen_episodes = {}
    for ep in episodes:
        if ep["episode"] not in seen_episodes:
            seen_episodes[ep["episode"]] = ep
    episodes = sorted(seen_episodes.values(), key=lambda x: x["episode"])

    # 構建 project.json
    project_title = project_name
    if script_files:
        with open(script_files[0], encoding="utf-8") as f:
            first_script = json.load(f)
            project_title = first_script.get("novel", {}).get("title", project_name)

    # 構建 project.json（不包含 status 欄位，由 StatusCalculator 讀時計算）
    project_data = {
        "title": project_title,
        "style": "",
        "episodes": episodes,
        "characters": all_characters,
        "clues": {},
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "migrated_from": "script_based_characters",
        },
    }

    # 統計已完成的角色設計圖（僅用於日誌輸出）
    completed_chars = 0
    for name, char_data in all_characters.items():
        sheet = char_data.get("character_sheet")
        if sheet:
            sheet_path = project_dir / sheet
            if sheet_path.exists():
                completed_chars += 1

    # 建立 clues 目錄
    clues_dir = project_dir / "clues"
    if not clues_dir.exists():
        if not dry_run:
            clues_dir.mkdir(parents=True, exist_ok=True)
        print("\n  📁 建立目錄: clues/")

    print("\n  📊 遷移摘要:")
    print(f"      - 角色: {len(all_characters)} 個 ({completed_chars} 個有設計圖)")
    print(f"      - 劇集: {len(episodes)} 個")
    print("      - 線索: 0 個 (待新增)")

    if dry_run:
        print("\n  🔍 預覽模式 - 不會實際寫入檔案")
        print("\n  將建立 project.json:")
        print(json.dumps(project_data, ensure_ascii=False, indent=2)[:500] + "...")
    else:
        # 寫入 project.json
        with open(project_file, "w", encoding="utf-8") as f:
            json.dump(project_data, f, ensure_ascii=False, indent=2)
        print("\n  ✅ 已建立 project.json")

        # 可選：從劇本中移除 characters 欄位（保留原檔案備份）
        # 這裡我們保留劇本中的 characters 以保持向後相容
        print("  ℹ️  保留劇本中的 characters 欄位以保持向後相容")

    return True


def main():
    parser = argparse.ArgumentParser(description="遷移專案資料到 project.json")
    parser.add_argument("project", nargs="?", help="專案名稱，或使用 --all 遷移所有專案")
    parser.add_argument("--all", action="store_true", help="遷移所有專案")
    parser.add_argument("--dry-run", action="store_true", help="預覽模式，不實際執行")
    parser.add_argument("--projects-root", default=None, help="專案根目錄")

    args = parser.parse_args()

    if not args.project and not args.all:
        parser.print_help()
        print("\n❌ 請指定專案名稱或使用 --all")
        sys.exit(1)

    # 初始化 ProjectManager
    pm = ProjectManager(projects_root=args.projects_root)

    print("🚀 開始遷移...")
    print(f"   專案根目錄: {pm.projects_root}")

    if args.dry_run:
        print("   📋 預覽模式已啟用")

    success_count = 0
    fail_count = 0

    if args.all:
        projects = pm.list_projects()
        print(f"   發現 {len(projects)} 個專案")

        for project_name in projects:
            if migrate_project(pm, project_name, dry_run=args.dry_run):
                success_count += 1
            else:
                fail_count += 1
    else:
        if migrate_project(pm, args.project, dry_run=args.dry_run):
            success_count = 1
        else:
            fail_count = 1

    print("\n" + "=" * 50)
    print("遷移完成!")
    print(f"   ✅ 成功: {success_count}")
    print(f"   ❌ 失敗: {fail_count}")
    print("=" * 50)

    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
