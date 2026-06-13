"""
BytePlus ModelArk 共享工具模組

供 text_backends / image_backends / video_backends / providers 複用。

包含：
- ARK_BASE_URL — BytePlus ModelArk API 基礎 URL
- resolve_ark_api_key — API Key 解析（含環境變數 fallback）
- create_ark_client — Ark 客戶端工廠
"""

from __future__ import annotations

import os

ARK_BASE_URL = "https://ark.ap-southeast.bytepluses.com/api/v3"


def resolve_ark_api_key(api_key: str | None = None) -> str:
    """解析 ModelArk API Key，支援環境變數 fallback。"""
    resolved = api_key or os.environ.get("BYTEPLUS_API_KEY") or os.environ.get("ARK_API_KEY")
    if not resolved:
        raise ValueError("BytePlus ModelArk API Key 未提供。請在「全域性設定 → 供應商」頁面配置 API Key。")
    return resolved


def create_ark_client(*, api_key: str | None = None):
    """建立 ModelArk 客戶端，統一校驗 api_key 並構造。"""
    from volcenginesdkarkruntime import Ark

    return Ark(base_url=ARK_BASE_URL, api_key=resolve_ark_api_key(api_key))
