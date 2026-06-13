#!/usr/bin/env python3
"""
add_characters_clues.py - 批次新增角色/道具到 project.json

用法（需從專案目錄內執行，必須單行）:
    python .claude/skills/manage-project/scripts/add_characters_clues.py --characters '{"角色名": {"description": "...", "voice_style": "..."}}' --clues '{"道具名": {"description": "...", "importance": "major"}}'
"""

import argparse
import json
import sys
from pathlib import Path

# 允許從倉庫任意工作目錄直接執行該指令碼
PROJECT_ROOT = (
    Path(__file__).resolve().parents[5]
)  # agent_runtime_profile/.claude/skills/manage-project/scripts -> repo root
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.data_validator import validate_project
from lib.project_manager import ProjectManager


def _fail(message: str, *, detail: str | None = None) -> None:
    print(message, file=sys.stderr)
    if detail:
        print(detail, file=sys.stderr)
    sys.exit(1)


def _parse_json_object(raw: str, label: str) -> dict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        _fail(
            f"❌ {label} 參數不是合法的 JSON：{e}",
            detail=f"   收到的內容：{raw[:200]}",
        )
    if not isinstance(value, dict):
        _fail(f"❌ {label} 必須是 JSON 物件（{{名稱: {{...}}}}），收到的是 {type(value).__name__}")
    return value


def _read_stdin_payload() -> dict:
    try:
        value = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        _fail(f"❌ stdin 不是合法的 JSON：{e}")
    if not isinstance(value, dict):
        _fail("❌ stdin 必須是包含 characters / clues 欄位的 JSON 物件")
    return value


def _get_stdin_mapping(payload: dict, key: str) -> tuple[dict, bool]:
    if key not in payload:
        return {}, False
    value = payload[key]
    if not isinstance(value, dict):
        _fail(f"❌ stdin.{key} 必須是 JSON 物件")
    return value, True


def _verify_persisted(pm: ProjectManager, project_name: str, key: str, entries: dict, label: str) -> None:
    persisted = pm.load_project(project_name).get(key, {})
    missing = [name for name in entries if name not in persisted]
    if missing:
        _fail(f"❌ {label}寫入後驗證失敗：以下{label}未出現在 project.json：{missing}")


def main():
    parser = argparse.ArgumentParser(
        description="批次新增角色/道具到 project.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例（需從專案目錄內執行，必須單行）:
    %(prog)s --characters '{"李白": {"description": "白衣劍客", "voice_style": "豪放"}}'
    %(prog)s --clues '{"玉佩": {"description": "溫潤白玉", "importance": "major"}}'
        """,
    )

    parser.add_argument(
        "--characters",
        type=str,
        default=None,
        help="JSON 格式的角色資料",
    )
    parser.add_argument(
        "--clues",
        type=str,
        default=None,
        help="JSON 格式的線索資料",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="從 stdin 讀取 JSON（包含 characters 和/或 clues 欄位）",
    )

    args = parser.parse_args()

    characters: dict = {}
    clues: dict = {}
    # 記錄使用者「打算」寫入的型別，用來在實際沒寫進去時報錯
    characters_requested = False
    clues_requested = False

    if args.stdin:
        stdin_data = _read_stdin_payload()
        characters, characters_requested = _get_stdin_mapping(stdin_data, "characters")
        clues, clues_requested = _get_stdin_mapping(stdin_data, "clues")
    else:
        if args.characters is not None:
            characters_requested = True
            characters = _parse_json_object(args.characters, "--characters")
        if args.clues is not None:
            clues_requested = True
            clues = _parse_json_object(args.clues, "--clues")

    if not characters_requested and not clues_requested:
        _fail("❌ 未提供角色或線索資料（需要 --characters 或 --clues）")
    if characters_requested and not characters:
        _fail("❌ --characters 提供了但內容為空物件，沒有任何角色可新增")
    if clues_requested and not clues:
        _fail("❌ --clues 提供了但內容為空物件，沒有任何線索可新增")

    pm, project_name = ProjectManager.from_cwd()

    # 新增角色
    chars_added = 0
    chars_skipped = 0
    if characters:
        project = pm.load_project(project_name)
        existing = project.get("characters", {})
        chars_skipped = sum(1 for name in characters if name in existing)
        chars_added = pm.add_characters_batch(project_name, characters)
        print(f"角色: 新增 {chars_added} 個，跳過 {chars_skipped} 個（已存在）")
        # 驗證確實寫進去了：要求寫入 N 個，最終 project.json 必須有這 N 個
        _verify_persisted(pm, project_name, "characters", characters, "角色")

    # 新增線索
    clues_added = 0
    clues_skipped = 0
    if clues:
        project = pm.load_project(project_name)
        existing = project.get("clues", {})
        clues_skipped = sum(1 for name in clues if name in existing)
        clues_added = pm.add_clues_batch(project_name, clues)
        print(f"線索: 新增 {clues_added} 個，跳過 {clues_skipped} 個（已存在）")
        _verify_persisted(pm, project_name, "clues", clues, "線索")

    # 資料驗證
    result = validate_project(project_name, projects_root=str(pm.projects_root))
    if result.valid:
        print("✅ 資料驗證透過")
    else:
        print("⚠️ 資料驗證發現問題:")
        for error in result.errors:
            print(f"  錯誤: {error}")
        for warning in result.warnings:
            print(f"  警告: {warning}")
        sys.exit(1)

    # 彙總
    total_added = chars_added + clues_added
    if total_added > 0:
        print(f"\n✅ 完成: 共新增 {total_added} 條資料")
    else:
        print("\nℹ️ 所有資料已存在，無新增")


if __name__ == "__main__":
    main()
