"""
entity_reconciler.py — 生成後的關聯欄位補齊（deterministic）

AI 生成劇本時常在正文（novel_text / image_prompt.scene / video_prompt.action）
寫到角色／道具／場景，卻沒同步填進結構欄位（characters_in_segment 等）。
本模組在劇本儲存時掃描正文，用 project.json 已知名稱補齊缺漏的關聯。

設計約束（見 docs/superpowers/specs/2026-05-19-entity-association-reconciler-design.md）：
  - 純函式、immutable：回傳新 dict，不 mutate 入參
  - union 語意：characters/clues 只新增缺漏，絕不移除 AI 已填的
  - scene_in_*：僅在現值為空時才補（尊重 AI／人工判斷）
  - 補齊失敗不應阻擋存檔（由 caller 以 try/except 包覆）
"""

from __future__ import annotations

from typing import Any

from lib.entity_matching import AliasEntries, build_sorted_entries, scan_with_entries

# narration 用 *_in_segment，drama 用 *_in_scene
_FIELDS_NARRATION = ("characters_in_segment", "clues_in_segment", "scene_in_segment")
_FIELDS_DRAMA = ("characters_in_scene", "clues_in_scene", "scene_in_scene")

# 掃描的正文欄位（image_prompt / video_prompt 為巢狀 dict）
_TEXT_PATHS = (
    ("novel_text",),
    ("image_prompt", "scene"),
    ("video_prompt", "action"),
)


def _collect_text(item: dict[str, Any]) -> str:
    """把一個 segment/scene 的三處正文串成一段供掃描。"""
    parts: list[str] = []
    for path in _TEXT_PATHS:
        node: Any = item
        for key in path:
            if not isinstance(node, dict):
                node = None
                break
            node = node.get(key)
        if isinstance(node, str) and node:
            parts.append(node)
    return "\n".join(parts)


def _union_keep_order(existing: Any, additions: list[str]) -> list[str]:
    """union：保留原有順序，只追加尚未存在的新項。原有非 list 時視為空。"""
    result: list[str] = [v for v in existing if isinstance(v, str)] if isinstance(existing, list) else []
    seen = set(result)
    for name in additions:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def reconcile_item(
    item: dict[str, Any],
    entries: AliasEntries,
    *,
    fields: tuple[str, str, str],
) -> dict[str, Any]:
    """補齊單一 segment/scene 的關聯欄位，回傳新 dict（不 mutate 入參）。

    Args:
        item: segment（narration）或 scene（drama）dict
        entries: build_sorted_entries 預建的排序條目表（整份 script 共用一份）
        fields: (chars_field, clues_field, scene_field) 欄位名三元組
    """
    chars_field, clues_field, scene_field = fields
    # 只改三個頂層欄位、巢狀內容只讀，故淺拷貝即可保證不 mutate 入參；
    # 避免與 reconcile_script 的整份 deepcopy 疊成每個 item 雙重深拷貝。
    result = dict(item)

    text = _collect_text(result)
    if not text:
        return result

    found = scan_with_entries(text, entries)

    result[chars_field] = _union_keep_order(result.get(chars_field), found.character_names)
    result[clues_field] = _union_keep_order(result.get(clues_field), found.clue_names)

    # scene 單值：僅在現值為空時補（尊重 AI／人工已填）
    current_scene = result.get(scene_field)
    if not current_scene and found.scene_name:
        result[scene_field] = found.scene_name

    return result


def reconcile_script(script: dict[str, Any], project_json: dict[str, Any]) -> dict[str, Any]:
    """補齊整份劇本的關聯欄位，回傳新 script dict（不 mutate 入參）。

    narration → segments + *_in_segment；drama → scenes + *_in_scene。
    project.json 無實體或結構不符時等同 no-op（回傳結構等價的新 dict）。
    """
    # 僅重新賦值 result[items_key]，list 內每個 item 由 reconcile_item 各自淺拷貝；
    # 整份淺拷貝即足以不 mutate 入參，不需深拷貝。
    result = dict(script)

    characters = project_json.get("characters") if isinstance(project_json, dict) else None
    clues = project_json.get("clues") if isinstance(project_json, dict) else None
    scenes = project_json.get("scenes") if isinstance(project_json, dict) else None
    if not isinstance(characters, dict):
        characters = None
    if not isinstance(clues, dict):
        clues = None
    if not isinstance(scenes, dict):
        scenes = None

    content_mode = result.get("content_mode", "narration")
    if content_mode == "narration":
        items_key, fields = "segments", _FIELDS_NARRATION
    else:
        items_key, fields = "scenes", _FIELDS_DRAMA

    items = result.get(items_key)
    if not isinstance(items, list):
        return result

    # 整份 script 的實體相同，條目表只建一次（避免每 segment 重跑 regex 與排序）
    entries = build_sorted_entries(characters, clues, scenes)
    result[items_key] = [
        reconcile_item(item, entries, fields=fields) if isinstance(item, dict) else item for item in items
    ]
    return result
