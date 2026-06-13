"""影片生成服務層公共 API。"""

from lib.providers import PROVIDER_AI360, PROVIDER_BYTEPLUS, PROVIDER_GEMINI, PROVIDER_GROK
from lib.video_backends.base import (
    VideoBackend,
    VideoCapability,
    VideoGenerationRequest,
    VideoGenerationResult,
)
from lib.video_backends.registry import create_backend, get_registered_backends, register_backend

__all__ = [
    "PROVIDER_AI360",
    "PROVIDER_BYTEPLUS",
    "PROVIDER_GEMINI",
    "PROVIDER_GROK",
    "PROVIDER_OPENAI",
    "VideoBackend",
    "VideoCapability",
    "VideoGenerationRequest",
    "VideoGenerationResult",
    "create_backend",
    "get_registered_backends",
    "register_backend",
]

# Auto-register backends
# Gemini: google-genai is a core dependency, import failure is a real error
from lib.video_backends.gemini import GeminiVideoBackend

register_backend(PROVIDER_GEMINI, GeminiVideoBackend)

# BytePlus ModelArk: volcengine-python-sdk[ark] is a project dependency
from lib.video_backends.ark import ArkVideoBackend

register_backend(PROVIDER_BYTEPLUS, ArkVideoBackend)

# Grok: xai-sdk
from lib.video_backends.grok import GrokVideoBackend

register_backend(PROVIDER_GROK, GrokVideoBackend)

# OpenAI Sora
from lib.providers import PROVIDER_OPENAI
from lib.video_backends.openai import OpenAIVideoBackend

register_backend(PROVIDER_OPENAI, OpenAIVideoBackend)

# ai360 Video Studio: 自託管 REST 服務（帳密登入 + 輪詢）
from lib.video_backends.ai360 import AI360VideoBackend

register_backend(PROVIDER_AI360, AI360VideoBackend)
