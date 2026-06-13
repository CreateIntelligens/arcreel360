"""OpenAIVideoBackend 單元測試。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import InternalServerError

from lib.providers import PROVIDER_OPENAI
from lib.video_backends.base import (
    VideoCapability,
    VideoGenerationRequest,
)


def _make_mock_video(status="completed", seconds="8", video_id="vid_123"):
    """構造 mock Video 響應。"""
    video = MagicMock()
    video.id = video_id
    video.status = status
    video.seconds = seconds
    video.error = None
    return video


def _make_mock_content(data: bytes = b"fake-video-data"):
    """構造 mock download_content 響應。"""
    content = MagicMock()
    content.content = data
    return content


class TestOpenAIVideoBackend:
    def test_name_and_model(self):
        with patch("lib.openai_shared.AsyncOpenAI"):
            from lib.video_backends.openai import OpenAIVideoBackend

            backend = OpenAIVideoBackend(api_key="test-key")
            assert backend.name == PROVIDER_OPENAI
            assert backend.model == "sora-2"

    def test_custom_model(self):
        with patch("lib.openai_shared.AsyncOpenAI"):
            from lib.video_backends.openai import OpenAIVideoBackend

            backend = OpenAIVideoBackend(api_key="test-key", model="sora-2-pro")
            assert backend.model == "sora-2-pro"

    def test_capabilities(self):
        with patch("lib.openai_shared.AsyncOpenAI"):
            from lib.video_backends.openai import OpenAIVideoBackend

            backend = OpenAIVideoBackend(api_key="test-key")
            assert VideoCapability.TEXT_TO_VIDEO in backend.capabilities
            assert VideoCapability.IMAGE_TO_VIDEO in backend.capabilities
            assert VideoCapability.GENERATE_AUDIO not in backend.capabilities
            assert VideoCapability.NEGATIVE_PROMPT not in backend.capabilities
            assert VideoCapability.SEED_CONTROL not in backend.capabilities

    async def test_text_to_video(self, tmp_path: Path):
        video_data = b"mp4-video-content"
        mock_client = AsyncMock()
        mock_client.videos.create_and_poll = AsyncMock(return_value=_make_mock_video(seconds="8"))
        mock_client.videos.download_content = AsyncMock(return_value=_make_mock_content(video_data))

        with patch("lib.openai_shared.AsyncOpenAI", return_value=mock_client):
            from lib.video_backends.openai import OpenAIVideoBackend

            backend = OpenAIVideoBackend(api_key="test-key")
            output_path = tmp_path / "output.mp4"
            request = VideoGenerationRequest(
                prompt="A cat walking in the park",
                output_path=output_path,
                aspect_ratio="9:16",
                resolution="720p",
                duration_seconds=8,
            )
            result = await backend.generate(request)

        assert result.provider == PROVIDER_OPENAI
        assert result.model == "sora-2"
        assert result.duration_seconds == 8
        assert result.video_path == output_path
        assert result.task_id == "vid_123"
        assert output_path.read_bytes() == video_data

        call_kwargs = mock_client.videos.create_and_poll.call_args[1]
        assert call_kwargs["prompt"] == "A cat walking in the park"
        assert call_kwargs["model"] == "sora-2"
        assert call_kwargs["seconds"] == "8"
        assert call_kwargs["size"] == "720x1280"  # 720p 9:16
        assert "input_reference" not in call_kwargs

    async def test_image_to_video(self, tmp_path: Path):
        start_image = tmp_path / "start.png"
        start_image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        mock_client = AsyncMock()
        mock_client.videos.create_and_poll = AsyncMock(return_value=_make_mock_video(seconds="4"))
        mock_client.videos.download_content = AsyncMock(return_value=_make_mock_content(b"video"))

        with patch("lib.openai_shared.AsyncOpenAI", return_value=mock_client):
            from lib.video_backends.openai import OpenAIVideoBackend

            backend = OpenAIVideoBackend(api_key="test-key")
            output_path = tmp_path / "output.mp4"
            request = VideoGenerationRequest(
                prompt="Animate this",
                output_path=output_path,
                start_image=start_image,
                duration_seconds=4,
            )
            result = await backend.generate(request)

        assert result.duration_seconds == 4
        call_kwargs = mock_client.videos.create_and_poll.call_args[1]
        ref = call_kwargs["input_reference"]
        assert isinstance(ref, tuple)
        assert ref[0] == "start.png"
        assert isinstance(ref[1], bytes)
        assert ref[2] == "image/png"

    async def test_failed_video_raises(self, tmp_path: Path):
        error = MagicMock()
        error.message = "Content policy violation"
        failed_video = _make_mock_video(status="failed")
        failed_video.error = error

        mock_client = AsyncMock()
        mock_client.videos.create_and_poll = AsyncMock(return_value=failed_video)

        with patch("lib.openai_shared.AsyncOpenAI", return_value=mock_client):
            from lib.video_backends.openai import OpenAIVideoBackend

            backend = OpenAIVideoBackend(api_key="test-key")
            output_path = tmp_path / "output.mp4"
            request = VideoGenerationRequest(
                prompt="Bad content",
                output_path=output_path,
            )
            with pytest.raises(RuntimeError, match="Sora 影片生成失敗"):
                await backend.generate(request)

    async def test_duration_mapping(self, tmp_path: Path):
        mock_client = AsyncMock()
        mock_client.videos.create_and_poll = AsyncMock(return_value=_make_mock_video(seconds="4"))
        mock_client.videos.download_content = AsyncMock(return_value=_make_mock_content(b"v"))

        with patch("lib.openai_shared.AsyncOpenAI", return_value=mock_client):
            from lib.video_backends.openai import OpenAIVideoBackend

            backend = OpenAIVideoBackend(api_key="test-key")

            for seconds, expected in [(3, "4"), (4, "4"), (5, "8"), (8, "8"), (10, "12"), (15, "12")]:
                output_path = tmp_path / f"output_{seconds}.mp4"
                request = VideoGenerationRequest(
                    prompt="test",
                    output_path=output_path,
                    duration_seconds=seconds,
                )
                await backend.generate(request)
                call_kwargs = mock_client.videos.create_and_poll.call_args[1]
                assert call_kwargs["seconds"] == expected, f"duration={seconds}"

    async def test_video_seconds_none_fallback(self, tmp_path: Path):
        """當 API 返回 video.seconds=None 時，應回退到請求的 duration。"""
        mock_client = AsyncMock()
        mock_client.videos.create_and_poll = AsyncMock(return_value=_make_mock_video(seconds=None))
        mock_client.videos.download_content = AsyncMock(return_value=_make_mock_content(b"v"))

        with patch("lib.openai_shared.AsyncOpenAI", return_value=mock_client):
            from lib.video_backends.openai import OpenAIVideoBackend

            backend = OpenAIVideoBackend(api_key="test-key")
            output_path = tmp_path / "output.mp4"
            request = VideoGenerationRequest(
                prompt="test",
                output_path=output_path,
                duration_seconds=5,
            )
            result = await backend.generate(request)

        # 請求 5 秒 → _map_duration → "8"，回退應返回 8
        assert result.duration_seconds == 8

    async def test_size_mapping(self, tmp_path: Path):
        mock_client = AsyncMock()
        mock_client.videos.create_and_poll = AsyncMock(return_value=_make_mock_video(seconds="4"))
        mock_client.videos.download_content = AsyncMock(return_value=_make_mock_content(b"v"))

        with patch("lib.openai_shared.AsyncOpenAI", return_value=mock_client):
            from lib.video_backends.openai import OpenAIVideoBackend

            backend = OpenAIVideoBackend(api_key="test-key")

            for aspect, expected_size in [("9:16", "720x1280"), ("16:9", "1280x720")]:
                output_path = tmp_path / f"output_{aspect.replace(':', '_')}.mp4"
                request = VideoGenerationRequest(
                    prompt="test",
                    output_path=output_path,
                    aspect_ratio=aspect,
                    resolution="720p",
                )
                await backend.generate(request)
                call_kwargs = mock_client.videos.create_and_poll.call_args[1]
                assert call_kwargs["size"] == expected_size, f"aspect={aspect}"

    async def test_content_download_retry_does_not_regenerate(self, tmp_path: Path):
        """內容下載 502 失敗後應單獨重試下載，而非重新呼叫 create_and_poll。"""
        error = InternalServerError(
            message="Failed to resolve Vertex video URL",
            response=MagicMock(status_code=502, headers={}),
            body=None,
        )
        mock_client = AsyncMock()
        mock_client.videos.create_and_poll = AsyncMock(return_value=_make_mock_video(seconds="8"))
        mock_client.videos.download_content = AsyncMock(side_effect=[error, error, _make_mock_content(b"video-data")])

        with (
            patch("lib.openai_shared.AsyncOpenAI", return_value=mock_client),
            patch("lib.retry.asyncio.sleep", new_callable=AsyncMock),
        ):
            from lib.video_backends.openai import OpenAIVideoBackend

            backend = OpenAIVideoBackend(api_key="test-key")
            output_path = tmp_path / "output.mp4"
            request = VideoGenerationRequest(
                prompt="test",
                output_path=output_path,
                duration_seconds=8,
            )
            result = await backend.generate(request)

        assert result.video_path == output_path
        assert output_path.read_bytes() == b"video-data"
        # create_and_poll 只呼叫 1 次，不因下載失敗生成
        assert mock_client.videos.create_and_poll.call_count == 1
        # download_content 呼叫 3 次（2 次失敗 + 1 次成功）
        assert mock_client.videos.download_content.call_count == 3

    async def test_content_download_all_retries_exhausted(self, tmp_path: Path):
        """內容下載全部重試耗盡後應丟擲異常，且不生成影片。"""
        error = InternalServerError(
            message="Failed to resolve Vertex video URL",
            response=MagicMock(status_code=502, headers={}),
            body=None,
        )
        mock_client = AsyncMock()
        mock_client.videos.create_and_poll = AsyncMock(return_value=_make_mock_video(seconds="8"))
        mock_client.videos.download_content = AsyncMock(side_effect=error)

        with (
            patch("lib.openai_shared.AsyncOpenAI", return_value=mock_client),
            patch("lib.retry.asyncio.sleep", new_callable=AsyncMock),
        ):
            from lib.video_backends.openai import OpenAIVideoBackend

            backend = OpenAIVideoBackend(api_key="test-key")
            output_path = tmp_path / "output.mp4"
            request = VideoGenerationRequest(
                prompt="test",
                output_path=output_path,
                duration_seconds=8,
            )
            with pytest.raises(InternalServerError):
                await backend.generate(request)

        # 即使下載重試耗盡，也只生成 1 次影片
        assert mock_client.videos.create_and_poll.call_count == 1

    async def test_content_download_non_retryable_error_fails_immediately(self, tmp_path: Path):
        """不可重試的下載錯誤（如 4xx）應立即失敗，不浪費退避時間。"""
        from openai import AuthenticationError

        error = AuthenticationError(
            message="Invalid API key",
            response=MagicMock(status_code=401, headers={}),
            body=None,
        )
        mock_client = AsyncMock()
        mock_client.videos.create_and_poll = AsyncMock(return_value=_make_mock_video(seconds="8"))
        mock_client.videos.download_content = AsyncMock(side_effect=error)
        mock_sleep = AsyncMock()

        with (
            patch("lib.openai_shared.AsyncOpenAI", return_value=mock_client),
            patch("lib.retry.asyncio.sleep", mock_sleep),
        ):
            from lib.video_backends.openai import OpenAIVideoBackend

            backend = OpenAIVideoBackend(api_key="test-key")
            output_path = tmp_path / "output.mp4"
            request = VideoGenerationRequest(
                prompt="test",
                output_path=output_path,
                duration_seconds=8,
            )
            with pytest.raises(AuthenticationError):
                await backend.generate(request)

        # 不可重試錯誤：只呼叫 1 次下載，無 sleep
        assert mock_client.videos.download_content.call_count == 1
        mock_sleep.assert_not_called()

    async def test_image_to_video_auto_resizes(self, tmp_path: Path):
        from PIL import Image

        # 1. 建立一個 100x100 的正方形 start_image
        start_image = tmp_path / "wrong_size.png"
        img = Image.new("RGB", (100, 100), color="red")
        img.save(start_image)

        mock_client = AsyncMock()
        mock_client.videos.create_and_poll = AsyncMock(return_value=_make_mock_video(seconds="4"))
        mock_client.videos.download_content = AsyncMock(return_value=_make_mock_content(b"video"))

        with patch("lib.openai_shared.AsyncOpenAI", return_value=mock_client):
            from lib.video_backends.openai import OpenAIVideoBackend

            backend = OpenAIVideoBackend(api_key="test-key")
            output_path = tmp_path / "output.mp4"
            request = VideoGenerationRequest(
                prompt="Animate this wrong size image",
                output_path=output_path,
                start_image=start_image,
                aspect_ratio="16:9",
                resolution="720p",  # 會 resolve 成 1280x720
                duration_seconds=4,
            )
            result = await backend.generate(request)

        assert result.duration_seconds == 4
        call_kwargs = mock_client.videos.create_and_poll.call_args[1]
        ref = call_kwargs["input_reference"]
        assert isinstance(ref, tuple)
        assert ref[0].startswith("wrong_size_resized_1280x720")
        assert ref[2] == "image/png"

        # 讀取傳送的二進位資料，檢查它的解析度是否已變為 1280x720
        from io import BytesIO

        with Image.open(BytesIO(ref[1])) as resized_img:
            assert resized_img.size == (1280, 720)

        # 確認臨時檔案在 generate() 結束後已被刪除
        temp_files = list(tmp_path.glob("*resized*"))
        assert len(temp_files) == 0
