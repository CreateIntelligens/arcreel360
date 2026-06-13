"""
Helpers for storyboard sequence ordering and dependency planning.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

_STORYBOARD_ID_PATTERN = re.compile(r"^E(\d+)S(\d+)(?:_(\d+))?$")


def normalize_storyboard_id(raw: object) -> tuple:
    """將 segment/scene id 正規化為可比對的標準形。

    補零與否視為同一個 id：``E2S1`` 與 ``E2S01`` 正規化後相等，
    避免不同來源（LLM 生成、前端、規範）的補零差異造成比對斷裂。

    不符 ``E{n}S{seq}(_{sub})?`` 格式者退化為原字串比較，不拋例外。
    """
    text = str(raw).strip()
    match = _STORYBOARD_ID_PATTERN.match(text)
    if not match:
        return ("raw", text)
    episode, seq, sub = match.groups()
    return ("ES", int(episode), int(seq), int(sub) if sub is not None else None)


@dataclass(frozen=True)
class StoryboardTaskPlan:
    resource_id: str
    script_file: str | None
    dependency_resource_id: str | None
    dependency_group: str
    dependency_index: int


PREVIOUS_STORYBOARD_REFERENCE_LABEL = "上一分鏡圖（鏡頭銜接參考）"
PREVIOUS_STORYBOARD_REFERENCE_DESCRIPTION = (
    "僅用於延續前一鏡頭的構圖、色調和場景連續性，不是新增角色、服裝或道具設定；請以當前 prompt 為準生成當前鏡頭。"
)


def get_storyboard_items(script: dict) -> tuple[list[dict], str, str, str, str]:
    content_mode = script.get("content_mode", "narration")
    if content_mode == "narration" and "segments" in script:
        return (
            list(script.get("segments", [])),
            "segment_id",
            "characters_in_segment",
            "clues_in_segment",
            "scene_in_segment",
        )
    return (
        list(script.get("scenes", [])),
        "scene_id",
        "characters_in_scene",
        "clues_in_scene",
        "scene_in_scene",
    )


def find_storyboard_item(
    items: Sequence[dict],
    id_field: str,
    resource_id: str,
) -> tuple[dict, int] | None:
    target = normalize_storyboard_id(resource_id)
    for index, item in enumerate(items):
        if normalize_storyboard_id(item.get(id_field)) == target:
            return item, index
    return None


def resolve_previous_storyboard_path(
    project_path: Path,
    items: Sequence[dict],
    id_field: str,
    resource_id: str,
) -> Path | None:
    resolved = find_storyboard_item(items, id_field, resource_id)
    if resolved is None:
        raise KeyError(f"scene/segment not found: {resource_id}")

    target_item, index = resolved
    if index == 0 or bool(target_item.get("segment_break")):
        return None

    previous_item = items[index - 1]
    previous_id = str(previous_item.get(id_field) or "").strip()
    if not previous_id:
        return None

    previous_path = project_path / "storyboards" / f"scene_{previous_id}.png"
    if previous_path.exists():
        return previous_path
    return None


def build_previous_storyboard_reference(path: Path) -> dict:
    return {
        "image": path,
        "label": PREVIOUS_STORYBOARD_REFERENCE_LABEL,
        "description": PREVIOUS_STORYBOARD_REFERENCE_DESCRIPTION,
    }


def build_storyboard_dependency_plan(
    items: Sequence[dict],
    id_field: str,
    selected_ids: Iterable[str],
    script_file: str | None,
) -> list[StoryboardTaskPlan]:
    selected_set = {str(item_id) for item_id in selected_ids}
    if not selected_set:
        return []

    plans: list[StoryboardTaskPlan] = []
    group_counter = 0
    current_group = ""
    current_group_index = 0

    for index, item in enumerate(items):
        resource_id = str(item.get(id_field) or "").strip()
        if not resource_id or resource_id not in selected_set:
            continue

        previous_resource_id: str | None = None
        if index > 0:
            previous_resource_id = str(items[index - 1].get(id_field) or "").strip() or None

        starts_new_group = (
            bool(item.get("segment_break")) or not previous_resource_id or previous_resource_id not in selected_set
        )

        if starts_new_group:
            group_counter += 1
            current_group = f"{script_file or 'storyboard'}:group:{group_counter}"
            current_group_index = 0
            dependency_resource_id = None
        else:
            current_group_index += 1
            dependency_resource_id = previous_resource_id

        plans.append(
            StoryboardTaskPlan(
                resource_id=resource_id,
                script_file=script_file,
                dependency_resource_id=dependency_resource_id,
                dependency_group=current_group,
                dependency_index=current_group_index,
            )
        )

    return plans
