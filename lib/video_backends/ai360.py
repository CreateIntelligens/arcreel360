"""AI360VideoBackend — ai360 Video Studio 影片生成後端。

ai360 是自託管的影片生成服務，認證流程與其他供應商不同：
以 username/password 登入換取 JWT token（30 天有效），之後所有請求帶
``Authorization: Bearer <token>`` 與 ``X-Project-Id``。

串接流程：
1. POST /api/auth/login          → 取得 JWT token
2. GET  /api/projects            → 取得 project_id（未指定時取第一個）
3. POST /api/assets/upload       → 上傳起始圖（image_to_video，可選）
4. POST /api/video/create        → 建立生成任務，取得 historyId
5. GET  /api/history/{historyId} → 輪詢直到 status=succeeded
6. 下載 task.videoUrl 到本地

詳見 docs/ark-docs/ai360-api.md。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

from lib.providers import PROVIDER_AI360
from lib.retry import with_retry_async
from lib.video_backends.base import (
    IMAGE_MIME_TYPES,
    VideoCapability,
    VideoGenerationRequest,
    VideoGenerationResult,
    download_video,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "ai360-video"

# ai360 支援的比例（base.py 的 aspect_ratio 直接相容此格式）
_SUPPORTED_RATIOS = frozenset({"16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "adaptive"})
_DEFAULT_RATIO = "16:9"

# ai360 支援的解析度
_SUPPORTED_RESOLUTIONS = frozenset({"480p", "720p", "1080p"})
_DEFAULT_RESOLUTION = "720p"

# 輪詢配置
_POLL_INTERVAL_SECONDS = 5
_POLL_TIMEOUT_SECONDS = 600  # 10 分鐘上限（生成通常 1–3 分鐘）

_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})


def _resolve_ratio(aspect_ratio: str) -> str:
    return aspect_ratio if aspect_ratio in _SUPPORTED_RATIOS else _DEFAULT_RATIO


def _resolve_resolution(resolution: str) -> str:
    return resolution if resolution in _SUPPORTED_RESOLUTIONS else _DEFAULT_RESOLUTION


def _clamp_duration(seconds: int) -> int:
    return max(4, min(15, seconds))


def _extract_video_url(task: dict) -> str | None:
    video_url = task.get("videoUrl")
    if video_url:
        return video_url

    outputs = task.get("outputs") or []
    return next((output.get("url") for output in outputs if output.get("kind") == "video"), None)


class AI360VideoBackend:
    """ai360 Video Studio 影片生成後端。"""

    def __init__(
        self,
        *,
        username: str | None = None,
        password: str | None = None,
        base_url: str | None = None,
        project_id: str | None = None,
        model: str | None = None,
    ):
        if not username or not password:
            raise ValueError("ai360 後端需要 username 與 password")
        if not base_url:
            raise ValueError("ai360 後端需要 base_url")

        self._username = username
        self._password = password
        self._base_url = base_url.rstrip("/")
        # project_id 為空字串視為未指定
        self._project_id: str | None = project_id or None
        self._model = model or DEFAULT_MODEL

        # 快取的 JWT token（過期時自動重新登入）
        self._token: str | None = None
        # 並發保護：避免多個 generate 同時觸發重複登入 / project 解析
        self._auth_lock = asyncio.Lock()

        self._capabilities: set[VideoCapability] = {
            VideoCapability.TEXT_TO_VIDEO,
            VideoCapability.IMAGE_TO_VIDEO,
            VideoCapability.GENERATE_AUDIO,
        }

    @property
    def name(self) -> str:
        return PROVIDER_AI360

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[VideoCapability]:
        return self._capabilities

    # ── HTTP 輔助 ──

    def _auth_headers(self, *, with_project: bool = True) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._token}"}
        if with_project and self._project_id:
            headers["X-Project-Id"] = str(self._project_id)
        return headers

    @staticmethod
    def _check_ok(data: dict, context: str) -> dict:
        """校驗回應 ``ok`` 旗標，失敗時拋出帶錯誤訊息的 RuntimeError。"""
        if not data.get("ok", False):
            err = data.get("error", "未知錯誤")
            raise RuntimeError(f"ai360 {context} 失敗: {err}")
        return data

    @with_retry_async()
    async def _login(self) -> None:
        """以帳密登入取得 JWT token。"""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base_url}/api/auth/login",
                json={"username": self._username, "password": self._password},
            )
            resp.raise_for_status()
            data = self._check_ok(resp.json(), "登入")
            token = data.get("token")
            if not token:
                raise RuntimeError("ai360 登入回應未包含 token")
            self._token = token
            logger.info("ai360 登入成功")

    @with_retry_async()
    async def _resolve_project_id(self) -> None:
        """未指定 project_id 時，取第一個專案的 id。"""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self._base_url}/api/projects",
                headers=self._auth_headers(with_project=False),
            )
            resp.raise_for_status()
            data = self._check_ok(resp.json(), "取得專案列表")
            projects = data.get("projects") or []
            if not projects:
                raise RuntimeError("ai360 帳號下沒有可用專案，請先在 ai360 建立專案")
            self._project_id = str(projects[0]["id"])
            logger.info("ai360 自動選用專案 id=%s", self._project_id)

    async def _ensure_auth(self) -> None:
        """確保已登入且已解析 project_id（並發安全）。"""
        async with self._auth_lock:
            if self._token is None:
                await self._login()
            if self._project_id is None:
                await self._resolve_project_id()

    @with_retry_async()
    async def _upload_start_image(self, image_path: Path) -> str:
        """上傳起始圖作為參考素材，返回可在 prompt 引用的 token（如 ``@圖片1``）。"""
        mime = IMAGE_MIME_TYPES.get(image_path.suffix.lower(), "image/png")
        async with httpx.AsyncClient(timeout=120) as client:
            with open(image_path, "rb") as f:
                files = {"file": (image_path.name, f, mime)}
                resp = await client.post(
                    f"{self._base_url}/api/assets/upload",
                    params={"kind": "image"},
                    headers=self._auth_headers(),
                    files=files,
                )
            resp.raise_for_status()
            data = self._check_ok(resp.json(), "上傳起始圖")
        images = (data.get("assets", {}).get("items", {}) or {}).get("image", [])
        if not images:
            raise RuntimeError("ai360 上傳起始圖後未返回素材 token")
        # 取最後一筆（本次新上傳的）token，回退到第一筆
        token = images[-1].get("token") or images[0].get("token")
        if not token:
            raise RuntimeError("ai360 起始圖素材缺少 token")
        logger.info("ai360 起始圖上傳完成: token=%s", token)
        return token

    @with_retry_async()
    async def _create_task(self, payload: dict) -> int:
        """建立生成任務，返回 historyId。"""
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._base_url}/api/video/create",
                headers=self._auth_headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = self._check_ok(resp.json(), "建立任務")
        history_id = data.get("historyId")
        if history_id is None:
            raise RuntimeError("ai360 建立任務回應未包含 historyId")
        return int(history_id)

    @with_retry_async()
    async def _poll_once(self, history_id: int) -> dict:
        """單次查詢任務狀態，返回 task 物件。"""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self._base_url}/api/history/{history_id}",
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            data = self._check_ok(resp.json(), "查詢任務狀態")
        return data.get("task", {}) or {}

    async def _wait_for_completion(self, history_id: int) -> dict:
        """輪詢直到任務進入終態，返回完成的 task 物件。"""
        elapsed = 0
        while elapsed < _POLL_TIMEOUT_SECONDS:
            task = await self._poll_once(history_id)
            status = task.get("status")
            if status == "succeeded":
                return task
            if status in _TERMINAL_STATUSES:
                err = task.get("errorMessage") or status
                raise RuntimeError(f"ai360 影片生成{status}: {err}")
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            elapsed += _POLL_INTERVAL_SECONDS
        raise RuntimeError(f"ai360 影片生成輪詢逾時（{_POLL_TIMEOUT_SECONDS} 秒）")

    def _absolute_url(self, url: str) -> str:
        """將相對路徑（如 /generated/videos/...）補成可下載的完整 URL。"""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return f"{self._base_url}/{url.lstrip('/')}"

    async def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        await self._ensure_auth()

        prompt = request.prompt
        # image_to_video：上傳起始圖並於 prompt 首部插入 @圖片1 token
        if request.start_image and Path(request.start_image).exists():
            token = await self._upload_start_image(Path(request.start_image))
            prompt = f"{token} {prompt}"

        duration = _clamp_duration(request.duration_seconds)
        payload: dict = {
            "prompt": prompt,
            "duration": duration,
            "ratio": _resolve_ratio(request.aspect_ratio),
            "resolution": _resolve_resolution(request.resolution),
            "generateAudio": bool(request.generate_audio),
        }

        logger.info(
            "ai360 影片生成開始: duration=%s, ratio=%s, resolution=%s, audio=%s",
            payload["duration"],
            payload["ratio"],
            payload["resolution"],
            payload["generateAudio"],
        )

        history_id = await self._create_task(payload)
        task = await self._wait_for_completion(history_id)

        video_url = _extract_video_url(task)
        if not video_url:
            raise RuntimeError("ai360 任務完成但未返回影片 URL")

        full_url = self._absolute_url(video_url)
        await download_video(full_url, request.output_path)
        logger.info("ai360 影片下載完成: %s", request.output_path)

        return VideoGenerationResult(
            video_path=request.output_path,
            provider=PROVIDER_AI360,
            model=self._model,
            duration_seconds=duration,
            video_uri=full_url,
            task_id=str(history_id),
            generate_audio=payload["generateAudio"],
        )
