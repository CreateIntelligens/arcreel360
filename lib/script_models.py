"""
script_models.py - 劇本資料模型

使用 Pydantic 定義劇本的資料結構，用於：
1. Gemini API 的 response_schema（Structured Outputs）
2. 輸出驗證
"""

from typing import Literal

from pydantic import BaseModel, Field

# ============ 列舉型別定義 ============

ShotType = Literal[
    "Extreme Close-up",
    "Close-up",
    "Medium Close-up",
    "Medium Shot",
    "Medium Long Shot",
    "Long Shot",
    "Extreme Long Shot",
    "Over-the-shoulder",
    "Point-of-view",
]

CameraMotion = Literal[
    "Static",
    "Pan Left",
    "Pan Right",
    "Tilt Up",
    "Tilt Down",
    "Zoom In",
    "Zoom Out",
    "Tracking Shot",
]


class Dialogue(BaseModel):
    """對話條目"""

    speaker: str = Field(description="說話人名稱")
    line: str = Field(description="對話內容")


class Composition(BaseModel):
    """構圖資訊"""

    shot_type: ShotType = Field(description="鏡頭型別")
    lighting: str = Field(description="光線描述，包含光源、方向和氛圍")
    ambiance: str = Field(description="整體氛圍，與情緒基調匹配")


class ImagePrompt(BaseModel):
    """分鏡圖生成 Prompt"""

    scene: str = Field(description="場景描述：角色位置、表情、動作、環境細節")
    composition: Composition = Field(description="構圖資訊")


class VideoPrompt(BaseModel):
    """影片生成 Prompt"""

    action: str = Field(description="動作描述：角色在該片段內的具體動作")
    camera_motion: CameraMotion = Field(description="鏡頭運動")
    ambiance_audio: str = Field(description="環境音效：僅描述場景內的聲音，禁止 BGM")
    dialogue: list[Dialogue] = Field(default_factory=list, description="對話列表，僅當原文有引號對話時填寫")


class GeneratedAssets(BaseModel):
    """生成資源狀態（初始化為空）"""

    storyboard_image: str | None = Field(default=None, description="分鏡圖路徑")
    video_clip: str | None = Field(default=None, description="影片片段路徑")
    video_uri: str | None = Field(default=None, description="影片 URI")
    status: Literal["pending", "storyboard_ready", "completed"] = Field(default="pending", description="生成狀態")


# ============ 說書模式（Narration） ============


class NarrationSegment(BaseModel):
    """說書模式的片段"""

    segment_id: str = Field(description="片段 ID，格式 E{集}S{序號} 或 E{集}S{序號}_{子序號}")
    episode: int = Field(description="所屬劇集")
    duration_seconds: int = Field(ge=1, le=60, description="片段時長（秒）")
    segment_break: bool = Field(default=False, description="是否為場景切換點")
    novel_text: str = Field(description="小說原文（必須原樣保留，用於後期配音）")
    characters_in_segment: list[str] = Field(description="出場角色名稱列表")
    clues_in_segment: list[str] = Field(default_factory=list, description="出場線索名稱列表")
    scene_in_segment: str | None = Field(default=None, description="所屬場景名稱（可選，對應 project.json scenes）")
    image_prompt: ImagePrompt = Field(description="分鏡圖生成提示詞")
    video_prompt: VideoPrompt = Field(description="影片生成提示詞")
    transition_to_next: Literal["cut", "fade", "dissolve"] = Field(default="cut", description="轉場型別")
    note: str | None = Field(default=None, description="使用者備註（不參與生成）")
    reference_image: str | None = Field(default=None, description="分鏡參考圖路徑")
    storyboard_sheet: str | None = Field(default=None, description="分鏡當前參考圖（指向 v0）")
    generated_assets: GeneratedAssets = Field(default_factory=GeneratedAssets, description="生成資源狀態")


class NovelInfo(BaseModel):
    """小說來源資訊"""

    title: str = Field(description="小說標題")
    chapter: str = Field(description="章節名稱")


class NarrationEpisodeScript(BaseModel):
    """說書模式劇集指令碼"""

    episode: int = Field(description="劇集編號")
    title: str = Field(description="劇集標題")
    content_mode: Literal["narration"] = Field(default="narration", description="內容模式")
    duration_seconds: int = Field(default=0, description="總時長（秒）")
    summary: str = Field(description="劇集摘要")
    novel: NovelInfo = Field(description="小說來源資訊")
    segments: list[NarrationSegment] = Field(description="片段列表")


# ============ 劇集動畫模式（Drama） ============


class DramaScene(BaseModel):
    """劇集動畫模式的場景"""

    scene_id: str = Field(description="場景 ID，格式 E{集}S{序號} 或 E{集}S{序號}_{子序號}")
    duration_seconds: int = Field(default=8, ge=1, le=60, description="場景時長（秒）")
    segment_break: bool = Field(default=False, description="是否為場景切換點")
    scene_type: str = Field(default="劇情", description="場景型別")
    scene_description: str = Field(
        default="", description="場景對應的原文／故事內容，供分鏡與影片提示詞參考（對應說書模式的 novel_text）"
    )
    narration_text: str = Field(
        default="", description="場景的旁白／配音文字，用於後期配音（對應 Step 1 的「旁白」欄）"
    )
    characters_in_scene: list[str] = Field(description="出場角色名稱列表")
    clues_in_scene: list[str] = Field(default_factory=list, description="出場線索名稱列表")
    scene_in_scene: str | None = Field(default=None, description="所屬場景名稱（可選，對應 project.json scenes）")
    image_prompt: ImagePrompt = Field(description="分鏡圖生成提示詞")
    video_prompt: VideoPrompt = Field(description="影片生成提示詞")
    transition_to_next: Literal["cut", "fade", "dissolve"] = Field(default="cut", description="轉場型別")
    note: str | None = Field(default=None, description="使用者備註（不參與生成）")
    reference_image: str | None = Field(default=None, description="分鏡參考圖路徑")
    storyboard_sheet: str | None = Field(default=None, description="分鏡當前參考圖（指向 v0）")
    generated_assets: GeneratedAssets = Field(default_factory=GeneratedAssets, description="生成資源狀態")


class DramaEpisodeScript(BaseModel):
    """劇集動畫模式劇集指令碼"""

    episode: int = Field(description="劇集編號")
    title: str = Field(description="劇集標題")
    content_mode: Literal["drama"] = Field(default="drama", description="內容模式")
    duration_seconds: int = Field(default=0, description="總時長（秒）")
    summary: str = Field(description="劇集摘要")
    novel: NovelInfo = Field(description="小說來源資訊")
    scenes: list[DramaScene] = Field(description="場景列表")


# ============ 空骨架工廠（供「手動建立空劇集」使用） ============


def _empty_image_prompt() -> ImagePrompt:
    return ImagePrompt(scene="", composition=Composition(shot_type="Medium Shot", lighting="", ambiance=""))


def _empty_video_prompt() -> VideoPrompt:
    return VideoPrompt(action="", camera_motion="Static", ambiance_audio="", dialogue=[])


def empty_narration_script(episode: int, title: str) -> dict:
    """產生說書模式的空骨架劇本 dict（segments 為空），所有必填欄位填合理空值。"""
    return NarrationEpisodeScript(
        episode=episode,
        title=title,
        summary="",
        novel=NovelInfo(title=title, chapter=""),
        segments=[],
    ).model_dump()


def empty_drama_script(episode: int, title: str) -> dict:
    """產生劇集動畫模式的空骨架劇本 dict（scenes 為空），所有必填欄位填合理空值。"""
    return DramaEpisodeScript(
        episode=episode,
        title=title,
        summary="",
        novel=NovelInfo(title=title, chapter=""),
        scenes=[],
    ).model_dump()


def empty_narration_segment(episode: int, segment_id: str) -> dict:
    """產生一個空的說書片段 dict，所有必填欄位填合理空值（duration 預設 4 秒）。"""
    return NarrationSegment(
        segment_id=segment_id,
        episode=episode,
        duration_seconds=4,
        novel_text="",
        characters_in_segment=[],
        image_prompt=_empty_image_prompt(),
        video_prompt=_empty_video_prompt(),
    ).model_dump()


def empty_drama_scene(episode: int, scene_id: str) -> dict:
    """產生一個空的劇集動畫場景 dict，所有必填欄位填合理空值（duration 預設 8 秒）。

    episode 參數僅為與 empty_narration_segment 一致；DramaScene 本身不帶 episode 欄位。
    """
    _ = episode
    return DramaScene(
        scene_id=scene_id,
        duration_seconds=8,
        characters_in_scene=[],
        image_prompt=_empty_image_prompt(),
        video_prompt=_empty_video_prompt(),
    ).model_dump()
