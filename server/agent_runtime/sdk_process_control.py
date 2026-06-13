"""
Claude SDK client process lifecycle helpers.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_client_process(client: Any) -> Any:
    """Best-effort access to the SDK transport process for fallback kill."""
    transport = getattr(client, "_transport", None)
    if transport is None:
        return None
    return getattr(transport, "_process", None)


def process_pid(process: Any) -> int | None:
    pid = getattr(process, "pid", None)
    return pid if isinstance(pid, int) else None


def process_returncode(process: Any) -> int | None:
    returncode = getattr(process, "returncode", None)
    return returncode if isinstance(returncode, int) else None


async def cancel_task(task: asyncio.Task | None) -> None:
    """Cancel a task and wait for it to finish."""
    if task is None or task.done():
        return
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def wait_for_process_exit(
    process: Any,
    *,
    timeout: float,
) -> bool:
    """Wait for a subprocess to exit within timeout."""
    if process is None:
        return True
    if process_returncode(process) is not None:
        return True
    try:
        await asyncio.wait_for(process.wait(), timeout=timeout)
    except TimeoutError:
        return False
    except Exception:
        logger.warning("等待 Claude 子程序退出失敗", exc_info=True)
        return False
    return process_returncode(process) is not None


async def force_close_client_process(
    session_id: str,
    process: Any,
    *,
    pid: int | None,
    cause: str,
    terminate_wait_timeout: float,
    kill_wait_timeout: float,
) -> bool:
    """Force terminate lingering Claude CLI process."""
    if process is None:
        logger.error(
            "會話斷開失敗且無法訪問底層程序 session_id=%s cause=%s",
            session_id,
            cause,
        )
        return False

    if process_returncode(process) is not None:
        return True

    logger.warning(
        "會話斷開異常，嘗試強制終止 Claude 子程序 session_id=%s pid=%s cause=%s",
        session_id,
        pid,
        cause,
    )
    try:
        process.terminate()
    except ProcessLookupError:
        return True
    except Exception:
        logger.warning(
            "傳送 SIGTERM 失敗 session_id=%s pid=%s",
            session_id,
            pid,
            exc_info=True,
        )
    else:
        if await wait_for_process_exit(process, timeout=terminate_wait_timeout):
            logger.warning(
                "Claude 子程序已透過 SIGTERM 退出 session_id=%s pid=%s returncode=%s",
                session_id,
                pid,
                process_returncode(process),
            )
            return True

    logger.error(
        "Claude 子程序在 SIGTERM 後仍存活，傳送 SIGKILL session_id=%s pid=%s",
        session_id,
        pid,
    )
    try:
        process.kill()
    except ProcessLookupError:
        return True
    except Exception:
        logger.error(
            "傳送 SIGKILL 失敗 session_id=%s pid=%s",
            session_id,
            pid,
            exc_info=True,
        )
        return False

    if await wait_for_process_exit(process, timeout=kill_wait_timeout):
        logger.warning(
            "Claude 子程序已透過 SIGKILL 退出 session_id=%s pid=%s returncode=%s",
            session_id,
            pid,
            process_returncode(process),
        )
        return True

    logger.error(
        "Claude 子程序在 SIGKILL 後仍未退出 session_id=%s pid=%s",
        session_id,
        pid,
    )
    return False
