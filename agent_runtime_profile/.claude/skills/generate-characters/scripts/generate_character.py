#!/usr/bin/env python3
"""
Character Generator - 使用 Gemini API 生成角色設計圖

Usage:
    python generate_character.py --character "張三"
    python generate_character.py --characters "張三" "李四"
    python generate_character.py --all
    python generate_character.py --list

Note:
    參考圖會自動從 project.json 中的 reference_image 欄位讀取
"""

import argparse
import sys
from pathlib import Path

from lib.generation_queue_client import (
    BatchTaskResult,
    BatchTaskSpec,
    batch_enqueue_and_wait_sync,
)
from lib.generation_queue_client import (
    enqueue_and_wait_sync as enqueue_and_wait,
)
from lib.project_manager import ProjectManager


def generate_character(
    character_name: str,
) -> Path:
    """
    生成單個角色設計圖

    Args:
        character_name: 角色名稱

    Returns:
        生成的圖片路徑
    """
    pm, project_name = ProjectManager.from_cwd()
    project_dir = pm.get_project_path(project_name)

    # 從 project.json 獲取角色資訊
    project = pm.load_project(project_name)

    description = ""
    if "characters" in project and character_name in project["characters"]:
        char_info = project["characters"][character_name]
        description = char_info.get("description", "")

    if not description:
        raise ValueError(f"角色 '{character_name}' 的描述為空，請先在 project.json 中新增描述")

    print(f"🎨 正在生成角色設計圖: {character_name}")
    print(f"   描述: {description[:50]}...")

    queued = enqueue_and_wait(
        project_name=project_name,
        task_type="character",
        media_type="image",
        resource_id=character_name,
        payload={"prompt": description},
        source="skill",
    )
    result = queued.get("result") or {}
    relative_path = result.get("file_path") or f"characters/{character_name}.png"
    output_path = project_dir / relative_path
    version = result.get("version")
    version_text = f" (版本 v{version})" if version is not None else ""
    print(f"✅ 角色設計圖已儲存: {output_path}{version_text}")
    return output_path


def list_pending_characters() -> None:
    """列出待生成設計圖的角色"""
    pm, project_name = ProjectManager.from_cwd()
    pending = pm.get_pending_characters(project_name)

    if not pending:
        print(f"✅ 專案 '{project_name}' 中所有角色都已有設計圖")
        return

    print(f"\n📋 待生成的角色 ({len(pending)} 個):\n")
    for char in pending:
        print(f"  🧑 {char['name']}")
        desc = char.get("description", "")
        print(f"     描述: {desc[:60]}..." if len(desc) > 60 else f"     描述: {desc}")
        print()


def generate_batch_characters(
    character_names: list[str] | None = None,
) -> tuple[int, int]:
    """
    批次生成角色設計圖（全部入隊，由 Worker 並行處理）

    Args:
        character_names: 指定的角色名稱列表。None 表示所有待處理角色。

    Returns:
        (成功數, 失敗數)
    """
    pm, project_name = ProjectManager.from_cwd()
    project = pm.load_project(project_name)

    if character_names:
        chars = project.get("characters", {})
        names_to_process = []
        for name in character_names:
            if name not in chars:
                print(f"⚠️  角色 '{name}' 不存在於 project.json 中，跳過")
                continue
            if not chars[name].get("description"):
                print(f"⚠️  角色 '{name}' 缺少描述，跳過")
                continue
            names_to_process.append(name)
    else:
        pending = pm.get_pending_characters(project_name)
        names_to_process = [c["name"] for c in pending]

    if not names_to_process:
        print("✅ 沒有需要生成的角色")
        return (0, 0)

    specs = [
        BatchTaskSpec(
            task_type="character",
            media_type="image",
            resource_id=name,
            payload={"prompt": project["characters"][name]["description"]},
        )
        for name in names_to_process
    ]

    total = len(specs)
    print(f"\n🚀 批次提交 {total} 個角色設計圖到生成佇列...\n")

    def on_success(br: BatchTaskResult) -> None:
        version = (br.result or {}).get("version")
        version_text = f" (版本 v{version})" if version is not None else ""
        print(f"✅ 角色設計圖: {br.resource_id} 完成{version_text}")

    def on_failure(br: BatchTaskResult) -> None:
        print(f"❌ 角色設計圖: {br.resource_id} 失敗 - {br.error}")

    successes, failures = batch_enqueue_and_wait_sync(
        project_name=project_name,
        specs=specs,
        on_success=on_success,
        on_failure=on_failure,
    )

    print(f"\n{'=' * 40}")
    print("生成完成!")
    print(f"   ✅ 成功: {len(successes)}")
    print(f"   ❌ 失敗: {len(failures)}")
    print(f"{'=' * 40}")

    return (len(successes), len(failures))


def main():
    parser = argparse.ArgumentParser(description="生成角色設計圖")
    parser.add_argument("--character", help="指定單個角色名稱")
    parser.add_argument("--characters", nargs="+", help="指定多個角色名稱")
    parser.add_argument("--all", action="store_true", help="生成所有待處理的角色")
    parser.add_argument("--list", action="store_true", help="列出待生成的角色")

    args = parser.parse_args()

    try:
        if args.list:
            list_pending_characters()
        elif args.all:
            _, fail = generate_batch_characters()
            sys.exit(0 if fail == 0 else 1)
        elif args.characters:
            _, fail = generate_batch_characters(args.characters)
            sys.exit(0 if fail == 0 else 1)
        elif args.character:
            output_path = generate_character(args.character)
            print(f"\n🖼️  請檢視生成的圖片: {output_path}")
        else:
            parser.print_help()
            print("\n❌ 請指定 --all、--characters、--character 或 --list")
            sys.exit(1)

    except Exception as e:
        print(f"❌ 錯誤: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
