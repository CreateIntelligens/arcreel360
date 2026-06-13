"""統一日誌配置。"""

import logging
import os

_HANDLER_ATTR = "_arcreel_logging"


def setup_logging(level: str | None = None) -> None:
    """配置根 logger。

    Args:
        level: 日誌級別字串（DEBUG/INFO/WARNING/ERROR）。
               如未提供，從環境變數 LOG_LEVEL 讀取，預設 INFO。
    """
    if level is None:
        level = os.environ.get("LOG_LEVEL", "INFO")

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # 冪等：避免重複新增 handler
    if any(getattr(h, _HANDLER_ATTR, False) for h in root.handlers):
        return

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    setattr(handler, _HANDLER_ATTR, True)
    root.addHandler(handler)

    # 統一 uvicorn 的日誌格式，避免兩種格式並存
    for name in ("uvicorn", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True

    # 禁用 uvicorn.access：請求日誌由 app.py 的 middleware 統一處理
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.disabled = True

    # 抑制 aiosqlite 的 DEBUG 噪音（每次 SQL 操作都會輸出兩行日誌）
    logging.getLogger("aiosqlite").setLevel(max(numeric_level, logging.INFO))
