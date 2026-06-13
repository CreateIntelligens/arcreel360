"""resource_rename.py — 角色 / 道具 / 場景改名（含檔案、版本、劇本引用）

設計目標：
- **原子性**：失敗時 rollback 已搬移的檔案，不留中途狀態
- **完整性**：除了 project.json，所有引用點都要更新（劇本陣列、dialogue.speaker、versions.json、檔案路徑欄位）
- 不直接觸碰 DB；專案資料是檔案系統 + project.json
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

ResourceKind = Literal["character", "clue", "scene"]

_BUCKET_BY_KIND: dict[ResourceKind, str] = {
    "character": "characters",
    "clue": "clues",
    "scene": "scenes",
}
_FOLDER_BY_KIND: dict[ResourceKind, str] = {
    "character": "characters",
    "clue": "clues",
    "scene": "scenes",
}
_SHEET_KEY_BY_KIND: dict[ResourceKind, str] = {
    "character": "character_sheet",
    "clue": "clue_sheet",
    "scene": "scene_sheet",
}
_REF_FIELD_BY_KIND: dict[ResourceKind, tuple[str, str]] = {
    "character": ("reference_image", "characters/refs"),
    "clue": ("reference_image", "clues/refs"),
    "scene": ("scene_ref", "scenes/refs"),
}
_LIST_REFERENCE_KEYS_BY_KIND: dict[ResourceKind, list[str]] = {
    "character": ["characters_in_segment", "characters_in_scene"],
    "clue": ["clues_in_segment", "clues_in_scene"],
    "scene": [],
}
_SCALAR_REFERENCE_KEYS_BY_KIND: dict[ResourceKind, list[str]] = {
    "character": [],
    "clue": [],
    "scene": ["scene_in_segment", "scene_in_scene"],
}

# 不允許的檔名字元（路徑分隔、保留字元、控制字元）
_INVALID_NAME_RE = re.compile(r'[/\\:\*\?"<>\|\x00-\x1f]')


def _validate_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("名稱不可為空")
    if _INVALID_NAME_RE.search(name):
        raise ValueError('名稱包含非法字元（不可有 / \\ : * ? " < > | 或控制字元）')
    if name in (".", ".."):
        raise ValueError("名稱不可為 . 或 ..")
    if len(name) > 64:
        raise ValueError("名稱過長（最多 64 字元）")
    return name


@dataclass
class _Move:
    """單筆檔案搬移記錄，rollback 用。"""

    src: Path
    dst: Path


@dataclass
class RenameResult:
    files_moved: int
    scripts_updated: int
    versions_updated: int


def rename_resource(
    project_path: Path,
    project: dict,
    kind: ResourceKind,
    old_name: str,
    new_name: str,
) -> RenameResult:
    """改名一個角色、道具或場景。**會直接修改傳入的 project dict**，呼叫者負責 save。

    步驟：
    1. 校驗 new_name 合法 + 不衝突
    2. 收集所有要搬移的檔案（設計圖、reference image、版本歷史）
    3. 預先計算所有目標路徑，檢查衝突
    4. 執行搬移（記錄已搬，失敗時 rollback）
    5. 更新 project.json 的 dict key + 路徑欄位
    6. 更新 versions.json 的字串列表
    7. 掃 scripts/*.json 替換引用
    """
    new_name = _validate_name(new_name)
    if new_name == old_name:
        return RenameResult(0, 0, 0)

    bucket = _BUCKET_BY_KIND[kind]
    if old_name not in project.get(bucket, {}):
        raise KeyError(f"{bucket}: {old_name} 不存在")
    if new_name in project.get(bucket, {}):
        raise ValueError(f"{bucket} 中已存在「{new_name}」")

    moves = _plan_moves(project_path, kind, old_name, new_name)

    # 檢查目標檔案不存在（避免覆蓋）
    for mv in moves:
        if mv.dst.exists():
            raise ValueError(f"目標檔案已存在，無法搬移：{mv.dst.relative_to(project_path)}")

    # 執行搬移（出錯 rollback）
    completed: list[_Move] = []
    try:
        for mv in moves:
            mv.dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(mv.src), str(mv.dst))
            completed.append(mv)
    except Exception:
        # rollback
        for mv in reversed(completed):
            try:
                shutil.move(str(mv.dst), str(mv.src))
            except Exception:
                logger.exception("rollback 失敗：%s -> %s", mv.dst, mv.src)
        raise

    # 更新 project dict（原地）
    bucket_dict = project[bucket]
    entry = bucket_dict.pop(old_name)
    sheet_key = _SHEET_KEY_BY_KIND[kind]
    folder = _FOLDER_BY_KIND[kind]

    # 更新內部路徑欄位
    if entry.get(sheet_key):
        entry[sheet_key] = _rename_owned_file_path(
            entry[sheet_key],
            folder=folder,
            old_name=old_name,
            new_name=new_name,
            include_versions=True,
        )

    ref_field, ref_folder = _REF_FIELD_BY_KIND[kind]
    if entry.get(ref_field):
        entry[ref_field] = _rename_owned_file_path(
            entry[ref_field],
            folder=ref_folder,
            old_name=old_name,
            new_name=new_name,
        )

    bucket_dict[new_name] = entry

    # 更新 versions.json（字串列表）
    versions_updated = _update_versions_json(project_path, kind, old_name, new_name)

    # 更新所有 scripts/*.json 引用
    scripts_updated = _update_scripts(project_path, kind, old_name, new_name)

    return RenameResult(
        files_moved=len(completed),
        scripts_updated=scripts_updated,
        versions_updated=versions_updated,
    )


def _plan_moves(project_path: Path, kind: ResourceKind, old_name: str, new_name: str) -> list[_Move]:
    moves: list[_Move] = []
    folder = _FOLDER_BY_KIND[kind]

    # 1. 主設計圖 {folder}/{name}.{ext}
    main_dir = project_path / folder
    if main_dir.exists():
        for f in main_dir.glob(f"{old_name}.*"):
            if f.is_file():
                moves.append(_Move(f, main_dir / f"{new_name}{f.suffix}"))

    # 2. reference 圖 {folder}/refs/{name}.{ext}
    _, ref_folder = _REF_FIELD_BY_KIND[kind]
    refs_dir = project_path / ref_folder
    if refs_dir.exists():
        for f in refs_dir.glob(f"{old_name}.*"):
            if f.is_file():
                moves.append(_Move(f, refs_dir / f"{new_name}{f.suffix}"))

    # 3. 版本歷史 versions/{folder}/{old_name}_v*.{ext}
    versions_dir = project_path / "versions" / folder
    if versions_dir.exists():
        for f in versions_dir.glob(f"{old_name}_v*"):
            if f.is_file():
                # 只替換開頭的 old_name，保留 _v123_timestamp.ext 部分
                new_filename = new_name + f.name[len(old_name) :]
                moves.append(_Move(f, versions_dir / new_filename))

    return moves


def _rename_owned_file_path(
    path: str,
    *,
    folder: str,
    old_name: str,
    new_name: str,
    include_versions: bool = False,
) -> str:
    """Rename resource-owned relative paths without touching similarly prefixed names."""
    candidates = [(f"{folder}/", (".",))]
    if include_versions:
        candidates.append((f"versions/{folder}/", ("_v",)))

    for prefix, allowed_suffixes in candidates:
        old_prefix = f"{prefix}{old_name}"
        if not path.startswith(old_prefix):
            continue
        suffix = path[len(old_prefix) :]
        if suffix.startswith(allowed_suffixes):
            return f"{prefix}{new_name}{suffix}"
    return path


def _update_versions_json(project_path: Path, kind: ResourceKind, old_name: str, new_name: str) -> int:
    versions_file = project_path / "versions" / "versions.json"
    if not versions_file.exists():
        return 0

    try:
        data = json.loads(versions_file.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("versions.json 解析失敗，跳過")
        return 0

    bucket = _BUCKET_BY_KIND[kind]
    items = data.get(bucket, [])

    updated = 0
    if isinstance(items, list):
        for i, item in enumerate(items):
            if item == old_name:
                items[i] = new_name
                updated += 1
    elif isinstance(items, dict):
        if old_name in items:
            items[new_name] = items.pop(old_name)
            updated += 1

        resource_data = items.get(new_name)
        if isinstance(resource_data, dict):
            folder = _FOLDER_BY_KIND[kind]
            for version in resource_data.get("versions", []):
                if not isinstance(version, dict) or not isinstance(version.get("file"), str):
                    continue
                new_file = _rename_owned_file_path(
                    version["file"],
                    folder=folder,
                    old_name=old_name,
                    new_name=new_name,
                    include_versions=True,
                )
                if new_file != version["file"]:
                    version["file"] = new_file
                    updated += 1
    else:
        return 0

    if updated:
        versions_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return updated


def _update_scripts(project_path: Path, kind: ResourceKind, old_name: str, new_name: str) -> int:
    scripts_dir = project_path / "scripts"
    if not scripts_dir.exists():
        return 0

    list_keys = _LIST_REFERENCE_KEYS_BY_KIND[kind]
    scalar_keys = _SCALAR_REFERENCE_KEYS_BY_KIND[kind]

    updated_files = 0
    for script_file in scripts_dir.glob("*.json"):
        try:
            script = json.loads(script_file.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("跳過解析失敗的劇本: %s", script_file.name)
            continue

        changed = False
        # narration: segments / drama: scenes
        items = script.get("segments") or script.get("scenes") or []
        for item in items:
            for key in list_keys:
                arr = item.get(key)
                if isinstance(arr, list):
                    new_arr = [new_name if x == old_name else x for x in arr]
                    if new_arr != arr:
                        item[key] = new_arr
                        changed = True

            for key in scalar_keys:
                if item.get(key) == old_name:
                    item[key] = new_name
                    changed = True

            # dialogue.speaker（只有 character 改名才需要）
            if kind == "character":
                vp = item.get("video_prompt")
                if isinstance(vp, dict):
                    dialogue = vp.get("dialogue")
                    if isinstance(dialogue, list):
                        for d in dialogue:
                            if isinstance(d, dict) and d.get("speaker") == old_name:
                                d["speaker"] = new_name
                                changed = True

        if changed:
            script_file.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
            updated_files += 1

    return updated_files
