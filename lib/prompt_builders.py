"""
統一的影象生成 Prompt 構建函式

所有 Prompt 模板集中在此檔案管理，確保 WebUI 和 Skill 使用相同的邏輯。

模組職責:
- 角色設計圖 Prompt 構建
- 線索設計圖 Prompt 構建（道具類）
- 場景設計圖 Prompt 構建（環境類）
- 分鏡圖 Prompt 字尾

使用方:
- webui/server/routers/generate.py
- .claude/skills/generate-characters/scripts/generate_character.py
- .claude/skills/generate-clues/scripts/generate_clue.py
"""


def build_character_prompt(name: str, description: str, style: str = "", style_description: str = "") -> str:
    """
    構建角色設計圖 Prompt

    遵循 nano-banana 最佳實踐：使用敘事性段落描述，而非關鍵詞列表。

    Args:
        name: 角色名稱
        description: 角色外貌描述（應為敘事性段落）
        style: 專案風格
        style_description: AI 分析的風格描述

    Returns:
        完整的 Prompt 字串
    """
    # 構建風格字首
    combined_style = build_style_prompt(style=style, style_description=style_description)
    style_prefix = f"{combined_style}\n\n" if combined_style else ""

    return f"""{style_prefix}角色設計參考圖。

「{name}」的全身立繪。

{description}

構圖要求：單一角色全身像，姿態自然，面向鏡頭。
背景：純淨淺灰色，無任何裝飾元素。
光線：柔和均勻的攝影棚照明，無強烈陰影。
畫質：高畫質，細節清晰，色彩準確。"""


def build_clue_prompt(name: str, description: str, style: str = "", style_description: str = "") -> str:
    """
    構建線索（道具）設計圖 Prompt

    Args:
        name: 線索名稱
        description: 線索描述
        style: 專案風格
        style_description: AI 分析的風格描述

    Returns:
        完整的 Prompt 字串
    """
    return build_prop_prompt(name, description, style, style_description)


def build_scene_prompt(name: str, description: str, style: str = "", style_description: str = "") -> str:
    """
    構建場景設計圖 Prompt

    場景本質為環境/背景，沿用 location 模板。

    Args:
        name: 場景名稱
        description: 場景描述
        style: 專案風格
        style_description: AI 分析的風格描述

    Returns:
        完整的 Prompt 字串
    """
    return build_location_prompt(name, description, style, style_description)


def build_prop_prompt(name: str, description: str, style: str = "", style_description: str = "") -> str:
    """
    構建道具類線索 Prompt

    使用三檢視構圖：正面全檢視、45度側檢視、細節特寫。

    Args:
        name: 道具名稱
        description: 道具描述
        style: 專案風格
        style_description: AI 分析的風格描述

    Returns:
        完整的 Prompt 字串
    """
    # 構建風格字首
    combined_style = build_style_prompt(style=style, style_description=style_description)
    style_prefix = f"{combined_style}\n\n" if combined_style else ""

    return f"""{style_prefix}一張專業的道具設計參考圖。

道具「{name}」的多視角展示。{description}

三個檢視水平排列在純淨淺灰背景上：左側正面全檢視、中間45度側檢視展示立體感、右側關鍵細節特寫。柔和均勻的攝影棚照明，高畫質質感，色彩準確。"""


def build_location_prompt(name: str, description: str, style: str = "", style_description: str = "") -> str:
    """
    構建場景環境 Prompt

    使用 3/4 主畫面 + 右下角細節特寫的構圖。

    Args:
        name: 場景名稱
        description: 場景描述
        style: 專案風格
        style_description: AI 分析的風格描述

    Returns:
        完整的 Prompt 字串
    """
    # 構建風格字首
    combined_style = build_style_prompt(style=style, style_description=style_description)
    style_prefix = f"{combined_style}\n\n" if combined_style else ""

    return f"""{style_prefix}一張專業的場景設計參考圖。

標誌性場景「{name}」的視覺參考。{description}

主畫面佔據四分之三區域展示環境整體外觀與氛圍，右下角小圖為細節特寫。柔和自然光線。"""


def build_storyboard_suffix(content_mode: str = "narration", *, aspect_ratio: str | None = None) -> str:
    """
    獲取分鏡圖 Prompt 字尾

    優先使用 aspect_ratio 引數；若未傳，按 content_mode 推導（向後相容）。
    """
    if aspect_ratio is None:
        ratio = "9:16" if content_mode == "narration" else "16:9"
    else:
        ratio = aspect_ratio
    if ratio == "9:16":
        return "豎屏構圖。"
    elif ratio == "16:9":
        return "橫屏構圖。"
    return ""


def build_style_prompt(project_data: dict | None = None, *, style: str = "", style_description: str = "") -> str:
    """
    構建風格描述 Prompt 片段

    合併 style 和 style_description。可接收 project_data 字典，或單獨接收 style / style_description。

    Args:
        project_data: project.json 資料 (可選)
        style: 專案風格標籤 (可選)
        style_description: AI 分析的風格描述 (可選)

    Returns:
        風格描述字串，用於拼接到生成 Prompt 中
    """
    if project_data is not None:
        style = project_data.get("style", "")
        style_description = project_data.get("style_description", "")

    parts = []

    # 基礎風格標籤
    if style:
        parts.append(f"Style: {style}")

    # AI 分析的風格描述
    if style_description:
        parts.append(f"Visual style: {style_description}")

    return "\n".join(parts)
