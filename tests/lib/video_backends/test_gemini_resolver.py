from pathlib import Path

import pytest

from lib.video_backends.base import VideoGenerationRequest
from lib.video_backends.gemini import GeminiVideoBackend, VeoInvalidCombinationError


def make_backend(model: str, backend_type: str = "aistudio") -> GeminiVideoBackend:
    backend = GeminiVideoBackend.__new__(GeminiVideoBackend)
    backend._backend_type = backend_type
    backend._video_model = model
    return backend


@pytest.mark.parametrize(
    ("model", "resolution", "duration", "has_ref", "expect_duration", "expect_resolution"),
    [
        ("veo-3.1-generate-preview", "720p", 4, False, 4, "720p"),
        ("veo-3.1-generate-preview", "720p", 6, False, 6, "720p"),
        ("veo-3.1-generate-preview", "1080p", 8, False, 8, "1080p"),
        ("veo-3.1-generate-preview", "4k", 8, False, 8, "4k"),
        ("veo-3.1-generate-preview", "720p", 8, True, 8, "720p"),
    ],
)
def test_resolve_request_valid_combinations(
    model: str,
    resolution: str,
    duration: int,
    has_ref: bool,
    expect_duration: int,
    expect_resolution: str,
    tmp_path: Path,
):
    backend = make_backend(model)
    request = VideoGenerationRequest(
        prompt="鏡頭緩慢推進",
        output_path=tmp_path / "out.mp4",
        duration_seconds=duration,
        resolution=resolution,
        start_image=tmp_path / "start.png" if has_ref else None,
    )

    resolved, adjusted = backend._resolve_request(request)

    assert resolved.duration_seconds == expect_duration
    assert resolved.resolution == expect_resolution
    assert adjusted == {}


@pytest.mark.parametrize(
    ("model", "resolution", "duration", "has_ref"),
    [
        ("veo-3.1-generate-preview", "1080p", 4, False),
        ("veo-3.1-generate-preview", "4k", 4, False),
        ("veo-3.1-generate-preview", "720p", 4, True),
        ("veo-3.1-lite-generate-preview", "4k", 4, False),
    ],
)
def test_resolve_request_invalid_combinations_raise_error(
    model: str,
    resolution: str,
    duration: int,
    has_ref: bool,
    tmp_path: Path,
):
    backend = make_backend(model)
    request = VideoGenerationRequest(
        prompt="鏡頭緩慢推進",
        output_path=tmp_path / "out.mp4",
        duration_seconds=duration,
        resolution=resolution,
        start_image=tmp_path / "start.png" if has_ref else None,
    )

    with pytest.raises(VeoInvalidCombinationError):
        backend._resolve_request(request)


def test_unknown_model_keeps_legacy_duration_normalization(tmp_path: Path):
    backend = make_backend("unknown-veo-model")
    request = VideoGenerationRequest(
        prompt="鏡頭緩慢推進",
        output_path=tmp_path / "out.mp4",
        duration_seconds=5,
        resolution="4k",
    )

    resolved, adjusted = backend._resolve_request(request)

    assert resolved.duration_seconds == 6
    assert resolved.resolution == "4k"
    assert adjusted == {"duration_seconds": (5, 6)}


@pytest.mark.asyncio
async def test_create_task_wraps_google_bad_request_as_human_readable_error(tmp_path: Path):
    class FakeBadRequest(Exception):
        status_code = 400

    class FakeTypes:
        class GenerateVideosConfig:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class GenerateVideosSource:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

    class FakeModels:
        async def generate_videos(self, **_kwargs):
            raise FakeBadRequest("400 invalid argument")

    class FakeAio:
        models = FakeModels()

    class FakeClient:
        aio = FakeAio()

    backend = make_backend("veo-3.1-generate-preview")
    backend._rate_limiter = None
    backend._types = FakeTypes
    backend._client = FakeClient()
    request = VideoGenerationRequest(
        prompt="鏡頭緩慢推進",
        output_path=tmp_path / "out.mp4",
        duration_seconds=8,
        resolution="1080p",
    )

    with pytest.raises(VeoInvalidCombinationError) as exc_info:
        await backend._create_task(request)

    assert exc_info.value.detail["code"] == "veo_invalid_combination"
    assert "Veo 不支援" in exc_info.value.detail["message"]
