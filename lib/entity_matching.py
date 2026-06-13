"""
entity_matching.py — 實體名稱比對（前後端共用規格的 Python 實作）

用途：在一段文字中掃描已知的角色 / 線索 / 場景名稱，回傳命中的原始 key。
比對方式為 longest-first、非重疊的裸文掃描（不需要 @ 前綴）。

名稱來源為 project.json 的 characters / clues / scenes 的 key；
若 key 形如「中文 (English)」會自動拆解為三個比對詞（完整 key、中文、英文）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

EntityKind = Literal["character", "clue", "scene"]

# 匹配 "中文 (English)" 或 "中文（English）" — 全半形括號皆可
_ALIAS_PATTERN = re.compile(r"^(.+?)\s*[（(]\s*(.+?)\s*[）)]\s*$")

# 判斷是否為純 ASCII word 字元（用於邊界檢查）
_ASCII_WORD_RE = re.compile(r"^[A-Za-z0-9_]+$")
_ASCII_WORD_CHAR_RE = re.compile(r"[A-Za-z0-9_]")


@dataclass
class EntityMentionNames:
    """比對結果：各組命中的原始 key 列表。"""

    character_names: list[str] = field(default_factory=list)
    clue_names: list[str] = field(default_factory=list)
    scene_name: str | None = None


def expand_entity_aliases(name: str) -> list[str]:
    """將 project.json key 拆解為比對詞列表。

    規則：
      - 正則 ``^(.+?)\\s*[（(]\\s*(.+?)\\s*[）)]\\s*$``
      - 匹配 → ``[full_key, group1.strip(), group2.strip()]``，去重
      - 不匹配 → ``[name.strip()]``

    所有產出皆去前後空白。
    """
    trimmed = name.strip()
    if not trimmed:
        return []

    m = _ALIAS_PATTERN.match(trimmed)
    if not m:
        return [trimmed]

    parts: list[str] = [trimmed, m.group(1).strip(), m.group(2).strip()]
    # 去重並保持順序
    seen: set[str] = set()
    result: list[str] = []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            result.append(p)
    return result


# ---------------------------------------------------------------------------
# 內部結構
# ---------------------------------------------------------------------------

_KIND_PRIORITY: dict[EntityKind, int] = {"character": 0, "clue": 1, "scene": 2}


@dataclass
class _AliasEntry:
    """一個比對詞條目。"""

    alias: str
    original_key: str
    kind: EntityKind


def _is_ascii_word(name: str) -> bool:
    return bool(_ASCII_WORD_RE.match(name))


def _is_ascii_word_char(ch: str | None) -> bool:
    if ch is None:
        return False
    return bool(_ASCII_WORD_CHAR_RE.match(ch))


def _check_boundary(text: str, start: int, length: int, alias: str) -> bool:
    """ASCII 名稱需做 word boundary 檢查，CJK 不需要。"""
    if not _is_ascii_word(alias):
        return True
    # 前面不能是 ASCII word char
    if start > 0 and _is_ascii_word_char(text[start - 1]):
        return False
    # 後面不能是 ASCII word char
    end = start + length
    if end < len(text) and _is_ascii_word_char(text[end]):
        return False
    return True


def _build_entries(
    names: dict[str, Any] | None,
    kind: EntityKind,
) -> list[_AliasEntry]:
    """為一組實體名稱建立 alias 條目。"""
    if not names:
        return []
    entries: list[_AliasEntry] = []
    for key in names:
        for alias in expand_entity_aliases(key):
            entries.append(_AliasEntry(alias=alias, original_key=key, kind=kind))
    return entries


def build_sorted_entries(
    characters: dict[str, Any] | None = None,
    clues: dict[str, Any] | None = None,
    scenes: dict[str, Any] | None = None,
) -> list[_AliasEntry]:
    """展開三組實體別名，去重後依（長度降序、kind 優先序）排序。

    抽出此步驟讓 reconciler 對整份 script 只建一次條目表（見
    reconcile_script），避免每個 segment 重跑 regex 與排序。
    """
    all_entries = (
        _build_entries(characters, "character") + _build_entries(clues, "clue") + _build_entries(scenes, "scene")
    )

    # 以 alias 去重：同一 alias 只保留優先序最高的條目
    seen_aliases: dict[str, _AliasEntry] = {}
    for entry in all_entries:
        existing = seen_aliases.get(entry.alias)
        if existing is None or _KIND_PRIORITY[entry.kind] < _KIND_PRIORITY[existing.kind]:
            seen_aliases[entry.alias] = entry

    return sorted(
        seen_aliases.values(),
        key=lambda e: (-len(e.alias), _KIND_PRIORITY[e.kind]),
    )


# reconciler 把建好的條目表當不透明值在 segment 間傳遞，不需知道內部結構
AliasEntries = list[_AliasEntry]


def scan_with_entries(text: str, sorted_entries: AliasEntries) -> EntityMentionNames:
    """以預建的排序條目表掃描文字（longest-first、非重疊）。

    逐字元掃描，命中最長比對詞 → 記錄 originalKey、游標跳過命中長度；
    未命中 → 游標 +1。
    """
    found_characters: set[str] = set()
    found_clues: set[str] = set()
    found_scenes: set[str] = set()

    i = 0
    text_len = len(text)
    while i < text_len:
        matched = False
        for entry in sorted_entries:
            alias_len = len(entry.alias)
            if i + alias_len > text_len:
                continue
            if text[i : i + alias_len] == entry.alias and _check_boundary(text, i, alias_len, entry.alias):
                if entry.kind == "character":
                    found_characters.add(entry.original_key)
                elif entry.kind == "clue":
                    found_clues.add(entry.original_key)
                else:
                    found_scenes.add(entry.original_key)
                i += alias_len
                matched = True
                break
        if not matched:
            i += 1

    return EntityMentionNames(
        character_names=sorted(found_characters),
        clue_names=sorted(found_clues),
        scene_name=sorted(found_scenes)[0] if found_scenes else None,
    )


def scan_entity_mentions(
    text: str,
    characters: dict[str, Any] | None = None,
    clues: dict[str, Any] | None = None,
    scenes: dict[str, Any] | None = None,
) -> EntityMentionNames:
    """單次掃描的便利包裝：建表 + 掃描。

    每次呼叫重建條目表；批次場景（同一份 script 多 segment）應改用
    build_sorted_entries + scan_with_entries 只建一次表。
    """
    return scan_with_entries(text, build_sorted_entries(characters, clues, scenes))
