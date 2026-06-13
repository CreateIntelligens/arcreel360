"""entity_matching 模組測試 — 與前端 entity-matching.test.ts 對稱。"""

from lib.entity_matching import EntityMentionNames, expand_entity_aliases, scan_entity_mentions

# ============ expand_entity_aliases ============


class TestExpandEntityAliases:
    """別名拆解測試。"""

    def test_plain_chinese_name(self):
        assert expand_entity_aliases("錦衣衛") == ["錦衣衛"]

    def test_plain_english_name(self):
        assert expand_entity_aliases("Hero") == ["Hero"]

    def test_chinese_english_half_width(self):
        """半形括號: 阿克 (Arke)"""
        assert expand_entity_aliases("阿克 (Arke)") == ["阿克 (Arke)", "阿克", "Arke"]

    def test_chinese_english_full_width(self):
        """全形括號: 青玉碎片（Jade Shard）"""
        assert expand_entity_aliases("青玉碎片（Jade Shard）") == [
            "青玉碎片（Jade Shard）",
            "青玉碎片",
            "Jade Shard",
        ]

    def test_extra_whitespace_trimmed(self):
        """括號前後多餘空白應被去除。"""
        assert expand_entity_aliases("  阿克  (  Arke  )  ") == ["阿克  (  Arke  )", "阿克", "Arke"]

    def test_empty_string(self):
        assert expand_entity_aliases("") == []

    def test_dedup_when_parts_identical(self):
        """若中文部分和英文部分相同，去重。"""
        assert expand_entity_aliases("Foo (Foo)") == ["Foo (Foo)", "Foo"]


# ============ scan_entity_mentions ============


CHARACTERS = {
    "阿克 (Arke)": {},
    "錦衣衛": {},
    "小明": {},
}

CLUES = {
    "青玉碎片（Jade Shard）": {},
    "Key": {},
}

SCENES = {
    "古城": {},
    "荒野 (Wasteland)": {},
}


class TestScanEntityMentions:
    """比對演算法測試。"""

    def test_basic_chinese_match(self):
        result = scan_entity_mentions("小明拿起了青玉碎片", CHARACTERS, CLUES, SCENES)
        assert result.character_names == ["小明"]
        assert result.clue_names == ["青玉碎片（Jade Shard）"]
        assert result.scene_name is None

    def test_english_alias_match(self):
        """英文別名也要命中，映回原始 key。"""
        result = scan_entity_mentions("Arke found the Jade Shard", CHARACTERS, CLUES, SCENES)
        assert result.character_names == ["阿克 (Arke)"]
        assert result.clue_names == ["青玉碎片（Jade Shard）"]

    def test_full_key_match(self):
        """完整 key（含括號）也是有效比對詞。"""
        result = scan_entity_mentions("角色阿克 (Arke)出場了", CHARACTERS, CLUES, SCENES)
        assert result.character_names == ["阿克 (Arke)"]

    def test_longest_first(self):
        """長名稱優先於短名稱的前綴。"""
        chars = {"錦衣衛": {}, "錦衣": {}}
        result = scan_entity_mentions("錦衣衛出場", chars, {}, {})
        assert result.character_names == ["錦衣衛"]

    def test_non_overlapping(self):
        """比對非重疊：命中後游標跳過，不會再匹配重疊部分。"""
        chars = {"甲乙": {}, "乙丙": {}}
        result = scan_entity_mentions("甲乙丙", chars, {}, {})
        # "甲乙" 先命中，游標跳到 "丙"，"乙丙" 不會命中
        assert result.character_names == ["甲乙"]

    def test_scene_returns_first(self):
        """多個場景命中時，回傳排序後的第一個。"""
        result = scan_entity_mentions("古城和荒野都很美", CHARACTERS, CLUES, SCENES)
        assert result.scene_name is not None
        assert result.scene_name in ("古城", "荒野 (Wasteland)")

    def test_scene_english_alias(self):
        result = scan_entity_mentions("the Wasteland is vast", CHARACTERS, CLUES, SCENES)
        assert result.scene_name == "荒野 (Wasteland)"

    def test_cross_group_conflict_character_wins(self):
        """同名跨組衝突：character 優先於 clue。"""
        chars = {"古玉": {}}
        clues = {"古玉": {}}
        result = scan_entity_mentions("古玉很重要", chars, clues, {})
        assert result.character_names == ["古玉"]
        assert result.clue_names == []

    def test_ascii_word_boundary(self):
        """ASCII 名稱不應匹配更長單字的子字串。"""
        chars = {"Hero": {}}
        result = scan_entity_mentions("Heroic action by Hero", chars, {}, {})
        assert result.character_names == ["Hero"]

    def test_ascii_boundary_prefix(self):
        """ASCII 名稱前面有 word char 時不匹配。"""
        chars = {"Key": {}}
        result = scan_entity_mentions("MonKey business", {}, chars, {})
        assert result.clue_names == []

    def test_no_match_for_unknown(self):
        result = scan_entity_mentions("未知角色出場", CHARACTERS, CLUES, SCENES)
        assert result.character_names == []
        assert result.clue_names == []
        assert result.scene_name is None

    def test_empty_text(self):
        result = scan_entity_mentions("", CHARACTERS, CLUES, SCENES)
        assert result == EntityMentionNames()

    def test_empty_entities(self):
        result = scan_entity_mentions("一些文字", {}, {}, {})
        assert result == EntityMentionNames()

    def test_none_entities(self):
        result = scan_entity_mentions("一些文字")
        assert result == EntityMentionNames()

    def test_multiple_characters_in_text(self):
        result = scan_entity_mentions("小明和錦衣衛在古城相遇", CHARACTERS, CLUES, SCENES)
        assert sorted(result.character_names) == ["小明", "錦衣衛"]
        assert result.scene_name == "古城"

    def test_alias_maps_back_to_original_key(self):
        """所有別名命中都應映回原始 key，不是 alias 本身。"""
        result = scan_entity_mentions("Arke 和 Jade Shard", CHARACTERS, CLUES, SCENES)
        assert "阿克 (Arke)" in result.character_names
        assert "青玉碎片（Jade Shard）" in result.clue_names
        # 不應出現 alias 本身
        assert "Arke" not in result.character_names
        assert "Jade Shard" not in result.clue_names
