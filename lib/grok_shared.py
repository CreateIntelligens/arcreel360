"""
Grok (xAI) 共享工具模組

供 text_backends / image_backends / video_backends 複用。

包含：
- create_grok_client — xAI AsyncClient 客戶端工廠
"""

from __future__ import annotations


def create_grok_client(*, api_key: str | None = None):
    """建立 xAI AsyncClient，統一校驗和構造。"""
    import xai_sdk

    if not api_key:
        raise ValueError("XAI_API_KEY 未設定\n請在系統配置頁中配置 xAI API Key")
    return xai_sdk.AsyncClient(api_key=api_key)
