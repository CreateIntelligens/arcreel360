import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DraftMode:
    filename: str
    id_header_aliases: set[str]
    segment_field: str
    script_items_key: str
    item_id_key: str
    # content（主文）欄的表頭別名；用於依表頭名稱定位該欄，而非寫死索引。
    content_header_aliases: set[str]
    # 旁白／配音欄的表頭別名；對應劇本片段的 narration_field（無此欄時為 None）。
    # 含新版「旁白」與舊版「旁白/台詞」，向後相容既有草稿。
    narration_header_aliases: set[str] = frozenset()  # type: ignore[assignment]
    # 旁白／配音內容回填到劇本片段的欄位名（narration 模式無獨立旁白欄）。
    narration_field: str | None = None


DRAFT_MODES = {
    "narration": DraftMode(
        filename="step1_segments.md",
        id_header_aliases={"片段", "片段 ID", "片段ID", "ID"},
        segment_field="novel_text",
        script_items_key="segments",
        item_id_key="segment_id",
        content_header_aliases={"原文"},
    ),
    "drama": DraftMode(
        filename="step1_normalized_script.md",
        id_header_aliases={"場景 ID", "場景ID", "ID"},
        segment_field="scene_description",
        script_items_key="scenes",
        item_id_key="scene_id",
        content_header_aliases={"場景描述"},
        narration_header_aliases={"旁白", "旁白/台詞", "旁白／台詞", "台詞"},
        narration_field="narration_text",
    ),
}

# 表頭欄位（任一模式）會出現的 ID 欄標題；用於略過表頭列。
_HEADER_ID_LABELS = {"片段", "場景 ID", "片段 ID", "場景ID", "片段ID", "ID"}

# 表頭名稱 → 角色（content / narration）的映射，跨所有模式；解析時用於依名稱定位欄位。
_HEADER_ROLES: dict[str, str] = {
    **{h: "content" for mode in DRAFT_MODES.values() for h in mode.content_header_aliases},
    **{h: "narration" for mode in DRAFT_MODES.values() for h in mode.narration_header_aliases},
}


def _split_cells(line: str) -> list[str]:
    """切分 Markdown 表格列為 cell 字串，尊重 `\\|` 跳脫。

    回傳含首尾空字串的 raw split（與 ``str.split("|")`` 對齊），呼叫端依需要取用。
    跳脫的 ``\\|`` 會被保留為字面 ``|``（已還原）。
    """
    cells: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == "\\" and i + 1 < n and line[i + 1] == "|":
            buf.append("|")
            i += 2
            continue
        if ch == "|":
            cells.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    cells.append("".join(buf))
    return cells


def _escape_cell(text: str) -> str:
    """把 cell 內容寫回表格前，將字面 ``|`` 跳脫為 ``\\|``。"""
    return text.replace("|", "\\|")


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and "---" not in stripped


def _data_cells(line: str) -> list[str]:
    """切出一列的純資料 cells（去掉外側 ``|`` 兩端的空字串），未 strip 前後空白。"""
    raw = _split_cells(line.strip())
    # _split_cells("| a | b |") -> ["", " a ", " b ", ""]；去首尾外側空欄。
    if raw and raw[0].strip() == "":
        raw = raw[1:]
    if raw and raw[-1].strip() == "":
        raw = raw[:-1]
    return raw


def _header_cells(md: str) -> list[str] | None:
    """找出表頭列並回傳其 strip 後的欄名（不含 ``---`` 分隔列）。找不到則回 None。"""
    for line in md.splitlines():
        if not _is_table_row(line):
            continue
        cells = [c.strip() for c in _data_cells(line)]
        if cells and cells[0] in _HEADER_ID_LABELS:
            return cells
    return None


def _locate_columns(headers: list[str] | None) -> tuple[int, int | None]:
    """依表頭名稱定位 ``(content_idx, narration_idx)``（0-based，相對純資料 cells）。

    找不到表頭或對應欄時：content 退回 index 1（id 之後第一欄，相容舊格式），narration 為 None。
    """
    if not headers:
        return 1, None
    content_idx = 1
    narration_idx: int | None = None
    for i, name in enumerate(headers):
        role = _HEADER_ROLES.get(name)
        if role == "content":
            content_idx = i
        elif role == "narration":
            narration_idx = i
    return content_idx, narration_idx


def parse_draft_table(md: str) -> list[dict]:
    """解析 step1 草稿表格（依表頭名稱定位欄位，避免欄序變動造成錯位）。

    回傳每列 ``{"id", "content", "narration", "raw_cells"}``：
    - ``id`` / ``content`` / ``narration`` 已還原跳脫，供讀取端直接使用。
    - ``content`` 取自表頭「原文」（narration）或「場景描述」（drama）欄；找不到表頭時退回 id 之後第一欄。
    - ``narration`` 取自「旁白」（新版）或「旁白/台詞」（舊版）欄，無此欄時為空字串。
    - ``raw_cells`` 為「id 與 content 以外」的其餘資料欄，供 round-trip 重建時保留。
    """
    headers = _header_cells(md)
    content_idx, narration_idx = _locate_columns(headers)

    def _cell(parts: list[str], idx: int | None) -> str:
        return parts[idx] if idx is not None and idx < len(parts) else ""

    rows = []
    for line in md.splitlines():
        if not _is_table_row(line):
            continue
        parts = [p.strip() for p in _data_cells(line)]
        if len(parts) < 2:
            continue
        id_val = parts[0]
        if id_val in _HEADER_ID_LABELS:
            continue
        content = _cell(parts, content_idx)
        narration = _cell(parts, narration_idx)
        raw_cells = [c for i, c in enumerate(parts) if i not in (0, content_idx)]
        rows.append({"id": id_val, "content": content, "narration": narration, "raw_cells": raw_cells})
    return rows


def render_draft_table(rows: list[dict], mode_name: str) -> str:
    """從 parsed rows 重建表格，欄序為 id → content → raw_cells（僅供 narration round-trip）。

    各 cell 內的 ``|`` 會重新跳脫。narration 採標準表頭（片段 ID|原文|字數|時長|有對話|segment_break）。
    **drama 的 content 欄原本不在第二欄，raw_cells 已不含 content，無法忠實重建欄序與表頭**，
    故 drama 需精確 round-trip 時請改走 ``sync_segment_to_draft`` 在原始 markdown 上行內覆寫，勿用本函式。
    """
    is_drama = mode_name == "drama"
    id_header = "場景 ID" if is_drama else "片段 ID"
    content_header = "場景描述" if is_drama else "原文"
    # raw_cells 的標準表頭（content 已抽出）。drama 無法對齊既有欄名，以空表頭佔位（見 docstring 警告）。
    raw_headers = [] if is_drama else ["字數", "時長", "有對話", "segment_break"]

    max_extra = max((len(row.get("raw_cells", [])) for row in rows), default=0)
    extra_headers = (raw_headers + [""] * max_extra)[:max_extra]
    out_headers = [id_header, content_header, *extra_headers]
    lines = [
        "| " + " | ".join(out_headers) + " |",
        "| " + " | ".join(["---"] * len(out_headers)) + " |",
    ]
    for row in rows:
        cells = [_escape_cell(c) for c in (row["id"], row["content"], *row.get("raw_cells", []))]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _normalize_id(item_id: str) -> str:
    """Normalize ID to sequence number for matching.
    E.g. E1S02 -> 02, G02 -> 02, E1S02_1 -> 02_1
    """
    if not item_id:
        return ""
    if "S" in item_id:
        parts = item_id.split("S", 1)
        return parts[1]
    if item_id.startswith("G"):
        return item_id[1:]
    return item_id


def sync_segment_to_draft(project_path: Path, episode: int, segment_id: str, new_content: str, mode_name: str) -> bool:
    """精準覆蓋草稿表格中指定 segment 的 content 欄，其餘列與欄位逐字保留。

    直接在原始 markdown 上做行內替換，不重建整張表，避免任何 schema 漂移。
    回傳是否確實命中並更新了該 segment（檔案不存在、找不到 id 或寫入失敗皆回傳 False）。
    """
    mode = DRAFT_MODES[mode_name]
    draft_dir = project_path / "drafts" / f"episode_{episode}"
    draft_file = draft_dir / mode.filename
    if not draft_file.exists():
        return False

    try:
        md = draft_file.read_text(encoding="utf-8")
        # 依表頭名稱定位 content 欄（純資料 cells 的 0-based 索引）。
        content_idx, _ = _locate_columns(_header_cells(md))
        # _split_cells 結果含外側空欄（cells[0]=""），故含外側偏移後 id 在 1、content 在 content_idx + 1。
        id_cell = 1
        content_cell = content_idx + 1

        normalized_segment_id = _normalize_id(segment_id) if mode_name == "narration" else segment_id

        out_lines: list[str] = []
        updated = False
        for line in md.splitlines():
            if not updated and _is_table_row(line):
                cells = _split_cells(line)
                # cells: ["", id, ...欄..., ""]（首尾為外側 | 兩端的空字串）
                if len(cells) > content_cell:
                    match_id = cells[id_cell].strip()
                    normalized_match_id = _normalize_id(match_id) if mode_name == "narration" else match_id
                    if normalized_match_id == normalized_segment_id:
                        # 保留 content cell 原有的前後空白排版。
                        original = cells[content_cell]
                        lstripped = original.lstrip()
                        lead = original[: len(original) - len(lstripped)]
                        trail = lstripped[len(lstripped.rstrip()) :]
                        cells[content_cell] = f"{lead}{_escape_cell(new_content)}{trail}"
                        line = "|".join(cells)
                        updated = True
            out_lines.append(line)

        if updated:
            new_md = "\n".join(out_lines)
            if md.endswith("\n") and not new_md.endswith("\n"):
                new_md += "\n"
            draft_file.write_text(new_md, encoding="utf-8")
        return updated
    except Exception as e:
        logger.error(f"Sync segment to draft failed: {e}", exc_info=True)
        return False


def apply_draft_rows_to_items(rows: list[dict], items, mode: DraftMode, *, only_if_empty: bool = False) -> int:
    """把已解析的草稿 rows 依 id 回填到劇本片段／場景的對應欄位（content→segment_field、narration→narration_field）。

    ``items`` 可為 list 或 dict（scenes 兩種儲存形態皆支援）。欄位映射由 ``DraftMode`` 提供，避免硬編欄名。
    ``only_if_empty=True`` 時僅在目標欄位為空才回填（供生成後回填、不覆蓋模型輸出）；否則內容不同即覆蓋。
    回傳實際變更的欄位數。
    """
    is_narration = mode.segment_field == "novel_text"

    def get_val_map(field_key: str) -> dict[str, str]:
        val_map = {}
        for r in rows:
            r_id = r["id"]
            key = _normalize_id(r_id) if is_narration else r_id
            val_map[key] = r[field_key]
        return val_map

    field_maps: list[tuple[str, dict[str, str]]] = [(mode.segment_field, get_val_map("content"))]
    if mode.narration_field:
        field_maps.append((mode.narration_field, get_val_map("narration")))

    def _apply(iid: str, item: dict) -> int:
        changed = 0
        normalized_iid = _normalize_id(iid) if is_narration else iid
        for field, value_map in field_maps:
            if normalized_iid not in value_map:
                continue
            new_value = value_map[normalized_iid]
            current = item.get(field)
            if only_if_empty:
                if not current and new_value:
                    item[field] = new_value
                    changed += 1
            elif current != new_value:
                item[field] = new_value
                changed += 1
        return changed

    changed_total = 0
    if isinstance(items, list):
        for item in items:
            changed_total += _apply(item.get(mode.item_id_key), item)
    elif isinstance(items, dict):
        for iid, item in items.items():
            changed_total += _apply(iid, item)
    return changed_total


def sync_draft_to_segments(project_path: Path, episode: int, new_md: str, mode_name: str, manager) -> int:
    mode = DRAFT_MODES[mode_name]
    rows = parse_draft_table(new_md)
    script_filename = f"episode_{episode}.json"

    try:
        script = manager.load_script(project_path.name, script_filename)
    except FileNotFoundError:
        return 0

    items = script.get(mode.script_items_key, [])
    if not items:
        items = script.get("scenes", {})

    updated_count = apply_draft_rows_to_items(rows, items, mode)
    if updated_count > 0:
        manager.save_script(project_path.name, script, script_filename)

    return updated_count


def sync_script_to_draft_file(project_path: Path, episode: int, content_mode: str, manager) -> bool:
    """Read the script JSON file and write its segments/scenes back to the Step 1 markdown file.
    This ensures structural edits (additions, deletions, reorderings) are reflected in the draft markdown,
    preventing LLM generation from overwriting or losing user edits.
    """
    if manager is None:
        return False
    script_filename = f"episode_{episode}.json"
    try:
        script = manager.load_script(project_path.name, script_filename)
    except FileNotFoundError:
        return False

    mode = DRAFT_MODES.get(content_mode)
    if not mode:
        return False

    draft_dir = project_path / "drafts" / f"episode_{episode}"
    draft_file = draft_dir / mode.filename

    # If the draft directory doesn't exist, create it
    draft_dir.mkdir(parents=True, exist_ok=True)

    items = script.get(mode.script_items_key, [])
    if not items and content_mode == "drama":
        items = script.get("scenes", [])

    if not items:
        # If there are no segments/scenes, we don't write anything
        return False

    lines = []
    if content_mode == "narration":
        # Header
        lines.append("| 片段 | 原文 | 字數 | 時長 | 有對話 | segment_break |")
        lines.append("|------|------|------|------|--------|---------------|")
        for i, item in enumerate(items, 1):
            novel_text = item.get("novel_text") or ""
            # Escape pipe characters
            escaped_text = _escape_cell(novel_text)
            char_len = len(novel_text)
            duration = f"{item.get('duration_seconds', 4)}s"

            # Check dialogue
            dialogue = item.get("video_prompt", {}).get("dialogue", [])
            has_dialogue = "是" if dialogue else "否"

            # Segment break
            seg_break = "是" if item.get("segment_break") else "-"

            lines.append(f"| G{i:02d} | {escaped_text} | {char_len} | {duration} | {has_dialogue} | {seg_break} |")
    else:
        # Drama mode
        lines.append("| 場景 ID | 場景描述 | 旁白 | 對話 | 出場的角色 | 出現的道具 | 場景 | 時長 | segment_break |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for item in items:
            scene_id = item.get("scene_id") or ""
            scene_desc = _escape_cell(item.get("scene_description") or "")

            # Narration
            narration = _escape_cell(item.get("narration_text") or "")
            if not narration:
                narration = "-"

            # Dialogue
            dialogue_list = item.get("video_prompt", {}).get("dialogue", [])
            if dialogue_list:
                dialogue_parts = []
                for diag in dialogue_list:
                    speaker = diag.get("speaker") or ""
                    line_val = diag.get("line") or diag.get("text") or ""
                    if speaker or line_val:
                        dialogue_parts.append(f"{speaker}：{line_val}")
                dialogue_str = _escape_cell("<br>".join(dialogue_parts)) if dialogue_parts else "-"
            else:
                dialogue_str = "-"

            # Characters
            chars = ", ".join(item.get("characters_in_scene") or [])
            chars_str = _escape_cell(chars) if chars else "-"

            # Clues
            clues = ", ".join(item.get("clues_in_scene") or [])
            clues_str = _escape_cell(clues) if clues else "-"

            # Scene location
            scene_in_scene = _escape_cell(item.get("scene_in_scene") or "")
            if not scene_in_scene:
                scene_in_scene = "-"

            # Duration
            duration = str(item.get("duration_seconds", 8))

            # Segment break
            seg_break = "是" if item.get("segment_break") else "否"

            lines.append(
                f"| {scene_id} | {scene_desc} | {narration} | {dialogue_str} | {chars_str} | {clues_str} | {scene_in_scene} | {duration} | {seg_break} |"
            )

    new_md = "\n".join(lines) + "\n"
    draft_file.write_text(new_md, encoding="utf-8")
    return True
