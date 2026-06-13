"""分鏡 id 正規化比對測試。

根因背景：episode_1 的 segment_id 補零（E1S01），episode_2 卻存成不補零（E2S1）。
使用者以規範格式 E2S01 操作 scene 設定時，find_storyboard_item 做字串精確比對
（"E2S1" == "E2S01" → False），導致 scene 覆蓋寫入找不到 item。

本測試固定「正規化比對」契約：補零與否視為同一個 id。
"""

from lib.storyboard_sequence import find_storyboard_item, normalize_storyboard_id


class TestNormalizeStoryboardId:
    def test_pads_sequence_to_canonical_form(self):
        # 不補零 → 正規化為補零的標準形
        assert normalize_storyboard_id("E2S1") == normalize_storyboard_id("E2S01")
        assert normalize_storyboard_id("E1S9") == normalize_storyboard_id("E1S09")

    def test_handles_sub_sequence(self):
        assert normalize_storyboard_id("E2S1_2") == normalize_storyboard_id("E2S01_2")

    def test_distinct_ids_stay_distinct(self):
        assert normalize_storyboard_id("E2S1") != normalize_storyboard_id("E2S2")
        assert normalize_storyboard_id("E1S01") != normalize_storyboard_id("E2S01")
        # 子序號不可與主序號混淆
        assert normalize_storyboard_id("E2S1_2") != normalize_storyboard_id("E2S12")

    def test_non_standard_id_falls_back_to_str(self):
        # 不符 E{n}S{n} 格式者，正規化不應拋例外，退化為原字串比較
        assert normalize_storyboard_id("custom") == normalize_storyboard_id("custom")
        assert normalize_storyboard_id("custom") != normalize_storyboard_id("E2S01")


class TestFindStoryboardItemNormalized:
    def test_finds_padded_query_against_unpadded_stored_id(self):
        # 重現 bug：JSON 存 E2S1，使用者用 E2S01 查
        items = [
            {"segment_id": "E2S1"},
            {"segment_id": "E2S2"},
            {"segment_id": "E2S3"},
        ]
        resolved = find_storyboard_item(items, "segment_id", "E2S01")
        assert resolved is not None
        item, index = resolved
        assert item["segment_id"] == "E2S1"
        assert index == 0

    def test_finds_unpadded_query_against_padded_stored_id(self):
        # 反向：JSON 存 E1S09，使用者用 E1S9 查
        items = [{"segment_id": "E1S08"}, {"segment_id": "E1S09"}]
        resolved = find_storyboard_item(items, "segment_id", "E1S9")
        assert resolved is not None
        assert resolved[0]["segment_id"] == "E1S09"

    def test_does_not_match_different_sequence(self):
        items = [{"segment_id": "E2S1"}, {"segment_id": "E2S2"}]
        assert find_storyboard_item(items, "segment_id", "E2S03") is None
