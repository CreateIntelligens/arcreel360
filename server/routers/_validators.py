"""共享校驗函式，供多個 router 複用。"""

from __future__ import annotations

from fastapi import HTTPException

from lib.config.registry import PROVIDER_REGISTRY
from lib.providers import normalize_provider_id


def validate_backend_value(value: str, field_name: str) -> None:
    """校驗 ``provider/model`` 格式的 backend 欄位值。

    也接受舊格式的單 provider 名（如 ``"gemini"``），以相容存量專案。

    Raises:
        HTTPException(400): 格式不合法或 provider 不在登錄檔中。
    """
    if "/" not in value:
        normalized = normalize_provider_id(value)
        if normalized in PROVIDER_REGISTRY:
            return  # 舊格式或裸 registry id，下游 _normalize_provider_id() 處理
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} 格式應為 provider/model",
        )
    provider_id = value.split("/", 1)[0]
    normalized = normalize_provider_id(provider_id)
    if normalized not in PROVIDER_REGISTRY and not provider_id.startswith("custom-"):
        raise HTTPException(
            status_code=400,
            detail=f"未知供應商: {provider_id}",
        )
