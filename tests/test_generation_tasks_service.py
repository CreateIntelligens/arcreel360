import contextlib
from pathlib import Path

import pytest

from server.services import generation_tasks


def _async_return(value):
    """Create an async function that always returns the given value (ignoring args)."""

    async def _inner(*args, **kwargs):
        return value

    return _inner


from lib.storyboard_sequence import (
    PREVIOUS_STORYBOARD_REFERENCE_DESCRIPTION,
    PREVIOUS_STORYBOARD_REFERENCE_LABEL,
)


class _FakePM:
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.project = {
            "content_mode": "narration",
            "style": "Anime",
            "style_description": "cinematic",
            "characters": {
                "Alice": {
                    "character_sheet": "characters/Alice.png",
                    "reference_image": "characters/refs/Alice-ref.png",
                }
            },
            "clues": {"玉佩": {"type": "prop", "clue_sheet": "clues/玉佩.png"}},
        }
        self.script = {
            "content_mode": "narration",
            "segments": [
                {
                    "segment_id": "E1S01",
                    "duration_seconds": 4,
                    "segment_break": False,
                    "characters_in_segment": [],
                    "clues_in_segment": [],
                    "image_prompt": "首鏡頭",
                },
                {
                    "segment_id": "E1S02",
                    "duration_seconds": 4,
                    "segment_break": False,
                    "characters_in_segment": ["Alice"],
                    "clues_in_segment": ["玉佩"],
                    "image_prompt": {
                        "scene": "在雨夜街道",
                        "composition": {
                            "shot_type": "Medium Shot",
                            "lighting": "暖光",
                            "ambiance": "薄霧",
                        },
                    },
                },
                {
                    "segment_id": "E1S03",
                    "duration_seconds": 4,
                    "segment_break": True,
                    "characters_in_segment": ["Alice"],
                    "clues_in_segment": ["玉佩"],
                    "image_prompt": "切場後的鏡頭",
                },
            ],
        }
        self.updated_assets = []

    def load_project(self, project_name: str):
        return self.project

    def get_project_path(self, project_name: str):
        return self.project_path

    def load_script(self, project_name: str, script_file: str):
        return self.script

    def update_scene_asset(self, **kwargs):
        self.updated_assets.append(kwargs)

    def save_project(self, project_name: str, project: dict):
        self.project = project

    def update_project(self, project_name: str, mutate_fn):
        mutate_fn(self.project)

    def project_exists(self, project_name: str) -> bool:
        return True


class _FakeGenerator:
    def __init__(self):
        self.image_calls = []
        self.video_calls = []
        self.versions = self

    def generate_image(self, **kwargs):
        self.image_calls.append(kwargs)
        return Path("/tmp/image.png"), 1

    async def generate_image_async(self, **kwargs):
        self.image_calls.append(kwargs)
        return Path("/tmp/image.png"), 1

    def generate_video(self, **kwargs):
        self.video_calls.append(kwargs)
        return Path("/tmp/video.mp4"), 2, "ref", "uri"

    async def generate_video_async(self, **kwargs):
        self.video_calls.append(kwargs)
        return Path("/tmp/video.mp4"), 2, "ref", "uri"

    def get_versions(self, resource_type, resource_id):
        return {"versions": [{"created_at": "2026-01-01T00:00:00Z"}]}


def _prepare_files(tmp_path: Path):
    project_path = tmp_path / "projects" / "demo"
    (project_path / "storyboards").mkdir(parents=True, exist_ok=True)
    (project_path / "characters").mkdir(parents=True, exist_ok=True)
    (project_path / "characters" / "refs").mkdir(parents=True, exist_ok=True)
    (project_path / "clues").mkdir(parents=True, exist_ok=True)
    (project_path / "storyboards" / "scene_E1S01.png").write_bytes(b"png")
    (project_path / "characters" / "Alice.png").write_bytes(b"png")
    (project_path / "characters" / "refs" / "Alice-ref.png").write_bytes(b"png")
    (project_path / "clues" / "玉佩.png").write_bytes(b"png")
    return project_path


class TestGenerationTasks:
    def test_helper_functions(self, tmp_path):
        from lib.storyboard_sequence import get_storyboard_items

        mode_items = get_storyboard_items({"content_mode": "drama", "scenes": []})
        assert mode_items[1] == "scene_id"

        # 字串型 prompt：有風格時前綴注入，無風格時原樣回傳
        prompt = generation_tasks._normalize_storyboard_prompt("text", "Anime")
        assert prompt == "Anime\n\ntext"
        assert generation_tasks._normalize_storyboard_prompt("text", "") == "text"

        with pytest.raises(ValueError):
            generation_tasks._normalize_storyboard_prompt({"scene": ""}, "Anime")

        video_yaml = generation_tasks._normalize_video_prompt(
            {
                "action": "行走",
                "camera_motion": "",
                "ambiance_audio": "風聲",
                "dialogue": [{"speaker": "Alice", "line": "hello"}],
            }
        )
        assert "Camera_Motion" in video_yaml

        with pytest.raises(ValueError):
            generation_tasks._normalize_video_prompt({"action": ""})

    async def test_execute_task_dispatch(self, tmp_path, monkeypatch):
        project_path = _prepare_files(tmp_path)
        fake_pm = _FakePM(project_path)
        fake_generator = _FakeGenerator()
        emitted_batches = []

        monkeypatch.setattr(generation_tasks, "get_project_manager", lambda: fake_pm)
        monkeypatch.setattr(generation_tasks, "get_media_generator", _async_return(fake_generator))
        monkeypatch.setattr(
            generation_tasks,
            "emit_project_change_batch",
            lambda project_name, changes, source="worker": emitted_batches.append(
                {
                    "project_name": project_name,
                    "source": source,
                    "changes": list(changes),
                }
            ),
        )

        storyboard_result = await generation_tasks.execute_storyboard_task(
            "demo",
            "E1S02",
            {
                "script_file": "episode_1.json",
                "prompt": "direct prompt",
                "extra_reference_images": ["characters/Alice.png"],
            },
        )
        assert storyboard_result["resource_type"] == "storyboards"
        storyboard_refs = fake_generator.image_calls[0]["reference_images"]
        assert storyboard_refs == [
            project_path / "characters" / "Alice.png",
            project_path / "clues" / "玉佩.png",
            project_path / "characters" / "Alice.png",
            {
                "image": project_path / "storyboards" / "scene_E1S01.png",
                "label": PREVIOUS_STORYBOARD_REFERENCE_LABEL,
                "description": PREVIOUS_STORYBOARD_REFERENCE_DESCRIPTION,
            },
        ]

        await generation_tasks.execute_storyboard_task(
            "demo",
            "E1S03",
            {"script_file": "episode_1.json", "prompt": "direct prompt"},
        )
        assert fake_generator.image_calls[1]["reference_images"] == [
            project_path / "characters" / "Alice.png",
            project_path / "clues" / "玉佩.png",
        ]

        video_result = await generation_tasks.execute_video_task(
            "demo",
            "E1S01",
            {"script_file": "episode_1.json", "prompt": {"action": "跑", "camera_motion": "Static", "dialogue": []}},
        )
        assert video_result["resource_type"] == "videos"
        assert video_result["video_uri"] == "uri"

        character_result = await generation_tasks.execute_character_task(
            "demo",
            "Alice",
            {"prompt": "角色描述"},
        )
        assert character_result["resource_type"] == "characters"
        assert fake_pm.project["characters"]["Alice"]["character_sheet"] == "characters/Alice.png"

        clue_result = await generation_tasks.execute_clue_task(
            "demo",
            "玉佩",
            {"prompt": "線索描述"},
        )
        assert clue_result["resource_type"] == "clues"

        dispatch = await generation_tasks.execute_generation_task(
            {
                "task_type": "storyboard",
                "project_name": "demo",
                "resource_id": "E1S02",
                "payload": {"script_file": "episode_1.json", "prompt": "text"},
            }
        )
        assert dispatch["resource_type"] == "storyboards"
        assert len(emitted_batches) == 1
        emitted_change = emitted_batches[0]["changes"][0]
        assert emitted_change["entity_type"] == "segment"
        assert emitted_change["action"] == "storyboard_ready"
        assert emitted_change["entity_id"] == "E1S02"
        assert "asset_fingerprints" in emitted_change

        with pytest.raises(ValueError):
            await generation_tasks.execute_generation_task(
                {"task_type": "unknown", "project_name": "demo", "resource_id": "x", "payload": {}}
            )

    async def test_execute_video_task_generates_thumbnail(self, monkeypatch, tmp_path):
        """影片生成後應自動提取首幀縮圖"""
        project_path = _prepare_files(tmp_path)
        fake_pm = _FakePM(project_path)
        fake_generator = _FakeGenerator()

        thumbnail_path = project_path / "thumbnails" / "scene_E1S01.jpg"

        async def fake_extract(video_path, out_path):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"thumb")
            return out_path

        monkeypatch.setattr(generation_tasks, "get_project_manager", lambda: fake_pm)
        monkeypatch.setattr(generation_tasks, "get_media_generator", _async_return(fake_generator))
        monkeypatch.setattr(generation_tasks, "extract_video_thumbnail", fake_extract)
        monkeypatch.setattr(generation_tasks, "emit_project_change_batch", lambda *a, **kw: None)

        result = await generation_tasks.execute_video_task(
            "demo",
            "E1S01",
            {"script_file": "episode_1.json", "prompt": {"action": "跑", "camera_motion": "Static", "dialogue": []}},
        )

        assert result["resource_type"] == "videos"
        # 驗證 update_scene_asset 被呼叫，其中包含 video_thumbnail
        asset_types = [call["asset_type"] for call in fake_pm.updated_assets]
        assert "video_thumbnail" in asset_types
        assert thumbnail_path.exists()

    async def test_get_media_generator_skips_image_backend_for_video_tasks(self, monkeypatch, tmp_path):
        """影片任務只應初始化影片 backend，避免圖片配置缺失導致提前失敗。"""
        project_path = _prepare_files(tmp_path)
        fake_pm = _FakePM(project_path)
        fake_video_backend = object()

        class _FakeResolver:
            def __init__(self, session_factory):
                self.session_factory = session_factory

            @contextlib.asynccontextmanager
            async def session(self):
                yield self

            async def default_image_backend(self):
                raise AssertionError("video tasks should not resolve image backend")

        async def _fake_resolve_video_backend(project_name, resolver, payload):
            assert project_name == "demo"
            return fake_video_backend, "unused", "video-model"

        monkeypatch.setattr(generation_tasks, "get_project_manager", lambda: fake_pm)
        monkeypatch.setattr("lib.config.resolver.ConfigResolver", _FakeResolver)
        monkeypatch.setattr(
            generation_tasks,
            "_resolve_video_backend",
            _fake_resolve_video_backend,
        )

        generator = await generation_tasks.get_media_generator(
            "demo",
            payload={"prompt": "video"},
            require_image_backend=False,
        )

        assert generator._image_backend is None
        assert generator._video_backend is fake_video_backend

    def test_emit_success_batch_includes_fingerprints(self, monkeypatch, tmp_path):
        """生成成功事件應攜帶 asset_fingerprints"""
        captured = []
        monkeypatch.setattr(
            generation_tasks,
            "emit_project_change_batch",
            lambda project_name, changes, source: captured.append(changes),
        )

        project_path = tmp_path / "demo"
        project_path.mkdir()
        (project_path / "storyboards").mkdir()
        sb = project_path / "storyboards" / "scene_E1S01.png"
        sb.write_bytes(b"img")

        fake_pm = _FakePM(project_path)
        monkeypatch.setattr(generation_tasks, "get_project_manager", lambda: fake_pm)

        generation_tasks._emit_generation_success_batch(
            task_type="storyboard",
            project_name="demo",
            resource_id="E1S01",
            payload={"script_file": "ep01.json"},
        )

        assert len(captured) == 1
        change = captured[0][0]
        assert "asset_fingerprints" in change
        assert "storyboards/scene_E1S01.png" in change["asset_fingerprints"]
        assert isinstance(change["asset_fingerprints"]["storyboards/scene_E1S01.png"], int)

    async def test_execute_task_validation_errors(self, tmp_path, monkeypatch):
        project_path = _prepare_files(tmp_path)
        fake_pm = _FakePM(project_path)
        monkeypatch.setattr(generation_tasks, "get_project_manager", lambda: fake_pm)
        monkeypatch.setattr(generation_tasks, "get_media_generator", _async_return(_FakeGenerator()))

        with pytest.raises(ValueError):
            await generation_tasks.execute_storyboard_task("demo", "E1S01", {"prompt": "x"})

        with pytest.raises(ValueError):
            await generation_tasks.execute_video_task("demo", "E1S01", {"script_file": "episode_1.json"})

        (project_path / "storyboards" / "scene_E1S01.png").unlink()
        with pytest.raises(ValueError):
            await generation_tasks.execute_video_task("demo", "E1S01", {"script_file": "episode_1.json", "prompt": "x"})

    async def test_resolve_video_backend_payload_override(self, monkeypatch, tmp_path):
        """驗證 _resolve_video_backend 優先使用 payload 中的 video_provider 及 settings"""
        project_path = _prepare_files(tmp_path)
        fake_pm = _FakePM(project_path)
        monkeypatch.setattr(generation_tasks, "get_project_manager", lambda: fake_pm)

        # Mock resolver 與 _get_or_create_video_backend
        class FakeResolver:
            async def default_video_backend(self):
                return "gemini-aistudio", "veo-3.1-lite-generate-preview"

        resolved_args = []

        async def fake_get_backend(provider_name, settings, resolver, default_video_model=None):
            resolved_args.append((provider_name, settings, default_video_model))
            return object()

        monkeypatch.setattr(generation_tasks, "_get_or_create_video_backend", fake_get_backend)

        # 1. 帶有 payload 覆蓋
        payload = {
            "video_provider": "byteplus",
            "video_provider_settings": {"model": "doubao-seedance-2-0-260128"},
        }
        resolver = FakeResolver()
        await generation_tasks._resolve_video_backend("demo", resolver, payload)
        assert len(resolved_args) == 1
        assert resolved_args[0][0] == "byteplus"
        assert resolved_args[0][1] == {"model": "doubao-seedance-2-0-260128"}

        # 2. 不帶 payload 覆蓋，使用 project.json (預設為 None, 走 default_video_provider_id)
        resolved_args.clear()
        await generation_tasks._resolve_video_backend("demo", resolver, {"script_file": "episode_1.json"})
        assert len(resolved_args) == 1
        assert resolved_args[0][0] == "gemini-aistudio"


class TestGetAspectRatio:
    def test_reads_top_level_aspect_ratio(self):
        project = {"aspect_ratio": "16:9", "content_mode": "narration"}
        assert generation_tasks.get_aspect_ratio(project, "videos") == "16:9"
        assert generation_tasks.get_aspect_ratio(project, "storyboards") == "16:9"

    def test_fallback_to_content_mode_narration(self):
        project = {"content_mode": "narration"}
        assert generation_tasks.get_aspect_ratio(project, "videos") == "9:16"

    def test_fallback_to_content_mode_drama(self):
        project = {"content_mode": "drama"}
        assert generation_tasks.get_aspect_ratio(project, "videos") == "16:9"

    def test_characters_always_3_4(self):
        project = {"aspect_ratio": "16:9"}
        assert generation_tasks.get_aspect_ratio(project, "characters") == "3:4"

    def test_clues_always_16_9(self):
        project = {"aspect_ratio": "9:16"}
        assert generation_tasks.get_aspect_ratio(project, "clues") == "16:9"


class TestGetOrCreateVideoBackend:
    async def test_byteplus_model_substitution(self, monkeypatch):
        """驗證當使用 byteplus 且模型非 ep- 開頭時，會自動替換為配置的 endpoint_id。"""
        import contextlib
        from unittest.mock import MagicMock

        # Clear cache to avoid hits
        generation_tasks._backend_cache.clear()

        # Mock create_backend
        created_backends = []

        def fake_create_backend(name, **kwargs):
            created_backends.append((name, kwargs))
            mock_backend = MagicMock()
            mock_backend.model = kwargs.get("model")
            return mock_backend

        monkeypatch.setattr("lib.video_backends.create_backend", fake_create_backend)

        # Mock resolver
        class FakeResolver:
            def __init__(self, endpoint_id):
                self.endpoint_id = endpoint_id

            async def provider_config(self, provider_id):
                return {"api_key": "fake-key"}

            @contextlib.asynccontextmanager
            async def _open_session(self):
                class FakeSvc:
                    def __init__(self, endpoint_id):
                        self.endpoint_id = endpoint_id

                    async def get_setting(self, key, default=""):
                        if key == "byteplus_video_endpoint_id":
                            return self.endpoint_id
                        return default

                yield object(), FakeSvc(self.endpoint_id)

        resolver_with_endpoint = FakeResolver("ep-2026-test")
        resolver_no_endpoint = FakeResolver("")

        # 1. 有配置 endpoint_id 且傳入 non-endpoint 模型名稱
        await generation_tasks._get_or_create_video_backend(
            "byteplus", {"model": "doubao-seedance-2-0-260128"}, resolver_with_endpoint
        )
        assert len(created_backends) == 1
        assert created_backends[0][0] == "byteplus"
        assert created_backends[0][1]["model"] == "ep-2026-test"

        # 2. 沒有配置 endpoint_id 且傳入 non-endpoint 模型名稱
        created_backends.clear()
        await generation_tasks._get_or_create_video_backend(
            "byteplus", {"model": "doubao-seedance-2-0-260128"}, resolver_no_endpoint
        )
        assert len(created_backends) == 1
        assert created_backends[0][1]["model"] == "doubao-seedance-2-0-260128"

        # 3. 有配置 endpoint_id 但傳入的本來就是 ep- 開頭的模型名稱（不應替換）
        created_backends.clear()
        await generation_tasks._get_or_create_video_backend(
            "byteplus", {"model": "ep-another-endpoint"}, resolver_with_endpoint
        )
        assert len(created_backends) == 1
        assert created_backends[0][1]["model"] == "ep-another-endpoint"
