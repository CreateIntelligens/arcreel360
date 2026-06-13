from lib.prompt_builders_script import (
    _format_character_names,
    _format_clue_names,
    build_drama_prompt,
    build_narration_prompt,
)


class TestPromptBuildersScript:
    def test_formatters_emit_bullet_lists(self):
        # 角色/線索名以 **name** 粗體標註，協助 LLM 識別為 token
        assert _format_character_names({"A": {}, "B": {}}) == "- **A**\n- **B**"
        assert _format_clue_names({"玉佩": {}, "祠堂": {}}) == "- **玉佩**\n- **祠堂**"

    def test_formatters_include_descriptions(self):
        assert _format_character_names({"比比拉布": {"description": "香蕉裡的貓"}}) == "- **比比拉布**：香蕉裡的貓"
        assert _format_clue_names({"玉佩": {"description": "綠色玉佩"}}) == "- **玉佩**：綠色玉佩"

    def test_build_narration_prompt_contains_dynamic_durations(self):
        prompt = build_narration_prompt(
            project_overview={"synopsis": "故事", "genre": "懸疑", "theme": "真相", "world_setting": "古代"},
            style="古風",
            style_description="cinematic",
            characters={"姜月茴": {}},
            clues={"玉佩": {}},
            segments_md="E1S01 | 文字",
            supported_durations=[4, 6, 8],
            default_duration=4,
            aspect_ratio="9:16",
        )
        assert "4, 6, 8" in prompt
        assert "預設使用 4 秒" in prompt

    def test_build_narration_prompt_auto_duration(self):
        prompt = build_narration_prompt(
            project_overview={"synopsis": "故事", "genre": "懸疑", "theme": "真相", "world_setting": "古代"},
            style="古風",
            style_description="cinematic",
            characters={"姜月茴": {}},
            clues={"玉佩": {}},
            segments_md="E1S01 | 文字",
            supported_durations=[5, 10],
            default_duration=None,
            aspect_ratio="9:16",
        )
        assert "5, 10" in prompt
        assert "根據內容節奏自行決定" in prompt

    def test_build_drama_prompt_uses_dynamic_aspect_ratio(self):
        prompt = build_drama_prompt(
            project_overview={"synopsis": "動作", "genre": "動作", "theme": "成長", "world_setting": "近未來"},
            style="賽博",
            style_description="high contrast",
            characters={"林": {}},
            clues={"晶片": {}},
            scenes_md="E1S01 | 追逐",
            supported_durations=[4, 8, 12],
            default_duration=8,
            aspect_ratio="9:16",
        )
        # 傳入豎屏時不應出現 "16:9 橫屏構圖"
        assert "16:9 橫屏構圖" not in prompt
        assert "豎屏構圖" in prompt

    def test_build_drama_prompt_landscape(self):
        prompt = build_drama_prompt(
            project_overview={"synopsis": "動作", "genre": "動作", "theme": "成長", "world_setting": "近未來"},
            style="賽博",
            style_description="high contrast",
            characters={"林": {}},
            clues={"晶片": {}},
            scenes_md="E1S01 | 追逐",
            supported_durations=[4, 6, 8],
            default_duration=8,
            aspect_ratio="16:9",
        )
        assert "橫屏構圖" in prompt

    def test_narration_prompt_embeds_language_rule(self):
        from lib.prompt_language import PROMPT_LANGUAGE_RULE

        prompt = build_narration_prompt(
            project_overview={"synopsis": "故事", "genre": "懸疑", "theme": "真相", "world_setting": "古代"},
            style="古風",
            style_description="cinematic",
            characters={"姜月茴": {}},
            clues={"玉佩": {}},
            segments_md="E1S01 | 文字",
            supported_durations=[4, 6, 8],
            default_duration=4,
            aspect_ratio="9:16",
        )
        assert PROMPT_LANGUAGE_RULE in prompt
        assert "繁體中文" in prompt

    def test_drama_prompt_embeds_language_rule(self):
        from lib.prompt_language import PROMPT_LANGUAGE_RULE

        prompt = build_drama_prompt(
            project_overview={"synopsis": "動作", "genre": "動作", "theme": "成長", "world_setting": "近未來"},
            style="賽博",
            style_description="high contrast",
            characters={"林": {}},
            clues={"晶片": {}},
            scenes_md="E1S01 | 追逐",
            supported_durations=[4, 8, 12],
            default_duration=8,
            aspect_ratio="9:16",
        )
        assert PROMPT_LANGUAGE_RULE in prompt
        assert "繁體中文" in prompt
