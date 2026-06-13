"""自定義供應商模組。"""

CUSTOM_PROVIDER_PREFIX = "custom-"


def make_provider_id(db_id: int) -> str:
    """構造自定義供應商的 provider_id 字串，如 'custom-3'。"""
    return f"{CUSTOM_PROVIDER_PREFIX}{db_id}"


def parse_provider_id(provider_id: str) -> int:
    """從 'custom-3' 格式的 provider_id 提取資料庫 ID。

    Raises:
        ValueError: 如果格式不正確
    """
    return int(provider_id.removeprefix(CUSTOM_PROVIDER_PREFIX))


def is_custom_provider(provider_id: str) -> bool:
    """判斷是否為自定義供應商的 provider_id。"""
    return provider_id.startswith(CUSTOM_PROVIDER_PREFIX)
