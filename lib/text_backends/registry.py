"""文字後端註冊與工廠。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lib.text_backends.base import TextBackend

_BACKEND_FACTORIES: dict[str, Callable[..., TextBackend]] = {}


def register_backend(name: str, factory: Callable[..., TextBackend]) -> None:
    """註冊一個文字後端工廠函式。"""
    _BACKEND_FACTORIES[name] = factory


def create_backend(name: str, **kwargs: Any) -> TextBackend:
    """根據名稱建立文字後端例項。"""
    if name not in _BACKEND_FACTORIES:
        raise ValueError(f"Unknown text backend: {name}")
    return _BACKEND_FACTORIES[name](**kwargs)


def get_registered_backends() -> list[str]:
    """返回所有已註冊的後端名稱。"""
    return list(_BACKEND_FACTORIES.keys())
