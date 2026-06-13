import pytest

from lib.episode_splitter import (
    count_chars,
    find_char_offset,
    find_natural_breakpoints,
    peek_split,
    split_episode_text,
)


def test_count_chars_skips_blank_lines():
    text = "abc\n\n  \ndef"
    assert count_chars(text) == 6  # "abc" + "def"，空行與純空白行不計


def test_count_chars_includes_punctuation():
    assert count_chars("你好，世界！") == 6


def test_find_char_offset_basic():
    text = "abcde"
    assert find_char_offset(text, 3) == 2


def test_find_char_offset_skips_blank_line():
    text = "ab\n\ncd"  # 有效字元: a b c d；c 是第 3 個
    # offset: a=0 b=1 \n=2 \n=3 c=4 d=5 → 第 3 個有效字元在 offset 4
    assert find_char_offset(text, 3) == 4


def test_find_char_offset_overflow_returns_end():
    text = "abc"
    assert find_char_offset(text, 999) == len(text)


def test_find_natural_breakpoints_finds_sentence_end():
    text = "他轉身。她跟上。"
    bps = find_natural_breakpoints(text, center_offset=4, window=10)
    assert any(bp["type"] == "sentence" for bp in bps)
    assert bps == sorted(bps, key=lambda b: b["distance"])


def test_find_natural_breakpoints_finds_paragraph():
    text = "第一段。\n\n第二段。"
    bps = find_natural_breakpoints(text, center_offset=len("第一段。\n"), window=10)
    assert any(bp["type"] == "paragraph" for bp in bps)


def test_peek_split_returns_context_and_breakpoints():
    text = "甲" * 10 + "。" + "乙" * 10
    result = peek_split(text, target_chars=10, context=5)
    assert result["total_chars"] == 21
    assert result["target_chars"] == 10
    assert "context_before" in result and "context_after" in result
    assert isinstance(result["nearby_breakpoints"], list)


def test_peek_split_target_overflow_raises():
    with pytest.raises(ValueError, match="超過"):
        peek_split("短文", target_chars=100)


def test_split_episode_text_basic():
    text = "前半段落。他轉身離開了。後半段落。"
    result = split_episode_text(text, target_chars=8, anchor="他轉身離開了。", context=20)
    assert result["part_before"].endswith("他轉身離開了。")
    assert result["part_after"].startswith("後半段落。")
    assert result["split_pos"] == len("前半段落。他轉身離開了。")
    assert result["before_preview"] in result["part_before"]


def test_split_episode_text_anchor_not_found_raises():
    with pytest.raises(ValueError, match="未找到錨點"):
        split_episode_text("一些文字內容。", target_chars=3, anchor="不存在的錨點", context=50)


def test_split_episode_text_anchor_multiple_picks_nearest():
    text = "錨點AB" + "X" * 20 + "錨點AB" + "Y" * 5
    target_offset_chars = len("錨點AB") + 20 + 1  # 接近第二個錨點
    result = split_episode_text(text, target_chars=target_offset_chars, anchor="錨點AB", context=30)
    assert result["split_pos"] == len("錨點AB") + 20 + len("錨點AB")
    assert result["anchor_match_count"] == 2


def test_split_into_n_episodes_single():
    """N=1：整本即唯一一集。"""
    from lib.episode_splitter import split_into_n_episodes

    text = "第一句。第二句。第三句。"
    parts = split_into_n_episodes(text, 1)
    assert parts == [text]


def test_split_into_n_episodes_two_parts_concatenate_to_original():
    """N=2：兩段串接後等於原文（不丟字、不重複）。"""
    from lib.episode_splitter import split_into_n_episodes

    text = "甲" * 50 + "。" + "乙" * 50 + "。"
    parts = split_into_n_episodes(text, 2)
    assert len(parts) == 2
    assert "".join(parts) == text
    assert min(len(p) for p in parts) >= len(text) // 4


def test_split_into_n_episodes_cuts_on_sentence_end():
    """切點應落在句末標點之後，不切斷句子。"""
    from lib.episode_splitter import split_into_n_episodes

    text = "甲甲甲甲甲。乙乙乙乙乙。丙丙丙丙丙。"
    parts = split_into_n_episodes(text, 3)
    assert len(parts) == 3
    assert "".join(parts) == text
    for part in parts[:-1]:
        assert part.rstrip()[-1] in "。！？…"


def test_split_into_n_episodes_three_parts():
    """N=3：產生 3 段，串接還原。"""
    from lib.episode_splitter import split_into_n_episodes

    text = "".join(f"這是第{i}句話。" for i in range(30))
    parts = split_into_n_episodes(text, 3)
    assert len(parts) == 3
    assert "".join(parts) == text


def test_split_into_n_episodes_invalid_n_raises():
    """N<1 → ValueError。"""
    import pytest

    from lib.episode_splitter import split_into_n_episodes

    with pytest.raises(ValueError):
        split_into_n_episodes("一些文字。", 0)


def test_split_into_n_episodes_more_episodes_than_content():
    """N 大於可切分句子數：仍回傳 N 段，允許部分段為空字串，串接仍還原。"""
    from lib.episode_splitter import split_into_n_episodes

    text = "只有一句。"
    parts = split_into_n_episodes(text, 5)
    assert len(parts) == 5
    assert "".join(parts) == text


def _depth(text: str, offset: int) -> int:
    """測試輔助：取 offset 前的引號淨深度。"""
    from lib.episode_splitter import _quote_depth_at

    return _quote_depth_at(text, offset)


def test_split_into_n_episodes_does_not_cut_inside_dialogue():
    """核心修復：切點原本會落在對話中間時，修正後切點落在引號外。

    建構一段：左半填充字 + 一句橫跨目標字數的長對話 + 右半填充字。
    目標切點（總字數一半）會落在長對話內部；修復後不得在引號內切。
    """
    from lib.episode_splitter import split_into_n_episodes

    left = "甲" * 40 + "。"
    # 長對話：內部無句末標點，舊版視窗 200 找不到斷點會硬切在對話中間。
    dialogue = "「" + "他緩緩開口說了很多話語" * 12 + "」"
    right = "乙" * 40 + "。"
    text = left + dialogue + right

    parts = split_into_n_episodes(text, 2)

    # 契約：段數正確、join 還原。
    assert len(parts) == 2
    assert "".join(parts) == text
    # 修復重點：切點（= 第一段長度）不在引號內部。
    cut = len(parts[0])
    assert _depth(text, cut) == 0
    # 切點不應落在對話正中間：第二段開頭不是孤立的殘缺半句。
    assert not parts[1].startswith("他緩緩")


def test_split_into_n_episodes_no_dangling_close_quote_at_start():
    """重現災情：修復後某集開頭不會是孤零零的閉引號。"""
    from lib.episode_splitter import split_into_n_episodes

    # 三段對話相連，目標切點落在中段對話內。
    text = "敘述文字。" * 10 + "「碎片自然不夠。」" * 6 + "赫爾曼將木盒收好。" * 10
    parts = split_into_n_episodes(text, 2)
    assert "".join(parts) == text
    after = parts[1].lstrip()
    # 開頭不得是閉引號（殘句），也不得在引號深度 >0 處起始。
    assert not after.startswith("」")
    assert _depth(text, len(parts[0])) == 0


def test_split_into_n_episodes_handles_nested_quotes():
    """巢狀引號（「…『…』…」）：切點不落在任一層引號內部。"""
    from lib.episode_splitter import split_into_n_episodes

    left = "丙" * 30 + "。"
    nested = "「外層對話" + "『內層引述很長很長』" * 8 + "外層結束」"
    right = "丁" * 30 + "。"
    text = left + nested + right
    parts = split_into_n_episodes(text, 2)
    assert "".join(parts) == text
    assert _depth(text, len(parts[0])) == 0


def test_split_into_n_episodes_straight_quotes():
    """直引號（"）配對計數：切點不落在成對直引號之間。"""
    from lib.episode_splitter import split_into_n_episodes

    left = "戊" * 40 + "。"
    dialogue = '"' + "this is a long english dialogue line " * 6 + '"'
    right = "己" * 40 + "。"
    text = left + dialogue + right
    parts = split_into_n_episodes(text, 2)
    assert "".join(parts) == text
    assert _depth(text, len(parts[0])) == 0


def test_split_into_n_episodes_unclosed_quote_falls_back_safely():
    """未閉合引號：往後找不到閉引號時，退回開引號之前，仍不破壞契約。"""
    from lib.episode_splitter import split_into_n_episodes

    # 開引號之後到文末都沒有閉引號。
    left = "庚" * 40 + "。"
    text = left + "「這段對話一直沒有結束" * 10
    parts = split_into_n_episodes(text, 2)
    assert len(parts) == 2
    assert "".join(parts) == text


def test_adjust_out_of_quotes_moves_after_close_quote():
    """_adjust_out_of_quotes：引號內 offset 調整到閉引號之後。"""
    from lib.episode_splitter import _adjust_out_of_quotes

    text = "前文。「對話內容」後文。"
    inside = text.index("對話")  # 落在引號內
    adjusted = _adjust_out_of_quotes(text, inside)
    assert _depth(text, adjusted) == 0
    assert adjusted == text.index("」") + 1


def test_adjust_out_of_quotes_keeps_safe_offset():
    """_adjust_out_of_quotes：引號外的 offset 不變動。"""
    from lib.episode_splitter import _adjust_out_of_quotes

    text = "前文。「對話」後文。"
    safe = text.index("後文")
    assert _adjust_out_of_quotes(text, safe) == safe


def test_split_into_n_episodes_many_parts_no_cut_inside_quotes():
    """N=5 多切點：每一個切點都必須落在引號外（淨深度 0）。"""
    from lib.episode_splitter import split_into_n_episodes

    # 對話與敘述交錯，確保部分切點目標字數會落在對話內。
    text = "".join("「一段對話內容」" if i % 3 == 0 else f"敘述句子第{i}句。" for i in range(60))
    parts = split_into_n_episodes(text, 5)

    assert len(parts) == 5
    assert "".join(parts) == text
    # 逐一檢查 4 個切點（= 各段累計長度）皆不在引號內部。
    cumulative = 0
    for part in parts[:-1]:
        cumulative += len(part)
        assert _depth(text, cumulative) == 0


def test_split_into_n_episodes_unclosed_straight_quote_safe():
    """直引號未配對（奇數個）：往後無法閉合時退回開引號之前，切點仍安全。"""
    from lib.episode_splitter import split_into_n_episodes

    left = "戊" * 40 + "。"
    text = left + '"this english dialogue never gets closed ' * 20
    parts = split_into_n_episodes(text, 2)

    assert len(parts) == 2
    assert "".join(parts) == text
    assert _depth(text, len(parts[0])) == 0


def test_split_into_n_episodes_short_dialogue_spanning_target():
    """短對話正好橫跨目標切點：切點被推到閉引號之後，不切斷短句。"""
    from lib.episode_splitter import split_into_n_episodes

    text = "子" * 50 + "「短對話」" + "丑" * 4
    parts = split_into_n_episodes(text, 2)

    assert "".join(parts) == text
    cut = len(parts[0])
    assert _depth(text, cut) == 0
    # 切點不得落在開引號與閉引號之間。
    assert not (text.index("「") < cut <= text.index("」"))


def test_split_into_n_episodes_strict_monotonic_no_empty_segments():
    """多切點 + 同一長對話橫跨多個目標位置:不得出現空段、切點需嚴格遞增。

    迴歸測試:`_adjust_out_of_quotes` 把相鄰切點都推到同一閉引號之後
    曾造成 cut_offsets 重複,parts 出現空字串段。
    """
    from lib.episode_splitter import split_into_n_episodes

    # 一段超長對話橫跨多個 N=5 的目標切點。
    text = "前文。" * 5 + "「" + "啊" * 200 + "」" + "後文。" * 5
    parts = split_into_n_episodes(text, 5)

    assert len(parts) == 5
    assert "".join(parts) == text
    # 每段都非空(嚴格單調 = 切點不重複)。
    for i, part in enumerate(parts):
        assert part != "", f"parts[{i}] 為空字串,切點重複導致空段"


def test_split_into_n_episodes_unclosed_quote_keeps_monotonic_for_many_parts():
    """N>2 + 未閉合引號:即便 fallback 往前推,切點順序仍與 k 編號一致、無空段。

    迴歸測試:未閉合引號 fallback 把切點往前推到 raw_offset 之前,
    曾導致 sorted 後排序與 k 編號脫鉤、長度分佈錯亂。
    """
    from lib.episode_splitter import split_into_n_episodes

    text = "正常文字。" * 10 + "「未閉合對話開始" + "字" * 500
    parts = split_into_n_episodes(text, 4)

    assert len(parts) == 4
    assert "".join(parts) == text
    # 每段非空。
    for i, part in enumerate(parts):
        assert part != "", f"parts[{i}] 為空字串"


def test_split_into_n_episodes_long_text_performance():
    """O(N²) 退化迴歸測試:10 萬字含未閉合引號應在 1 秒內完成,而非數十秒。"""
    import time

    from lib.episode_splitter import split_into_n_episodes

    text = "正文段落。" * 5000 + "「未閉合對話" + "字" * 50000
    start = time.monotonic()
    parts = split_into_n_episodes(text, 10)
    elapsed = time.monotonic() - start

    assert "".join(parts) == text
    assert len(parts) == 10
    # 上限放寬到 1 秒(實際 O(N) 應遠快於此);修前 O(N²) 同等規模耗時可達數十秒。
    assert elapsed < 1.0, f"split_into_n_episodes 退化:10 萬字耗時 {elapsed:.2f}s"
