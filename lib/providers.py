"""供應商名稱常量，image_backends / video_backends 共用。"""

from typing import Literal

PROVIDER_GEMINI = "gemini"
PROVIDER_BYTEPLUS = "byteplus"
PROVIDER_ARK = PROVIDER_BYTEPLUS  # 舊程式碼匯入相容；新 provider id 是 byteplus。
PROVIDER_GROK = "grok"
PROVIDER_OPENAI = "openai"
PROVIDER_AI360 = "ai360"

CallType = Literal["image", "video", "text"]
CALL_TYPE_IMAGE: CallType = "image"
CALL_TYPE_VIDEO: CallType = "video"
CALL_TYPE_TEXT: CallType = "text"

LEGACY_PROVIDER_ALIASES: dict[str, str] = {
    "ark": PROVIDER_BYTEPLUS,
    "seedance": PROVIDER_BYTEPLUS,
    "gemini": "gemini-aistudio",
    "vertex": "gemini-vertex",
}


def normalize_provider_id(provider_id: str) -> str:
    """Normalize legacy provider ids to current registry provider ids."""
    return LEGACY_PROVIDER_ALIASES.get(provider_id, provider_id)
