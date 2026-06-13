"""影片首幀縮圖提取"""

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def extract_video_thumbnail(
    video_path: Path,
    thumbnail_path: Path,
) -> Path | None:
    """
    使用 ffmpeg 提取影片第一幀作為 JPEG 縮圖。

    Args:
        video_path: 影片檔案路徑
        thumbnail_path: 輸出縮圖路徑

    Returns:
        縮圖路徑（成功）或 None（失敗）
    """
    if not video_path.exists():
        return None

    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-i",
            str(video_path),
            "-vframes",
            "1",
            "-q:v",
            "2",
            "-y",
            str(thumbnail_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

        if proc.returncode != 0 or not thumbnail_path.exists():
            return None

        return thumbnail_path
    except Exception:
        logger.warning("提取影片縮圖失敗: %s", video_path, exc_info=True)
        return None
