"""通用重試裝飾器，帶指數退避和隨機抖動。

不依賴任何特定供應商 SDK，可被所有後端複用。
各供應商可透過 retryable_errors 引數注入自己的可重試異常型別。
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random

logger = logging.getLogger(__name__)

# 基礎可重試錯誤（不依賴任何 SDK）
BASE_RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
)

# 字串模式匹配：覆蓋異常型別不在列表中但屬於瞬態的情況（大小寫不敏感）
RETRYABLE_STATUS_PATTERNS = (
    "429",
    "resource_exhausted",
    "500",
    "502",
    "503",
    "504",
    "internalservererror",
    "internal server error",
    "serviceunavailable",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "timed out",
    "timeout",
)

# 預設重試配置，供各後端直接引用，避免魔法數字分散在 9+ 處
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS: tuple[int, ...] = (2, 4, 8)


def _should_retry(exc: Exception, retryable_errors: tuple[type[Exception], ...]) -> bool:
    """判斷異常是否應當重試。"""
    if isinstance(exc, retryable_errors):
        return True
    error_lower = str(exc).lower()
    return any(pattern in error_lower for pattern in RETRYABLE_STATUS_PATTERNS)


def with_retry_async(
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: tuple[int, ...] = DEFAULT_BACKOFF_SECONDS,
    retryable_errors: tuple[type[Exception], ...] = BASE_RETRYABLE_ERRORS,
):
    """非同步函式重試裝飾器，帶指數退避和隨機抖動。"""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if not _should_retry(e, retryable_errors):
                        raise

                    if attempt < max_attempts - 1:
                        backoff_idx = min(attempt, len(backoff_seconds) - 1)
                        base_wait = backoff_seconds[backoff_idx]
                        jitter = random.uniform(0, 2)
                        wait_time = base_wait + jitter
                        logger.warning(
                            "API 呼叫異常: %s - %s",
                            type(e).__name__,
                            str(e)[:200],
                        )
                        logger.warning(
                            "重試 %d/%d, %.1f 秒後...",
                            attempt + 1,
                            max_attempts - 1,
                            wait_time,
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        raise

            raise RuntimeError(f"with_retry_async: max_attempts={max_attempts}，未執行任何嘗試")

        return wrapper

    return decorator
