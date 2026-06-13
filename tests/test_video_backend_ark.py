"""ArkVideoBackend 單元測試 — mock Ark SDK。"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lib.video_backends.ark import ArkVideoBackend
from lib.video_backends.base import (
    VideoCapability,
    VideoGenerationRequest,
    VideoGenerationResult,
)


@pytest.fixture
def mock_ark_client():
    client = MagicMock()
    client.content_generation = MagicMock()
    client.content_generation.tasks = MagicMock()
    return client


@pytest.fixture
def backend(mock_ark_client):
    with patch("lib.video_backends.ark.create_ark_client", return_value=mock_ark_client):
        b = ArkVideoBackend(
            api_key="test-ark-key",
        )
    b._client = mock_ark_client
    return b


def _mock_httpx_stream(data: bytes = b"fake-mp4-data"):
    """Create a patched httpx mock that supports async stream context manager."""
    patcher = patch("lib.video_backends.base.httpx")
    mock_httpx = patcher.start()

    mock_stream_response = MagicMock()
    mock_stream_response.raise_for_status = MagicMock()

    async def _aiter_bytes(chunk_size=65536):
        yield data

    mock_stream_response.aiter_bytes = _aiter_bytes
    mock_stream_response.__aenter__ = AsyncMock(return_value=mock_stream_response)
    mock_stream_response.__aexit__ = AsyncMock(return_value=None)

    mock_http_client = AsyncMock()
    mock_http_client.stream = MagicMock(return_value=mock_stream_response)
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=None)
    mock_httpx.AsyncClient.return_value = mock_http_client

    return patcher


class TestArkProperties:
    def test_name(self, backend):
        assert backend.name == "byteplus"

    def test_capabilities(self, backend):
        caps = backend.capabilities
        assert VideoCapability.TEXT_TO_VIDEO in caps
        assert VideoCapability.IMAGE_TO_VIDEO in caps
        assert VideoCapability.GENERATE_AUDIO in caps
        assert VideoCapability.SEED_CONTROL in caps
        # service_tier 已移除（cf356f3），ark 不再宣告 FLEX_TIER
        assert VideoCapability.FLEX_TIER not in caps
        assert VideoCapability.NEGATIVE_PROMPT not in caps


class TestArkGenerate:
    async def test_text_to_video(self, backend, tmp_path):
        """文生影片：無 start_image。"""
        output = tmp_path / "out.mp4"

        create_result = MagicMock()
        create_result.id = "cgt-20250101-test"
        backend._client.content_generation.tasks.create = MagicMock(return_value=create_result)

        get_result = MagicMock()
        get_result.status = "succeeded"
        get_result.content = MagicMock()
        get_result.content.video_url = "https://cdn.example.com/video.mp4"
        get_result.seed = 58944
        get_result.usage = MagicMock()
        get_result.usage.completion_tokens = 246840
        backend._client.content_generation.tasks.get = MagicMock(return_value=get_result)

        patcher = _mock_httpx_stream()
        try:
            request = VideoGenerationRequest(
                prompt="a flower field",
                output_path=output,
                duration_seconds=5,
            )
            result = await backend.generate(request)
        finally:
            patcher.stop()

        assert isinstance(result, VideoGenerationResult)
        assert result.provider == "byteplus"
        assert result.model == "doubao-seedance-2-0-260128"
        assert result.seed == 58944
        assert result.usage_tokens == 246840
        assert result.task_id == "cgt-20250101-test"

    async def test_create_task_invalid_model_friendly_error(self, backend, tmp_path):
        """當模型不是 ep- 開頭且 Ark API 報 InvalidEndpointOrModel 錯誤時，應丟出友善的錯誤。"""
        output = tmp_path / "out.mp4"
        backend._client.content_generation.tasks.create = MagicMock(
            side_effect=Exception(
                "InvalidEndpointOrModel.NotFound: The model or endpoint doubao-seedance-2-0-260128 does not exist"
            )
        )

        request = VideoGenerationRequest(prompt="test", output_path=output)
        with pytest.raises(RuntimeError) as exc_info:
            await backend.generate(request)

        assert "火山引擎 (BytePlus ModelArk) 影片生成失敗" in str(exc_info.value)
        assert "Endpoint ID" in str(exc_info.value)

    async def test_create_task_endpoint_other_error(self, tmp_path):
        """當模型是 ep- 開頭且 Ark API 報 NotFound 錯誤時，應直接拋出原始錯誤（不由 friendly error 攔截）。"""
        output = tmp_path / "out.mp4"
        with patch("lib.video_backends.ark.create_ark_client", return_value=MagicMock()):
            b = ArkVideoBackend(api_key="test", model="ep-20260508120826-lkcjf")
            b._client.content_generation.tasks.create = MagicMock(
                side_effect=Exception(
                    "InvalidEndpointOrModel.NotFound: The model or endpoint ep-20260508120826-lkcjf does not exist"
                )
            )

            request = VideoGenerationRequest(prompt="test", output_path=output)
            with pytest.raises(Exception) as exc_info:
                await b.generate(request)

            # 應直接傳播原始 Exception，且其內容不包含我們包裝的「火山引擎」中文字樣
            assert "火山引擎" not in str(exc_info.value)
            assert "InvalidEndpointOrModel.NotFound" in str(exc_info.value)

    async def test_image_to_video(self, backend, tmp_path):
        """圖生影片：有 start_image。"""
        output = tmp_path / "out.mp4"
        frame = tmp_path / "scene_E1S01.png"
        frame.write_bytes(b"fake-png")

        create_result = MagicMock()
        create_result.id = "cgt-i2v-test"
        backend._client.content_generation.tasks.create = MagicMock(return_value=create_result)

        get_result = MagicMock()
        get_result.status = "succeeded"
        get_result.content = MagicMock()
        get_result.content.video_url = "https://cdn.example.com/video2.mp4"
        get_result.seed = 12345
        get_result.usage = MagicMock()
        get_result.usage.completion_tokens = 200000
        backend._client.content_generation.tasks.get = MagicMock(return_value=get_result)

        patcher = _mock_httpx_stream()
        try:
            request = VideoGenerationRequest(
                prompt="girl opens eyes",
                output_path=output,
                start_image=frame,
                generate_audio=True,
            )
            result = await backend.generate(request)
        finally:
            patcher.stop()

        assert result.provider == "byteplus"
        create_call = backend._client.content_generation.tasks.create
        call_kwargs = create_call.call_args
        content_arg = call_kwargs.kwargs.get("content") or call_kwargs[1].get("content")
        assert len(content_arg) == 2
        assert content_arg[1]["type"] == "image_url"
        assert content_arg[1]["image_url"]["url"].startswith("data:image/")

    async def test_failed_task_raises(self, backend, tmp_path):
        output = tmp_path / "out.mp4"

        create_result = MagicMock()
        create_result.id = "cgt-fail"
        backend._client.content_generation.tasks.create = MagicMock(return_value=create_result)

        get_result = MagicMock()
        get_result.status = "failed"
        get_result.error = "content violation"
        backend._client.content_generation.tasks.get = MagicMock(return_value=get_result)

        request = VideoGenerationRequest(prompt="test", output_path=output)
        with pytest.raises(RuntimeError, match="Ark 影片生成失敗"):
            await backend.generate(request)

    async def test_with_seed(self, backend, tmp_path):
        output = tmp_path / "out.mp4"

        create_result = MagicMock()
        create_result.id = "cgt-seed"
        backend._client.content_generation.tasks.create = MagicMock(return_value=create_result)

        get_result = MagicMock()
        get_result.status = "succeeded"
        get_result.content = MagicMock()
        get_result.content.video_url = "https://cdn.example.com/video.mp4"
        get_result.seed = 42
        get_result.usage = MagicMock()
        get_result.usage.completion_tokens = 100000
        backend._client.content_generation.tasks.get = MagicMock(return_value=get_result)

        patcher = _mock_httpx_stream()
        try:
            request = VideoGenerationRequest(
                prompt="test",
                output_path=output,
                seed=42,
            )
            await backend.generate(request)
        finally:
            patcher.stop()

        create_call = backend._client.content_generation.tasks.create
        call_kwargs = create_call.call_args
        assert call_kwargs.kwargs.get("seed") == 42 or call_kwargs[1].get("seed") == 42
        assert "service_tier" not in call_kwargs.kwargs

    def test_missing_api_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Ark API Key"):
                ArkVideoBackend(api_key=None)


class TestArkRetryBehavior:
    """測試任務建立與輪詢的重試分離行為。"""

    async def test_poll_transient_error_retries_without_recreating_task(self, backend, tmp_path):
        """輪詢階段瞬態錯誤應重試輪詢，而不是重新建立任務。"""
        output = tmp_path / "out.mp4"

        create_result = MagicMock()
        create_result.id = "cgt-retry-test"
        backend._client.content_generation.tasks.create = MagicMock(return_value=create_result)

        get_success = MagicMock()
        get_success.status = "succeeded"
        get_success.content = MagicMock()
        get_success.content.video_url = "https://cdn.example.com/video.mp4"
        get_success.seed = None
        get_success.usage = None

        # 第一次輪詢拋 ConnectionError，第二次成功
        backend._client.content_generation.tasks.get = MagicMock(
            side_effect=[ConnectionError("connection reset"), get_success]
        )

        patcher = _mock_httpx_stream()
        try:
            request = VideoGenerationRequest(prompt="test", output_path=output)
            with patch("lib.video_backends.ark.asyncio.sleep", new_callable=AsyncMock):
                result = await backend.generate(request)
        finally:
            patcher.stop()

        assert result.task_id == "cgt-retry-test"
        # 關鍵斷言：任務只建立了一次
        assert backend._client.content_generation.tasks.create.call_count == 1
        # 輪詢呼叫了兩次（一次失敗 + 一次成功）
        assert backend._client.content_generation.tasks.get.call_count == 2

    async def test_create_retries_on_transient_error(self, backend, tmp_path):
        """任務建立階段的瞬態錯誤應由 @with_retry_async 重試。"""
        output = tmp_path / "out.mp4"

        create_result = MagicMock()
        create_result.id = "cgt-create-retry"
        # 第一次建立拋 ConnectionError，第二次成功
        backend._client.content_generation.tasks.create = MagicMock(
            side_effect=[ConnectionError("connection reset"), create_result]
        )

        get_result = MagicMock()
        get_result.status = "succeeded"
        get_result.content = MagicMock()
        get_result.content.video_url = "https://cdn.example.com/video.mp4"
        get_result.seed = None
        get_result.usage = None
        backend._client.content_generation.tasks.get = MagicMock(return_value=get_result)

        patcher = _mock_httpx_stream()
        try:
            request = VideoGenerationRequest(prompt="test", output_path=output)
            with (
                patch("lib.video_backends.ark.asyncio.sleep", new_callable=AsyncMock),
                patch("lib.retry.asyncio.sleep", new_callable=AsyncMock),
            ):
                result = await backend.generate(request)
        finally:
            patcher.stop()

        assert result.task_id == "cgt-create-retry"
        # 建立呼叫了兩次（一次失敗 + 一次成功）
        assert backend._client.content_generation.tasks.create.call_count == 2

    async def test_poll_non_retryable_error_propagates(self, backend, tmp_path):
        """輪詢階段不可重試的錯誤應直接丟擲。"""
        output = tmp_path / "out.mp4"

        create_result = MagicMock()
        create_result.id = "cgt-no-retry"
        backend._client.content_generation.tasks.create = MagicMock(return_value=create_result)

        backend._client.content_generation.tasks.get = MagicMock(side_effect=ValueError("invalid response"))

        request = VideoGenerationRequest(prompt="test", output_path=output)
        with pytest.raises(ValueError, match="invalid response"):
            with patch("lib.video_backends.ark.asyncio.sleep", new_callable=AsyncMock):
                await backend.generate(request)

        # 建立只呼叫一次，輪詢只嘗試一次就丟擲
        assert backend._client.content_generation.tasks.create.call_count == 1
        assert backend._client.content_generation.tasks.get.call_count == 1


class TestArkModelCapabilities:
    """測試不同模型的能力對映。"""

    def test_seedance_2_no_flex_tier(self):
        with patch("lib.video_backends.ark.create_ark_client", return_value=MagicMock()):
            b = ArkVideoBackend(api_key="test", model="doubao-seedance-2-0-260128")
        caps = b.capabilities
        assert VideoCapability.FLEX_TIER not in caps
        assert VideoCapability.VIDEO_EXTEND not in caps

    def test_modelark_endpoint_id_uses_seedance_2_capabilities(self):
        with patch("lib.video_backends.ark.create_ark_client", return_value=MagicMock()):
            b = ArkVideoBackend(api_key="test", model="ep-20260508120826-lkcjf")
        caps = b.capabilities
        assert VideoCapability.FLEX_TIER not in caps
        assert VideoCapability.SEED_CONTROL in caps

    def test_unknown_model_gets_default_capabilities(self):
        with patch("lib.video_backends.ark.create_ark_client", return_value=MagicMock()):
            b = ArkVideoBackend(api_key="test", model="some-future-model")
        caps = b.capabilities
        assert VideoCapability.FLEX_TIER not in caps
        assert VideoCapability.SEED_CONTROL in caps
