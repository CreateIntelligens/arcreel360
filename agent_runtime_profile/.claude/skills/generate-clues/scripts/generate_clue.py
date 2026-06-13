#!/usr/bin/env python3
"""
Clue Generator - 使用 Gemini API 生成線索設計圖

Usage:
    python generate_clue.py --all
    python generate_clue.py --clue "玉佩"
    python generate_clue.py --clues "玉佩" "密信"
    python generate_clue.py --list

Example:
    python generate_clue.py --all
    python generate_clue.py --clue "玉佩"
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


def generate_clue(clue_name: str) -> Path:
    """
    生成單個線索設計圖

    Args:
        clue_name: 線索名稱

    Returns:
        生成的圖片路徑
    """
    pm, project_name = ProjectManager.from_cwd()
    project_dir = pm.get_project_path(project_name)

    # 獲取線索資訊
    clue = pm.get_clue(project_name, clue_name)
    description = clue.get("description", "")

    if not description:
        raise ValueError(f"線索 '{clue_name}' 的描述為空，請先新增描述")

    print(f"🎨 正在生成線索設計圖: {clue_name}")
    print(f"   描述: {description[:50]}..." if len(description) > 50 else f"   描述: {description}")

    queued = enqueue_and_wait(
        project_name=project_name,
        task_type="clue",
        media_type="image",
        resource_id=clue_name,
        payload={"prompt": description},
        source="skill",
    )
    result = queued.get("result") or {}
    relative_path = result.get("file_path") or f"clues/{clue_name}.png"
    output_path = project_dir / relative_path
    version = result.get("version")
    version_text = f" (版本 v{version})" if version is not None else ""
    print(f"✅ 線索設計圖已儲存: {output_path}{version_text}")
    return output_path


def list_pending_clues() -> None:
    """
    列出待生成的線索
    """
    pm, project_name = ProjectManager.from_cwd()
    pending = pm.get_pending_clues(project_name)

    if not pending:
        print(f"✅ 專案 '{project_name}' 中所有重要線索都已有設計圖")
        return

    print(f"\n📋 待生成的線索 ({len(pending)} 個):\n")
    for clue in pending:
        print(f"  📦 {clue['name']}")
        print(f"     描述: {clue.get('description', '')[:60]}...")
        print()


def generate_batch_clues(
    clue_names: list[str] | None = None,
) -> tuple[int, int]:
    """
    批次生成線索設計圖（全部入隊，由 Worker 並行處理）

    Args:
        clue_names: 指定的線索名稱列表。None 表示所有待處理線索。

    Returns:
        (成功數, 失敗數)
    """
    pm, project_name = ProjectManager.from_cwd()
    project = pm.load_project(project_name)
    clues_dict = project.get("clues", {})

    if clue_names:
        names_to_process = []
        for name in clue_names:
            if name not in clues_dict:
                print(f"⚠️  線索 '{name}' 不存在於 project.json 中，跳過")
                continue
            if not clues_dict[name].get("description"):
                print(f"⚠️  線索 '{name}' 缺少描述，跳過")
                continue
            names_to_process.append(name)
    else:
        pending = pm.get_pending_clues(project_name)
        names_to_process = [c["name"] for c in pending]

    if not names_to_process:
        print("✅ 沒有需要生成的線索")
        return (0, 0)
    specs = [
        BatchTaskSpec(
            task_type="clue",
            media_type="image",
            resource_id=name,
            payload={"prompt": clues_dict[name]["description"]},
        )
        for name in names_to_process
    ]

    total = len(specs)
    print(f"\n🚀 批次提交 {total} 個線索設計圖到生成佇列...\n")

    def on_success(br: BatchTaskResult) -> None:
        version = (br.result or {}).get("version")
        version_text = f" (版本 v{version})" if version is not None else ""
        print(f"✅ 線索設計圖: {br.resource_id} 完成{version_text}")

    def on_failure(br: BatchTaskResult) -> None:
        print(f"❌ 線索設計圖: {br.resource_id} 失敗 - {br.error}")

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
    parser = argparse.ArgumentParser(description="生成線索設計圖")
    parser.add_argument("--all", action="store_true", help="生成所有待處理的線索")
    parser.add_argument("--clue", help="指定單個線索名稱")
    parser.add_argument("--clues", nargs="+", help="指定多個線索名稱")
    parser.add_argument("--list", action="store_true", help="列出待生成的線索")

    args = parser.parse_args()

    try:
        if args.list:
            list_pending_clues()
        elif args.all:
            _, fail = generate_batch_clues()
            sys.exit(0 if fail == 0 else 1)
        elif args.clues:
            _, fail = generate_batch_clues(args.clues)
            sys.exit(0 if fail == 0 else 1)
        elif args.clue:
            output_path = generate_clue(args.clue)
            print(f"\n🖼️  請檢視生成的圖片: {output_path}")
        else:
            parser.print_help()
            print("\n❌ 請指定 --all、--clues、--clue 或 --list")
            sys.exit(1)

    except Exception as e:
        print(f"❌ 錯誤: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
