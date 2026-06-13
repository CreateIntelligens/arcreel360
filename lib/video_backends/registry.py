"""影片後端註冊與工廠。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lib.video_backends.base import VideoBackend

_BACKEND_FACTORIES: dict[str, Callable[..., VideoBackend]] = {}


def register_backend(name: str, factory: Callable[..., VideoBackend]) -> None:
    """註冊一個影片後端工廠函式。"""
    _BACKEND_FACTORIES[name] = factory


def create_backend(name: str, **kwargs: Any) -> VideoBackend:
    """根據名稱建立影片後端例項。"""
    if name not in _BACKEND_FACTORIES:
        raise ValueError(f"Unknown video backend: {name}")
    return _BACKEND_FACTORIES[name](**kwargs)


def get_registered_backends() -> list[str]:
    """返回所有已註冊的後端名稱。"""
    return list(_BACKEND_FACTORIES.keys())
