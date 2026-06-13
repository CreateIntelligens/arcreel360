from lib.prompt_builders import (
    build_character_prompt,
    build_clue_prompt,
    build_storyboard_suffix,
    build_style_prompt,
)


class TestPromptBuilders:
    def test_build_character_prompt_includes_style_and_description(self):
        prompt = build_character_prompt(
            "姜月茴",
            "黑髮，冷靜神態。",
            style="古風",
            style_description="Cinematic, low-key lighting",
        )
        assert "Style: 古風" in prompt
        assert "Visual style: Cinematic, low-key lighting" in prompt
        assert "角色設計參考圖。" in prompt
        assert "姜月茴" in prompt
        assert "黑髮，冷靜神態。" in prompt

    def test_build_clue_prompt_builds_prop_prompt(self):
        clue_prompt = build_clue_prompt("玉佩", "古樸", style="寫實")
        # 由於均呼叫 build_style_prompt，所以此時包含 Style: 寫實
        assert "Style: 寫實" in clue_prompt

    def test_build_storyboard_suffix_by_aspect_ratio(self):
        assert build_storyboard_suffix(aspect_ratio="9:16") == "豎屏構圖。"
        assert build_storyboard_suffix(aspect_ratio="16:9") == "橫屏構圖。"
        # 向後相容：不傳 aspect_ratio 時預設豎屏
        assert build_storyboard_suffix() == "豎屏構圖。"

    def test_build_style_prompt_combines_available_parts(self):
        project_data = {
            "style": "Anime",
            "style_description": "soft pastel, hand-drawn",
        }
        result = build_style_prompt(project_data)
        assert "Style: Anime" in result
        assert "Visual style: soft pastel, hand-drawn" in result

    def test_build_style_prompt_with_kwargs(self):
        result = build_style_prompt(style="Photographic", style_description="high detail")
        assert "Style: Photographic" in result
        assert "Visual style: high detail" in result

    def test_build_style_prompt_handles_empty_values(self):
        assert build_style_prompt({}) == ""
        assert build_style_prompt({"style": ""}) == ""
        assert build_style_prompt(style="", style_description="") == ""
