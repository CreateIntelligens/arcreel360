"""
prompt_builders_script.py - 劇本生成 Prompt 構建器

1. XML 標籤分隔上下文
2. 明確的欄位描述和約束
3. 可選值列表約束輸出
"""

from lib.prompt_language import PROMPT_LANGUAGE_RULE


def _format_named_entries(items: dict, *, separator: str = "：") -> str:
    lines = []
    for name, data in items.items():
        desc = (data.get("description") or "").strip() if isinstance(data, dict) else ""
        suffix = f"{separator}{desc}" if desc else ""
        lines.append(f"- **{name}**{suffix}")
    return "\n".join(lines)


def _format_character_names(characters: dict) -> str:
    """格式化角色列表（含描述，協助 LLM 正確識別）"""
    return _format_named_entries(characters)


def _format_clue_names(clues: dict) -> str:
    """格式化線索列表（含描述，協助 LLM 正確識別）"""
    return _format_named_entries(clues)


def _format_duration_constraint(supported_durations: list[int], default_duration: int | None) -> str:
    """根據引數生成時長約束描述。"""
    durations_str = ", ".join(str(d) for d in supported_durations)
    if default_duration is not None:
        return f"時長：從 [{durations_str}] 秒中選擇，預設使用 {default_duration} 秒"
    return f"時長：從 [{durations_str}] 秒中選擇，根據內容節奏自行決定"


def _format_aspect_ratio_desc(aspect_ratio: str) -> str:
    """根據寬高比返回構圖描述。"""
    if aspect_ratio == "9:16":
        return "豎屏構圖"
    if aspect_ratio == "16:9":
        return "橫屏構圖"
    return f"{aspect_ratio} 構圖"


def _format_scene_names(scenes: dict) -> str:
    """格式化場景列表（含描述,協助 LLM 判斷該段發生在哪個場景）。"""
    return _format_named_entries(scenes, separator=":")


def _scene_catalog_block(scenes: dict | None) -> tuple[str, str]:
    """根據 scenes 清單回 (catalog_xml, rule_text):

    - 0 個場景: 兩者皆為空字串(不注入 catalog 區塊與規則,避免浪費 token)
    - 1 個或多個: catalog 注入 + 規則要求 LLM 從白名單選或填 null
    """
    if not scenes:
        return "", ""

    scene_names = list(scenes.keys())
    catalog_xml = (
        "<scenes_catalog>\n"
        f"{_format_scene_names(scenes)}\n"
        "</scenes_catalog>\n\n"
        "scenes_catalog 為本專案已註冊的場景清單；每個場景已有設計圖（scene_sheet），"
        "下游會把對應 sheet 圖送入生圖 API 作為環境一致性參考。\n"
    )
    rule_text = (
        "本片段發生的場景名稱，用於下游反查 scene_sheet 參考圖：\n"
        f"   - 可選值:[{', '.join(scene_names)}] 或 null\n"
        "   - **必須**來自 `<scenes_catalog>` 清單；未列於清單的場景名稱（例如「書房」「客廳」如未登記）一律填 null。\n"
        "   - 若該段內容與清單中任一場景**都不符**（例如純人物特寫、抽象空鏡、室內未登記場所），填 null，**禁止強行套用**。\n"
        "   - 同一個場景可被多段共用（例如多個鏡頭都發生在天安門 → 都填同一個值）。\n"
    )
    return catalog_xml, rule_text


def _user_instruction_block(extra_instruction: str | None) -> str:
    """使用者於 WebUI 輸入的自由提示詞，包成高優先級區塊插入 prompt。

    回傳空字串代表使用者未填寫。內容只影響改編語氣/取向，
    不得凌駕段數/場景數、segment_id 格式、逐段對應等硬約束。
    """
    text = (extra_instruction or "").strip()
    if not text:
        return ""
    return f"""

## 使用者額外指示（高優先級，但不得違反上方硬約束）

以下為使用者針對本次劇本生成提出的額外要求，請在不違反「段數/場景數約束」「ID 格式」「逐段對應原文」等硬性規則的前提下，盡量遵循：

<user_instruction>
{text}
</user_instruction>
"""


def _count_step1_rows(step1_md: str, row_prefix: str) -> int:
    """數 step1 markdown 表格的資料行數。

    narration 表格行以 ``| G`` 開頭（G01/G02...），drama 以 ``| E`` 開頭（E1S01...）。
    若數不出來（檔案空、被破壞）回 0，呼叫端可改為弱約束（不寫死段數）。
    """
    if not step1_md:
        return 0
    return sum(1 for line in step1_md.splitlines() if line.lstrip().startswith(f"| {row_prefix}"))


def build_narration_prompt(
    project_overview: dict,
    style: str,
    style_description: str,
    characters: dict,
    clues: dict,
    segments_md: str,
    supported_durations: list[int] | None = None,
    default_duration: int | None = None,
    aspect_ratio: str = "9:16",
    episode: int | None = None,
    scenes: dict | None = None,
    extra_instruction: str | None = None,
) -> str:
    """
    構建說書模式的 Prompt

    Args:
        project_overview: 專案概述（synopsis, genre, theme, world_setting）
        style: 視覺風格標籤
        style_description: 風格描述
        characters: 角色字典（僅用於提取名稱列表）
        clues: 線索字典（僅用於提取名稱列表）
        segments_md: Step 1 的 Markdown 內容

    Returns:
        構建好的 Prompt 字串
    """
    character_names = list(characters.keys())
    clue_names = list(clues.keys())
    expected_segments = _count_step1_rows(segments_md, "G")
    episode_no = episode if episode is not None else 1
    scenes_catalog_xml, scene_field_rule = _scene_catalog_block(scenes)

    count_block = (
        f"""

## 鋼定段數約束（最高優先級）

下方 `<segments>` 區塊內共有 **{expected_segments}** 段（G01 ~ G{expected_segments:02d}），
你輸出的 JSON `segments` 陣列**必須恰好包含 {expected_segments} 個元素**，一段不多、一段不少。

- 第 i 個輸出 segment 對應 step1 表格的第 i 行（G{{i:02d}}）。
- `segment_id` 必須形如 `E{episode_no}S{{i:02d}}`（集數固定為 {episode_no}，序號從 01 遞增到 {expected_segments:02d}）。
- `novel_text` 必須**逐字複製** step1 表格中對應行的「原文」欄位，不得改寫、合併、刪減。
- 若你覺得內容相似想合併，**禁止**——逐段對應是硬要求。
- 若 token 不夠導致只能輸出部分段，**仍須以縮減描述細節為優先**，保留段數完整。
"""
        if expected_segments > 0
        else ""
    )

    prompt = f"""你的任務是為短影片生成分鏡劇本。請仔細遵循以下指示：

{PROMPT_LANGUAGE_RULE}
**集數：本次處理的是第 {episode_no} 集,所有 segment_id 必須使用 `E{episode_no}S{{序號}}` 格式,不得寫成其他集數。**
{count_block}{_user_instruction_block(extra_instruction)}
1. 你將獲得故事概述、視覺風格、角色列表、線索列表，以及已拆分的小說片段。

2. 為每個片段生成：
   - image_prompt：第一幀的影象生成提示詞（中文描述）
   - video_prompt：動作和音效的影片生成提示詞（中文描述）

<overview>
{project_overview.get("synopsis", "")}

題材型別：{project_overview.get("genre", "")}
核心主題：{project_overview.get("theme", "")}
世界觀設定：{project_overview.get("world_setting", "")}
</overview>

<style>
風格：{style}
描述：{style_description}
</style>

<characters>
{_format_character_names(characters)}
</characters>

<clues>
{_format_clue_names(clues)}
</clues>

{scenes_catalog_xml}<segments>
{segments_md}
</segments>

segments 為片段拆分表，每行是一個片段，包含：
- 片段 ID：格式為 E{{集數}}S{{序號}}
- 小說原文：必須原樣保留到 novel_text 欄位
- {_format_duration_constraint(supported_durations or [4, 6, 8], default_duration)}
- 是否有對話：用於判斷是否需要填寫 video_prompt.dialogue
- 是否為 segment_break：場景切換點，需設定 segment_break 為 true

3. 為每個片段生成時，遵循以下規則：

a. **novel_text**：原樣複製小說原文，不做任何修改。

b. **characters_in_segment**：列出本片段中實際出場的角色名稱。
   - 可選值：[{", ".join(character_names)}]
   - 必須**忠實對照** characters 區塊的描述，根據小說正文判斷實際出場者；不要因為列表第一項就盲目選用。
   - 若小說正文使用代稱、別名或第三人稱，仍應對照描述歸位到對應角色。
   - 若片段無任何已定義角色出場（如純風景描述），填空陣列 []。

c. **clues_in_segment**：列出本片段中可見或被提及的道具線索名稱。
   - 可選值：[{", ".join(clue_names)}]
   - 必須**忠實標註**：只要小說正文的描寫匹配 clues 區塊中某個道具線索的描述（包含別稱、外觀特徵、所在地點），就要列入。
   - 道具線索若在畫面中可見，務必填入，後續會作為視覺參考圖；遺漏會導致影像生成時道具走樣。
   - 若片段確實未涉及任何已定義線索，填空陣列 []。

{("c2. **scene_in_segment**：" + scene_field_rule) if scene_field_rule else ""}
d. **image_prompt**：生成包含以下欄位的物件：
   - scene：用中文描述此刻畫面中的具體場景。
     **提到角色時必須先寫角色名，再用括號附一句精簡外觀**（例：「比比拉布（香蕉造型的貓）」、「我的刀盾（柴犬造型）」），
     角色名必須與 characters_in_segment 中的名稱完全一致；接著描述角色的位置、姿態、表情、服裝細節，以及可見的環境元素和物品。
     **環境一致性（關鍵）**：如果該片段的 `scene_in_segment` 填寫了某個標準場景（非 null），在此描述環境與背景時，**必須參考並融合** `<scenes_catalog>` 中該場景的設定描述（如擺設、色調、特定道具、氛圍等），保持場景視覺的一致性。
     聚焦當下瞬間的可見畫面。僅描述攝像機能夠捕捉到的具體視覺元素。
     確保描述避免超出此刻畫面的元素。排除比喻、隱喻、抽象情緒詞、主觀評價、多場景切換等無法直接渲染的描述。
     畫面應自包含，不暗示過去事件或未來發展。
   - composition：
     - shot_type：鏡頭型別（Extreme Close-up, Close-up, Medium Close-up, Medium Shot, Medium Long Shot, Long Shot, Extreme Long Shot, Over-the-shoulder, Point-of-view）
     - lighting：用中文描述具體的光源型別、方向和色溫（如"左側窗戶透入的暖黃色晨光"）
     - ambiance：用中文描述可見的環境效果（如"薄霧瀰漫"、"塵埃飛揚"），避免抽象情緒詞

e. **video_prompt**：生成包含以下欄位的物件：
   - action：用中文精確描述該時長內主體的具體動作——身體移動、手勢變化、表情轉換。
     提到角色時同樣先寫角色名（如「比比拉布縮成圓球」），名稱須與 characters_in_segment 一致。如果出場的角色或線索道具在 `<characters>` 或 `<clues>` 中有特定的動作/使用特徵，亦請在動作中合理體現。
     聚焦單一連貫動作，確保在指定時長內可完成。
     排除多場景切換、蒙太奇、快速剪輯等單次生成無法實現的效果。
     排除比喻性動作描述（如"像蝴蝶般飛舞"）。
   - camera_motion：鏡頭運動（Static, Pan Left, Pan Right, Tilt Up, Tilt Down, Zoom In, Zoom Out, Tracking Shot）
     每個片段僅選擇一種鏡頭運動。
   - ambiance_audio：用中文描述畫內音（diegetic sound）——環境聲、腳步聲、物體聲音。
     僅描述場景內真實存在的聲音。排除音樂、BGM、旁白、畫外音。
   - dialogue：{{speaker, line}} 陣列。僅當原文有引號對話時填寫。speaker 必須來自 characters_in_segment。

f. **segment_break**：如果在片段表中標記為"是"，則設為 true。

g. **duration_seconds**：使用片段表中的時長。

h. **transition_to_next**：預設為 "cut"。

目標：建立生動、視覺一致的分鏡提示詞，用於指導 AI 影象和影片生成。保持創意、具體，並忠於原文。
"""
    return prompt


def build_drama_prompt(
    project_overview: dict,
    style: str,
    style_description: str,
    characters: dict,
    clues: dict,
    scenes_md: str,
    supported_durations: list[int] | None = None,
    default_duration: int | None = None,
    aspect_ratio: str = "16:9",
    episode: int | None = None,
    scenes: dict | None = None,
    extra_instruction: str | None = None,
) -> str:
    """
    構建劇集動畫模式的 Prompt

    Args:
        project_overview: 專案概述
        style: 視覺風格標籤
        style_description: 風格描述
        characters: 角色字典
        clues: 線索字典
        scenes_md: Step 1 的 Markdown 內容

    Returns:
        構建好的 Prompt 字串
    """
    character_names = list(characters.keys())
    clue_names = list(clues.keys())
    expected_scenes = _count_step1_rows(scenes_md, f"E{episode if episode is not None else ''}")
    if expected_scenes == 0:
        # fallback：drama 規範化表頭以 | E{episode}S 開頭，找不到該集數時用泛 E 前綴再試
        expected_scenes = _count_step1_rows(scenes_md, "E")
    episode_no = episode if episode is not None else 1
    scenes_catalog_xml, scene_field_rule = _scene_catalog_block(scenes)

    count_block = (
        f"""

## 鋼定場景數約束（最高優先級）

下方 `<scenes>` 區塊內共有 **{expected_scenes}** 個場景，
你輸出的 JSON `scenes` 陣列**必須恰好包含 {expected_scenes} 個元素**，一個不多、一個不少。

- 第 i 個輸出 scene 對應 step1 表格的第 i 行。
- `scene_id` 必須形如 `E{episode_no}S{{序號:02d}}`（集數固定為 {episode_no}，序號從 01 遞增到 {expected_scenes:02d}），與表格列出的 ID 對齊。
- 場景描述要**忠實取材**自 step1 表格的「場景描述」欄位，不得擅自合併或刪減場景。
- 若 token 不夠導致只能輸出部分場景，**仍須以縮減描述細節為優先**，保留場景數完整。
"""
        if expected_scenes > 0
        else ""
    )

    prompt = f"""你的任務是為劇集動畫生成分鏡劇本。請仔細遵循以下指示：

{PROMPT_LANGUAGE_RULE}
**集數：本次處理的是第 {episode_no} 集,所有 scene_id 必須使用 `E{episode_no}S{{序號}}` 格式,不得寫成其他集數。**
{count_block}{_user_instruction_block(extra_instruction)}
1. 你將獲得故事概述、視覺風格、角色列表、線索列表，以及已拆分的場景列表。

2. 為每個場景生成：
   - image_prompt：第一幀的影象生成提示詞（中文描述）
   - video_prompt：動作和音效的影片生成提示詞（中文描述）

<overview>
{project_overview.get("synopsis", "")}

題材型別：{project_overview.get("genre", "")}
核心主題：{project_overview.get("theme", "")}
世界觀設定：{project_overview.get("world_setting", "")}
</overview>

<style>
風格：{style}
描述：{style_description}
</style>

<characters>
{_format_character_names(characters)}
</characters>

<clues>
{_format_clue_names(clues)}
</clues>

{scenes_catalog_xml}<scenes>
{scenes_md}
</scenes>

scenes 為場景拆分表，每行是一個場景，包含：
- 場景 ID：格式為 E{{集數}}S{{序號}}
- 場景描述：劇本改編後的場景畫面內容
- 旁白：該場景的旁白／獨白配音文字（「-」表示無）——**請原樣填入該場景的 narration_text 欄位**
- 對話：角色直接對白，格式 `角色名：台詞`（「-」表示無）——**請解析後填入該場景的 video_prompt.dialogue 陣列**
- {_format_duration_constraint(supported_durations or [4, 6, 8], default_duration)}
- 是否為 segment_break：場景切換點，需設定 segment_break 為 true

3. 為每個場景生成時，遵循以下規則：

a. **characters_in_scene**：列出本場景中實際出場的角色名稱。
   - 可選值：[{", ".join(character_names)}]
   - 必須**忠實對照** characters 區塊的描述，根據場景內容判斷實際出場者；不要因為列表第一項就盲目選用。
   - 若場景使用代稱、別名、人稱代名詞或第三人稱（例如「老人」、「這名書生」），**必須**主動對照描述，映射並歸位到列表中的標準名稱，不能因為正文沒有直接寫出標準名稱而漏填。
   - 若場景無任何已定義角色出場，填空陣列 []。

b. **clues_in_scene**：列出本場景中可見或被提及的道具線索名稱。
   - 可選值：[{", ".join(clue_names)}]
   - 必須**忠實標註**：只要場景描寫匹配 clues 區塊中某個道具線索的描述（包含別稱、外觀特徵、所在地點），**必須**映射並列入對應的標準名稱，不可遺漏。
   - 道具線索若在畫面中可見，務必填入，後續會作為視覺參考圖；遺漏會導致影像生成時道具走樣。
   - 若場景確實未涉及任何已定義線索，填空陣列 []。

{("b2. **scene_in_scene**：" + scene_field_rule) if scene_field_rule else ""}

c. **image_prompt**：生成包含以下欄位的物件：
   - scene：用中文描述此刻畫面中的具體場景。{_format_aspect_ratio_desc(aspect_ratio)}。
     **提到角色時必須先寫角色名，再用括號附一句精簡外觀**（例：「比比拉布（香蕉造型的貓）」、「我的刀盾（柴犬造型）」），
     角色名必須與 characters_in_scene 中的名稱完全一致；接著描述角色的位置、姿態、表情、服裝細節，以及可見的環境元素和物品。
     **環境一致性（關鍵）**：如果該場景的 `scene_in_scene` 填寫了某個標準場景（非 null），在此描述環境與背景時，**必須參考並融合** `<scenes_catalog>` 中該場景的設定描述（如擺設、色調、特定道具、氛圍等），保持場景視覺的一致性。
     聚焦當下瞬間的可見畫面。僅描述攝像機能夠捕捉到的具體視覺元素。
     確保描述避免超出此刻畫面的元素。排除比喻、隱喻、抽象情緒詞、主觀評價、多場景切換等無法直接渲染的描述。
     畫面應自包含，不暗示過去事件或未來發展。
   - composition：
     - shot_type：鏡頭型別（Extreme Close-up, Close-up, Medium Close-up, Medium Shot, Medium Long Shot, Long Shot, Extreme Long Shot, Over-the-shoulder, Point-of-view）
     - lighting：用中文描述具體的光源型別、方向和色溫（如"左側窗戶透入的暖黃色晨光"）
     - ambiance：用中文描述可見的環境效果（如"薄霧瀰漫"、"塵埃飛揚"），避免抽象情緒詞

d. **video_prompt**：生成包含以下欄位的物件：
   - action：用中文精確描述該時長內主體的具體動作——身體移動、手勢變化、表情轉換。
     提到角色時同樣先寫角色名（如「比比拉布縮成圓球」），名稱須與 characters_in_scene 中的一致。如果出場的角色或線索道具在 `<characters>` 或 `<clues>` 中有特定的動作/使用特徵，亦請在動作中合理體現。
     聚焦單一連貫動作，確保在指定時長內可完成。
     排除多場景切換、蒙太奇、快速剪輯等單次生成無法實現的效果。
     排除比喻性動作描述（如"像蝴蝶般飛舞"）。
   - camera_motion：鏡頭運動（Static, Pan Left, Pan Right, Tilt Up, Tilt Down, Zoom In, Zoom Out, Tracking Shot）
     每個片段僅選擇一種鏡頭運動。
   - ambiance_audio：用中文描述畫內音（diegetic sound）——環境聲、腳步聲、物體聲音。
     僅描述場景內真實存在的聲音。排除音樂、BGM、旁白、畫外音。
   - dialogue：{{speaker, line}} 陣列。**直接解析場景表「對話」欄**（格式 `角色名：台詞`，多句分行）填入；
     speaker 必須來自 characters_in_scene。若「對話」欄為「-」則填空陣列 []。**不要把旁白填進 dialogue**。

e. **scene_description**：原樣沿用場景表的「場景描述」欄內容。

f. **narration_text**：原樣沿用場景表的「旁白」欄內容（旁白／獨白／畫外音配音文字）；若為「-」則填空字串 ""。

g. **segment_break**：如果在場景表中標記為"是"，則設為 true。

h. **duration_seconds**：使用場景表中的時長。

i. **scene_type**：預設為"劇情"。

j. **transition_to_next**：預設為 "cut"。

目標：建立生動、視覺一致的分鏡提示詞，用於指導 AI 影象和影片生成。保持創意、具體，適合{_format_aspect_ratio_desc(aspect_ratio)}動畫呈現。
"""
    return prompt
