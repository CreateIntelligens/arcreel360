#!/usr/bin/env python3
"""
Storyboard Generator - 透過生成佇列生成分鏡圖

兩種模式統一透過 generation worker 生成分鏡圖：
- narration 模式（說書+畫面）：生成 9:16 豎屏分鏡圖
- drama 模式（劇集動畫）：生成 16:9 橫屏分鏡圖

Usage:
    # narration 模式：提交分鏡圖生成任務（預設）
    python generate_storyboard.py <project_name> <script_file>
    python generate_storyboard.py <project_name> <script_file> --scene E1S05
    python generate_storyboard.py <project_name> <script_file> --segment-ids E1S01 E1S02

    # drama 模式：提交分鏡圖生成任務
    python generate_storyboard.py <project_name> <script_file>
    python generate_storyboard.py <project_name> <script_file> --scene E1S05
    python generate_storyboard.py <project_name> <script_file> --scene-ids E1S01 E1S02
"""

import argparse
import json
import sys
import threading
from datetime import datetime
from pathlib import Path

from lib.generation_queue_client import (
    BatchTaskResult,
    BatchTaskSpec,
    batch_enqueue_and_wait_sync,
)
from lib.project_manager import ProjectManager
from lib.prompt_utils import image_prompt_to_yaml, is_structured_image_prompt
from lib.storyboard_sequence import (
    StoryboardTaskPlan,
    build_storyboard_dependency_plan,
    get_storyboard_items,
)


class FailureRecorder:
    """失敗記錄管理器（執行緒安全）"""

    def __init__(self, output_dir: Path):
        self.output_path = output_dir / "generation_failures.json"
        self.failures: list[dict] = []
        self._lock = threading.Lock()

    def record_failure(
        self,
        scene_id: str,
        failure_type: str,  # "scene"
        error: str,
        attempts: int = 3,
        **extra,
    ):
        """記錄一次失敗"""
        with self._lock:
            self.failures.append(
                {
                    "scene_id": scene_id,
                    "type": failure_type,
                    "error": error,
                    "attempts": attempts,
                    "timestamp": datetime.now().isoformat(),
                    **extra,
                }
            )

    def save(self):
        """儲存失敗記錄到檔案"""
        if not self.failures:
            return

        with self._lock:
            data = {
                "generated_at": datetime.now().isoformat(),
                "total_failures": len(self.failures),
                "failures": self.failures,
            }

            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"\n⚠️  失敗記錄已儲存: {self.output_path}")

    def get_failed_scene_ids(self) -> list[str]:
        """獲取所有失敗的場景 ID（用於生成）"""
        return [f["scene_id"] for f in self.failures if f["type"] == "scene"]


# ==================== Prompt 構建函式 ====================


def get_items_from_script(script: dict) -> tuple:
    """
    根據內容模式獲取場景/片段列表和 ID 欄位名

    Args:
        script: 劇本資料

    Returns:
        (items_list, id_field, char_field, clue_field, scene_field) 元組
    """
    return get_storyboard_items(script)


def build_storyboard_prompt(
    segment: dict,
    characters: dict = None,
    clues: dict = None,
    style: str = "",
    style_description: str = "",
    id_field: str = "segment_id",
    char_field: str = "characters_in_segment",
    clue_field: str = "clues_in_segment",
    content_mode: str = "narration",
) -> str:
    """
    構建分鏡圖任務 prompt（通用，適用於 narration 和 drama 模式）

    支援結構化 prompt 格式：如果 image_prompt 是 dict，則轉換為 YAML 格式。
    """
    image_prompt = segment.get("image_prompt", "")
    if not image_prompt:
        raise ValueError(f"片段/場景 {segment[id_field]} 缺少 image_prompt 欄位")

    # 構建風格字首
    style_parts = []
    if style:
        style_parts.append(f"Style: {style}")
    if style_description:
        style_parts.append(f"Visual style: {style_description}")
    style_prefix = "\n".join(style_parts) + "\n\n" if style_parts else ""

    # narration 模式追加豎屏構圖字尾，drama 模式透過 API aspect_ratio 引數控制
    composition_suffix = ""
    if content_mode == "narration":
        if is_structured_image_prompt(image_prompt):
            composition_suffix = "\n豎屏構圖。"
        else:
            composition_suffix = " 豎屏構圖。"

    # 檢測是否為結構化格式
    if is_structured_image_prompt(image_prompt):
        yaml_prompt = image_prompt_to_yaml(image_prompt, style)
        return f"{style_prefix}{yaml_prompt}{composition_suffix}"

    return f"{style_prefix}{image_prompt}{composition_suffix}"


def _select_storyboard_items(
    items: list[dict],
    id_field: str,
    segment_ids: list[str] | None,
) -> list[dict]:
    if segment_ids:
        selected_set = {str(segment_id) for segment_id in segment_ids}
        return [item for item in items if str(item.get(id_field)) in selected_set]

    return [item for item in items if not item.get("generated_assets", {}).get("storyboard_image")]


def _build_storyboard_specs(
    *,
    plans: list[StoryboardTaskPlan],
    items_by_id: dict[str, dict],
    characters: dict[str, dict],
    clues: dict[str, dict],
    style: str,
    style_description: str,
    id_field: str,
    char_field: str,
    clue_field: str,
    content_mode: str,
    script_filename: str,
) -> list[BatchTaskSpec]:
    """Build BatchTaskSpec list from dependency plans, with prompts and dependency_resource_id."""
    specs: list[BatchTaskSpec] = []
    for plan in plans:
        item = items_by_id[plan.resource_id]
        prompt = build_storyboard_prompt(
            item,
            characters,
            clues,
            style,
            style_description,
            id_field,
            char_field,
            clue_field,
            content_mode=content_mode,
        )
        specs.append(
            BatchTaskSpec(
                task_type="storyboard",
                media_type="image",
                resource_id=plan.resource_id,
                payload={"prompt": prompt, "script_file": script_filename},
                script_file=script_filename,
                dependency_resource_id=plan.dependency_resource_id,
                dependency_group=plan.dependency_group,
                dependency_index=plan.dependency_index,
            )
        )
    return specs


def _load_project_metadata(pm: ProjectManager, project_name: str) -> dict | None:
    """Load project.json if available."""
    if not pm.project_exists(project_name):
        return None
    try:
        data = pm.load_project(project_name)
        print("📁 已載入專案後設資料 (project.json)")
        return data
    except Exception as e:
        print(f"⚠️  無法載入專案後設資料: {e}")
        return None


def _collect_ordered_paths(
    successes: list[BatchTaskResult],
    plans: list[StoryboardTaskPlan],
    project_dir: Path,
) -> list[Path]:
    """Map successes back to plan order and return file paths."""
    success_map = {s.resource_id: s for s in successes}
    paths: list[Path] = []
    for plan in plans:
        br = success_map.get(plan.resource_id)
        if br:
            result = br.result or {}
            relative = result.get("file_path") or f"storyboards/scene_{plan.resource_id}.png"
            paths.append(project_dir / relative)
    return paths


def generate_storyboard_direct(
    script_filename: str,
    segment_ids: list[str] | None = None,
) -> tuple[list[Path], list[tuple[str, str]]]:
    """
    透過生成佇列提交分鏡圖任務（narration 和 drama 模式通用）。

    Returns:
        (成功路徑列表, 失敗列表) 元組
    """
    pm, project_name = ProjectManager.from_cwd()
    script = pm.load_script(project_name, script_filename)
    project_dir = pm.get_project_path(project_name)
    content_mode = script.get("content_mode", "narration")
    project_data = _load_project_metadata(pm, project_name)

    items, id_field, char_field, clue_field, _ = get_items_from_script(script)
    segments_to_process = _select_storyboard_items(items, id_field, segment_ids)

    if not segments_to_process:
        print("✨ 所有片段的分鏡圖都已生成")
        return [], []

    characters = project_data.get("characters", {}) if project_data else {}
    clues = project_data.get("clues", {}) if project_data else {}
    style = project_data.get("style", "") if project_data else ""
    style_description = project_data.get("style_description", "") if project_data else ""
    items_by_id = {str(item[id_field]): item for item in items if item.get(id_field)}
    dependency_plans = build_storyboard_dependency_plan(
        items,
        id_field,
        [str(item[id_field]) for item in segments_to_process],
        script_filename,
    )

    specs = _build_storyboard_specs(
        plans=dependency_plans,
        items_by_id=items_by_id,
        characters=characters,
        clues=clues,
        style=style,
        style_description=style_description,
        id_field=id_field,
        char_field=char_field,
        clue_field=clue_field,
        content_mode=content_mode,
        script_filename=script_filename,
    )

    print(f"📷 批次提交 {len(specs)} 個分鏡圖到生成佇列...")

    recorder = FailureRecorder(project_dir / "storyboards")

    def on_success(br: BatchTaskResult) -> None:
        print(f"✅ 分鏡圖生成: {br.resource_id} 完成")

    def on_failure(br: BatchTaskResult) -> None:
        recorder.record_failure(
            scene_id=br.resource_id,
            failure_type="scene",
            error=br.error or "unknown",
            attempts=3,
        )
        print(f"❌ 分鏡圖生成: {br.resource_id} 失敗 - {br.error}")

    successes, failures = batch_enqueue_and_wait_sync(
        project_name=project_name,
        specs=specs,
        on_success=on_success,
        on_failure=on_failure,
    )
    recorder.save()

    ordered_results = _collect_ordered_paths(successes, dependency_plans, project_dir)
    failure_tuples = [(f.resource_id, f.error or "unknown") for f in failures]
    return ordered_results, failure_tuples


def main():
    parser = argparse.ArgumentParser(description="生成分鏡圖")
    parser.add_argument("script", help="劇本檔名")

    # 輔助引數
    parser.add_argument("--scene", help="指定單個場景 ID（單場景模式）")
    parser.add_argument("--scene-ids", nargs="+", help="指定場景 ID")
    parser.add_argument("--segment-ids", nargs="+", help="指定片段 ID（narration 模式別名）")

    args = parser.parse_args()

    try:
        # 檢測 content_mode
        pm, project_name = ProjectManager.from_cwd()
        script = pm.load_script(project_name, args.script)
        content_mode = script.get("content_mode", "narration")

        print(f"🚀 {content_mode} 模式：透過佇列生成分鏡圖")

        # 合併 --scene-ids 和 --segment-ids 引數
        if args.scene:
            segment_ids = [args.scene]
        else:
            segment_ids = args.segment_ids or args.scene_ids

        results, failed = generate_storyboard_direct(
            args.script,
            segment_ids=segment_ids,
        )
        print(f"\n📊 生成完成: {len(results)} 個分鏡圖")
        if failed:
            print(f"⚠️  失敗: {len(failed)} 個")

    except Exception as e:
        print(f"❌ 錯誤: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
