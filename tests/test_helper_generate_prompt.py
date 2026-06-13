def test_helper_system_prompt_traditional_chinese():
    from server.routers.generate import _build_helper_system_prompt

    for is_video in (True, False):
        sp = _build_helper_system_prompt(is_video)
        assert "繁體中文" in sp
        assert "英文 Prompt" not in sp
        assert "Zoom in" not in sp  # 相機運動範例已中文化


def test_helper_prompt_retry_detects_short_or_dangling_output():
    from server.routers.generate import _helper_prompt_needs_retry

    assert _helper_prompt_needs_retry("鏡頭緩慢向前推近，溫暖")
    assert _helper_prompt_needs_retry("鏡頭緩慢向前推近，")
    assert not _helper_prompt_needs_retry(
        "鏡頭緩慢向前推近老闆娘整理冰櫃的身影，午後暖光灑入柑仔店，空氣裡有蟬鳴與塑膠箱碰撞聲。"
    )


def test_helper_user_prompt_includes_lorebook_and_style_context():
    from server.routers.generate import OptimizePromptRequest, _build_helper_user_prompt

    project = {
        "style": "1980年代台灣寫實",
        "style_description": "暖色底片顆粒、午後斜射光、自然生活感",
        "style_image": "style/refs/store.png",
        "overview": {"genre": "懷舊日常", "synopsis": "柑仔店的一天"},
        "characters": {
            "老闆娘": {"description": "勤快、親切，穿著碎花圍裙", "voice_style": "溫柔但俐落"},
        },
        "clues": {
            "麥香紅茶": {"description": "鋁箔包裝的紅茶飲料，整齊排在老冰櫃角落", "importance": "major"},
        },
        "scenes": {
            "柑仔店": {"description": "木架陳列雜貨，老舊冰櫃在門口旁", "scene_ref": "scenes/refs/store.png"},
        },
    }
    req = OptimizePromptRequest(
        type="video_prompt",
        description="上下文內容:\n1980年代夏季午後，老闆娘把麥香紅茶排進柑仔店冰櫃。",
    )

    prompt = _build_helper_user_prompt(project, req, "影片動作提示詞")

    assert "請優先依據「基本描述/分鏡旁白內容」中的最新原文或目前片段內容" in prompt
    assert "基本描述/分鏡旁白內容: 上下文內容:" in prompt
    assert "專案風格描述: 暖色底片顆粒、午後斜射光、自然生活感" in prompt
    assert "專案風格參考圖: style/refs/store.png" in prompt
    assert "角色設定集:" in prompt
    assert "- 老闆娘：勤快、親切，穿著碎花圍裙（聲線/語氣: 溫柔但俐落）" in prompt
    assert "道具/線索設定集:" in prompt
    assert "- 麥香紅茶：鋁箔包裝的紅茶飲料，整齊排在老冰櫃角落（重要程度: major）" in prompt
    assert "場景設定集:" in prompt
    assert "- 柑仔店：木架陳列雜貨，老舊冰櫃在門口旁（參考圖: scenes/refs/store.png）" in prompt
