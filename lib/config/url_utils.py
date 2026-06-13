"""URL 歸一化工具函式。"""

from __future__ import annotations

import re


def ensure_openai_base_url(url: str | None) -> str | None:
    """自動補全 OpenAI 相容 API 的 /v1 路徑字尾。

    使用者可能只填了 ``https://api.example.com``，但 OpenAI SDK 期望
    ``https://api.example.com/v1``。本函式在缺少版本路徑時自動追加。
    """
    if not url:
        return url
    stripped = url.strip().rstrip("/")
    if not re.search(r"/v\d+$", stripped):
        stripped += "/v1"
    return stripped


def normalize_base_url(url: str | None) -> str | None:
    """確保 base_url 以 / 結尾。

    Google genai SDK 的 http_options.base_url 要求尾部帶 /，
    否則請求路徑拼接會失敗。預置 Gemini 後端使用此函式。
    """
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if not url.endswith("/"):
        url += "/"
    return url


def ensure_google_base_url(url: str | None) -> str | None:
    """規範化 Google genai SDK 的 base_url。

    Google genai SDK 會自動在 base_url 後拼接 ``api_version``（預設 ``v1beta``）。
    如果使用者誤填了 ``https://example.com/v1beta``，SDK 會拼出
    ``https://example.com/v1beta/v1beta/models``，導致請求失敗。

    本函式剝離末尾的版本路徑（如 ``/v1beta``、``/v1``），並確保尾部帶 ``/``。
    """
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    url = url.rstrip("/")
    # 剝離末尾的版本路徑（/v1, /v1beta, /v1alpha 等）
    url = re.sub(r"/v\d+\w*$", "", url)
    if not url.endswith("/"):
        url += "/"
    return url
