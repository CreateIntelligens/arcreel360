"""分集切分核心：純文字運算（無 I/O、無 cwd 假設）。

供三條路徑共用：
- Claude CLI 腳本（agent_runtime_profile/.claude/skills/manage-project/scripts/*.py，薄 wrapper）
- gemini/openai function handler（server/agent_runtime/skill_function_declarations.py）
- HTTP API（server/routers/projects.py）

計數規則：含標點，不含空行（純空白行不計入字數）。
"""

from __future__ import annotations

from pathlib import Path


class SourceFileError(ValueError):
    """source 檔案路徑越界或不存在。"""

    def __init__(self, kind: str, source: str) -> None:
        self.kind = kind  # "path_escape" | "not_found"
        self.source = source
        msg = f"source 必須在 source/ 下: {source}" if kind == "path_escape" else f"檔案不存在: {source}"
        super().__init__(msg)


def resolve_source_under(project_dir: Path, source: str) -> Path:
    """把 source（相對路徑）解析為 project_dir/source/ 內的絕對路徑。

    Raises SourceFileError("path_escape" | "not_found")。
    """
    source_dir = (project_dir / "source").resolve()
    src_abs = (project_dir / source).resolve()
    if not src_abs.is_relative_to(source_dir):
        raise SourceFileError("path_escape", source)
    if not src_abs.exists():
        raise SourceFileError("not_found", source)
    return src_abs


def split_result_dict(episode: int, split: dict) -> dict:
    """把 split_episode_text 的結果整理成對外回傳的固定欄位 dict。"""
    return {
        "episode": episode,
        "episode_file": f"source/episode_{episode}.txt",
        "remaining_file": "source/_remaining.txt",
        "part_before_chars": len(split["part_before"]),
        "part_after_chars": len(split["part_after"]),
        "split_pos": split["split_pos"],
        "anchor_match_count": split["anchor_match_count"],
    }


def count_chars(text: str) -> int:
    """計算有效字數：所有非空行中的字元總數（含標點，不含空行）。"""
    total = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped:  # 跳過空行
            total += len(stripped)
    return total


def find_char_offset(text: str, target_count: int) -> int:
    """將有效字數轉換為原文字元偏移位置（0-based）。

    遍歷原文，跳過空行中的字元，當累計有效字數達到 target_count 時，
    返回對應的原文字元偏移。target_count 超過總有效字數時，返回文字末尾偏移。
    """
    counted = 0
    lines = text.split("\n")
    pos = 0  # 原文中的字元位置

    for line_idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            # 空行：跳過整行（含換行符）
            pos += len(line)
            if line_idx < len(lines) - 1:
                pos += 1  # 換行符
            continue

        # 非空行：逐字元計數
        for char in line:
            if not char.strip():
                # 行首/行尾空白不計入有效字數，但推進偏移
                pos += 1
                continue
            counted += 1
            if counted >= target_count:
                return pos
            pos += 1

        if line_idx < len(lines) - 1:
            pos += 1  # 換行符

    return pos


def find_natural_breakpoints(text: str, center_offset: int, window: int = 200) -> list[dict]:
    """在指定偏移附近查詢自然斷點（句末標點、段落邊界）。

    回斷點列表，每個斷點含：
    - offset: 原文字元偏移（標點/段落之後的位置）
    - char: 斷點字元
    - type: 斷點型別（sentence / paragraph）
    - distance: 距 center_offset 的字元數

    結果按 distance 由近到遠排序。
    """
    start = max(0, center_offset - window)
    end = min(len(text), center_offset + window)

    sentence_endings = {"。", "！", "？", "…"}
    breakpoints: list[dict] = []

    for i in range(start, end):
        ch = text[i]
        if ch == "\n" and i + 1 < len(text) and text[i + 1] == "\n":
            breakpoints.append(
                {
                    "offset": i + 1,
                    "char": "\\n\\n",
                    "type": "paragraph",
                    "distance": abs(i + 1 - center_offset),
                }
            )
        elif ch in sentence_endings:
            breakpoints.append(
                {
                    "offset": i + 1,  # 在標點之後切分
                    "char": ch,
                    "type": "sentence",
                    "distance": abs(i + 1 - center_offset),
                }
            )

    breakpoints.sort(key=lambda bp: bp["distance"])
    return breakpoints


# 成對引號：開引號 → 對應閉引號。
_QUOTE_PAIRS = {"「": "」", "『": "』", "“": "”"}
_OPEN_QUOTES = set(_QUOTE_PAIRS.keys())
_CLOSE_QUOTES = set(_QUOTE_PAIRS.values())


def _compute_quote_depth_prefix(text: str) -> list[int]:
    """一次 O(N) 算出整段文字每個位置的引號總深度。

    depth[i] = 「字元 text[0..i-1] 處理完後」的累積深度,等同 _quote_depth_at(text, i)。
    長度為 len(text) + 1。供 split_into_n_episodes 等需多次查詢的呼叫者重用,
    避免每次 _quote_state_at 都從頭線性掃描造成 O(N²)。
    """
    n = len(text)
    depth = [0] * (n + 1)
    pair_depth = 0
    straight_open = 0
    for i in range(n):
        ch = text[i]
        if ch in _OPEN_QUOTES:
            pair_depth += 1
        elif ch in _CLOSE_QUOTES:
            pair_depth = max(0, pair_depth - 1)
        elif ch == '"':
            straight_open ^= 1
        depth[i + 1] = pair_depth + straight_open
    return depth


def _quote_state_at(text: str, offset: int) -> tuple[int, int]:
    """計算 offset 位置前的引號狀態。

    回傳 (pair_depth, straight_open)：
    - pair_depth：成對引號（「」『』“”）的淨深度，遇開 +1、遇閉 -1（不為負）。
    - straight_open：直/英文引號（"）的開合狀態，採配對計數，奇數個為 1。

    巢狀引號（如「…『…』…」）由淨深度自然涵蓋。
    """
    pair_depth = 0
    straight_open = 0
    for ch in text[:offset]:
        if ch in _OPEN_QUOTES:
            pair_depth += 1
        elif ch in _CLOSE_QUOTES:
            pair_depth = max(0, pair_depth - 1)
        elif ch == '"':
            straight_open ^= 1
    return pair_depth, straight_open


def _quote_depth_at(text: str, offset: int) -> int:
    """offset 前的引號總深度（>0 表示落在對話/引號內部）。"""
    pair_depth, straight_open = _quote_state_at(text, offset)
    return pair_depth + straight_open


def _adjust_out_of_quotes(text: str, offset: int, depth_prefix: list[int] | None = None) -> int:
    """若 offset 落在成對引號內部，調整到引號外最近的安全點。

    優先往後移到對話結束（閉引號之後）；找不到閉引號（未閉合引號）時，
    退而往前移到對話開始（開引號之前）。兩者皆失敗（理論上不會）則回原值。
    保證回傳值仍落在 [0, len(text)]，呼叫端的單調遞增/越界裁切照常生效。

    depth_prefix:可選的預計算引號深度陣列(`_compute_quote_depth_prefix(text)` 的輸出),
    傳入後「往前找」的 fallback 由 O(N²) 降為 O(N)。
    """
    if offset <= 0 or offset >= len(text):
        return offset
    pair_depth, straight_open = _quote_state_at(text, offset)
    if pair_depth == 0 and straight_open == 0:
        return offset

    # 往後找：移到使深度歸零的閉引號（或直引號）之後。
    for i in range(offset, len(text)):
        ch = text[i]
        if ch in _OPEN_QUOTES:
            pair_depth += 1
        elif ch in _CLOSE_QUOTES:
            pair_depth = max(0, pair_depth - 1)
        elif ch == '"' and straight_open:
            straight_open = 0
        if pair_depth == 0 and straight_open == 0:
            return i + 1

    # 未閉合引號：往前找到最外層開引號之前。
    # 有 depth_prefix 時走 O(N) 快路徑;否則退回每次 O(N) 重掃(O(N²) 但保留契約相容)。
    if depth_prefix is not None:
        for i in range(offset - 1, -1, -1):
            if depth_prefix[i] == 0:
                return i
    else:
        for i in range(offset - 1, -1, -1):
            if _quote_depth_at(text, i) == 0:
                return i
    return offset


def find_anchor_near_target(text: str, anchor: str, target_offset: int, window: int = 500) -> list[int]:
    """在 target_offset 附近視窗內查 anchor，回匹配「末尾」偏移列表（按距 target_offset 排序）。"""
    search_start = max(0, target_offset - window)
    search_end = min(len(text), target_offset + window)
    region = text[search_start:search_end]
    positions: list[int] = []
    start = 0
    while True:
        idx = region.find(anchor, start)
        if idx == -1:
            break
        positions.append(search_start + idx + len(anchor))  # 錨點末尾的絕對偏移
        start = idx + 1
    positions.sort(key=lambda p: abs(p - target_offset))
    return positions


def peek_split(source_text: str, target_chars: int, context: int = 200) -> dict:
    """預覽分集切分點（read-only）。

    Args:
        source_text: 小說原文。
        target_chars: 目標有效字數（含標點、不含空行）。
        context: 前後文與斷點搜尋視窗（字元數）。

    Returns:
        {total_chars, target_chars, target_offset, context_before, context_after, nearby_breakpoints}。

    Raises:
        ValueError: target_chars 大於等於總有效字數。
    """
    total_chars = count_chars(source_text)
    if target_chars >= total_chars:
        raise ValueError(f"目標字數 ({target_chars}) 超過或等於總有效字數 ({total_chars})")
    target_offset = find_char_offset(source_text, target_chars)
    breakpoints = find_natural_breakpoints(source_text, target_offset, window=context)
    ctx_start = max(0, target_offset - context)
    ctx_end = min(len(source_text), target_offset + context)
    return {
        "total_chars": total_chars,
        "target_chars": target_chars,
        "target_offset": target_offset,
        "context_before": source_text[ctx_start:target_offset],
        "context_after": source_text[target_offset:ctx_end],
        "nearby_breakpoints": breakpoints[:10],
    }


def split_episode_text(source_text: str, target_chars: int, anchor: str, context: int = 500) -> dict:
    """用 anchor 在 target_chars 附近精確定位切點，回兩半文字。

    anchor 找不到 → ValueError。anchor 多個 → 選距 target 最近的（不報錯，回傳 anchor_match_count 供呼叫方提示）。

    Returns:
        {split_pos, part_before, part_after, before_preview, after_preview, anchor_match_count, target_offset}。
    """
    target_offset = find_char_offset(source_text, target_chars)
    positions = find_anchor_near_target(source_text, anchor, target_offset, window=context)
    if not positions:
        raise ValueError(f'在目標字數 {target_chars} 附近（±{context} 字元視窗）未找到錨點文字: "{anchor}"')
    split_pos = positions[0]
    part_before = source_text[:split_pos]
    part_after = source_text[split_pos:]
    preview_len = 50
    return {
        "split_pos": split_pos,
        "part_before": part_before,
        "part_after": part_after,
        "before_preview": part_before[-preview_len:] if len(part_before) > preview_len else part_before,
        "after_preview": part_after[:preview_len] if len(part_after) > preview_len else part_after,
        "anchor_match_count": len(positions),
        "target_offset": target_offset,
    }


def split_into_n_episodes(text: str, total_episodes: int) -> list[str]:
    """把整本原文按有效字數均分為 total_episodes 段，切點落最近句末標點。

    供「拆段時自動按集數均分原文」使用：不需錨點、不需使用者指定切點。
    保證 "".join(回傳值) == text（不丟字、不重複）。

    Args:
        text: 整本小說原文。
        total_episodes: 目標段數（= project.json 的集數），須 >= 1。

    Returns:
        長度為 total_episodes 的字串列表，依序為第 1..N 段。
        當內容過短不足以切出 N 段時，末尾段可能為空字串。

    Raises:
        ValueError: total_episodes < 1。
    """
    if total_episodes < 1:
        raise ValueError(f"集數必須 >= 1，得到 {total_episodes}")
    if total_episodes == 1:
        return [text]

    total = count_chars(text)
    text_len = len(text)
    # 預計算引號深度 prefix:O(N) 一次,免去 _quote_depth_at / _adjust_out_of_quotes
    # 內每次線性重掃造成的 O(N²)。
    depth_prefix = _compute_quote_depth_prefix(text)

    # 第 k 個切點落在 [prev_cut + 1, text_len] 區間,保證單調嚴格遞增、不產生空段。
    # 為每個 k 先挑選最佳切點,再以 prev_cut + 1 為下界強制單調。
    cut_offsets: list[int] = []
    prev_cut = 0
    for k in range(1, total_episodes):
        target_chars = round(total * k / total_episodes)
        raw_offset = find_char_offset(text, target_chars)
        # 視窗放大到 600：長對話（句末標點稀疏）也能命中自然斷點，
        # 大幅降低 fallback 成純字數硬切的機率。
        breakpoints = find_natural_breakpoints(text, raw_offset, window=600)
        # 優先句末標點，其次段落邊界；引號外的斷點優先（避免對話中間）。
        sentence_bps = [bp for bp in breakpoints if bp["type"] == "sentence"]
        chosen = sentence_bps or breakpoints
        safe_bp = next((bp for bp in chosen if depth_prefix[bp["offset"]] == 0), None)
        if safe_bp is not None:
            offset = safe_bp["offset"]
        elif chosen:
            # 視窗內的斷點全落在引號內：取最近者再往外調整出引號。
            offset = _adjust_out_of_quotes(text, chosen[0]["offset"], depth_prefix)
        else:
            # 完全無自然斷點：fallback 字數硬切，但避開引號內部。
            offset = _adjust_out_of_quotes(text, raw_offset, depth_prefix)

        # 強制單調嚴格遞增 + 越界裁切:
        # _adjust_out_of_quotes 的「未閉合引號」fallback 可能往前推到上一切點之前,
        # 造成 sorted 後相鄰 offset 重複(產生空段)或順序與 k 編號脫鉤;
        # 改在此處夾在 [prev_cut + 1, text_len] 內,保證單調且不產生空段。
        offset = max(prev_cut + 1, min(offset, text_len))
        cut_offsets.append(offset)
        prev_cut = offset

    parts: list[str] = []
    prev = 0
    for offset in cut_offsets:
        parts.append(text[prev:offset])
        prev = offset
    parts.append(text[prev:])
    return parts
