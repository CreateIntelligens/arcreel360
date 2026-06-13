from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from lib.config.resolver import ConfigResolver
from lib.config.service import ProviderStatus
from lib.db.base import Base


async def _make_session():
    """建立記憶體 SQLite 資料庫並返回 (factory, engine)。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory, engine


def _make_ready_provider(name: str, media_types: list[str]) -> ProviderStatus:
    return ProviderStatus(
        name=name,
        display_name=name,
        description="",
        status="ready",
        media_types=media_types,
        capabilities=[],
        required_keys=[],
        configured_keys=[],
        missing_keys=[],
    )


class _FakeConfigService:
    """最小化的 ConfigService fake，只實現 resolver 需要的方法。"""

    def __init__(
        self,
        settings: dict[str, str] | None = None,
        *,
        ready_providers: list[ProviderStatus] | None = None,
    ):
        self._settings = settings or {}
        self._ready_providers = ready_providers

    async def get_setting(self, key: str, default: str = "") -> str:
        return self._settings.get(key, default)

    async def get_default_video_backend(self) -> tuple[str, str]:
        return ("gemini-aistudio", "veo-3.1-fast-generate-preview")

    async def get_default_image_backend(self) -> tuple[str, str]:
        return ("gemini-aistudio", "gemini-3.1-flash-image-preview")

    async def get_provider_config(self, provider: str) -> dict[str, str]:
        return {"api_key": f"key-{provider}"}

    async def get_all_provider_configs(self) -> dict[str, dict[str, str]]:
        return {"gemini-aistudio": {"api_key": "key-aistudio"}}

    async def get_all_providers_status(self) -> list[ProviderStatus]:
        if self._ready_providers is not None:
            return self._ready_providers
        return [_make_ready_provider("gemini-aistudio", ["text", "image", "video"])]


class TestVideoGenerateAudio:
    """驗證 video_generate_audio 的預設值、全域性配置、專案級覆蓋優先順序。"""

    async def test_default_is_false_when_db_empty(self, tmp_path):
        """DB 無值時應返回 False（不是 True）。"""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={})
        result = await resolver._resolve_video_generate_audio(fake_svc, project_name=None)
        assert result is False

    async def test_global_true(self, tmp_path):
        """DB 中值為 "true" 時返回 True。"""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={"video_generate_audio": "true"})
        result = await resolver._resolve_video_generate_audio(fake_svc, project_name=None)
        assert result is True

    async def test_global_false(self, tmp_path):
        """DB 中值為 "false" 時返回 False。"""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={"video_generate_audio": "false"})
        result = await resolver._resolve_video_generate_audio(fake_svc, project_name=None)
        assert result is False

    async def test_bool_parsing_variants(self, tmp_path):
        """驗證各種布林字串的解析。"""
        resolver = ConfigResolver.__new__(ConfigResolver)
        for val, expected in [("TRUE", True), ("1", True), ("yes", True), ("0", False), ("no", False), ("", False)]:
            fake_svc = _FakeConfigService(settings={"video_generate_audio": val} if val else {})
            result = await resolver._resolve_video_generate_audio(fake_svc, project_name=None)
            assert result is expected, f"Failed for {val!r}: got {result}"

    async def test_project_override_true_over_global_false(self, tmp_path):
        """專案級覆蓋 True 優先於全域性 False。"""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={"video_generate_audio": "false"})
        with patch("lib.config.resolver.get_project_manager") as mock_pm:
            mock_pm.return_value.load_project.return_value = {"video_generate_audio": True}
            result = await resolver._resolve_video_generate_audio(fake_svc, project_name="demo")
        assert result is True

    async def test_project_override_false_over_global_true(self, tmp_path):
        """專案級覆蓋 False 優先於全域性 True。"""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={"video_generate_audio": "true"})
        with patch("lib.config.resolver.get_project_manager") as mock_pm:
            mock_pm.return_value.load_project.return_value = {"video_generate_audio": False}
            result = await resolver._resolve_video_generate_audio(fake_svc, project_name="demo")
        assert result is False

    async def test_project_none_skips_override(self, tmp_path):
        """project_name=None 時不讀取專案配置。"""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={"video_generate_audio": "true"})
        result = await resolver._resolve_video_generate_audio(fake_svc, project_name=None)
        assert result is True

    async def test_project_override_string_value(self, tmp_path):
        """專案級覆蓋值為字串時也能正確解析。"""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={"video_generate_audio": "true"})
        with patch("lib.config.resolver.get_project_manager") as mock_pm:
            mock_pm.return_value.load_project.return_value = {"video_generate_audio": "false"}
            result = await resolver._resolve_video_generate_audio(fake_svc, project_name="demo")
        assert result is False


class TestDefaultBackends:
    """驗證 video/image 後端解析：顯式值 vs auto-resolve。"""

    async def test_video_backend_explicit(self):
        """DB 有顯式值時直接返回。"""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(
            settings={"default_video_backend": "ark/doubao-seedance-1-5-pro"},
        )
        result = await resolver._resolve_default_video_backend(fake_svc, None)
        assert result == ("byteplus", "doubao-seedance-1-5-pro")

    async def test_video_backend_auto_resolve(self):
        """DB 無值時走 auto-resolve，選第一個 ready 供應商的預設 video 模型。"""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={})
        # auto-resolve 會在 PROVIDER_REGISTRY 中找到 ready 供應商，不會走到 custom provider 分支
        factory, engine = await _make_session()
        try:
            async with factory() as session:
                result = await resolver._resolve_default_video_backend(fake_svc, session)
            assert result[0] in ("gemini-aistudio", "gemini-vertex", "byteplus", "grok")
        finally:
            await engine.dispose()

    async def test_video_backend_auto_resolve_no_ready_provider(self):
        """無 ready 供應商且無自定義供應商時丟擲 ValueError。"""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={}, ready_providers=[])
        factory, engine = await _make_session()
        try:
            async with factory() as session:
                with pytest.raises(ValueError, match="未找到可用的 video 供應商"):
                    await resolver._resolve_default_video_backend(fake_svc, session)
        finally:
            await engine.dispose()

    async def test_image_backend_explicit(self):
        """DB 有顯式值時直接返回。"""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(
            settings={"default_image_backend": "grok/grok-2-image"},
        )
        result = await resolver._resolve_default_image_backend(fake_svc, None)
        assert result == ("grok", "grok-2-image")

    async def test_image_backend_auto_resolve(self):
        """DB 無值時走 auto-resolve。"""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={})
        factory, engine = await _make_session()
        try:
            async with factory() as session:
                result = await resolver._resolve_default_image_backend(fake_svc, session)
            assert result[0] in ("gemini-aistudio", "gemini-vertex", "byteplus", "grok")
        finally:
            await engine.dispose()

    async def test_image_backend_auto_resolve_no_ready_provider(self):
        """無 ready 供應商且無自定義供應商時丟擲 ValueError。"""
        resolver = ConfigResolver.__new__(ConfigResolver)
        fake_svc = _FakeConfigService(settings={}, ready_providers=[])
        factory, engine = await _make_session()
        try:
            async with factory() as session:
                with pytest.raises(ValueError, match="未找到可用的 image 供應商"):
                    await resolver._resolve_default_image_backend(fake_svc, session)
        finally:
            await engine.dispose()


class TestProviderConfig:
    """驗證供應商配置方法委託給 ConfigService。"""

    async def test_provider_config(self):
        factory, engine = await _make_session()
        try:
            resolver = ConfigResolver.__new__(ConfigResolver)
            fake_svc = _FakeConfigService()
            async with factory() as session:
                result = await resolver._resolve_provider_config(fake_svc, session, "gemini-aistudio")
            assert result == {"api_key": "key-gemini-aistudio"}
        finally:
            await engine.dispose()

    async def test_all_provider_configs(self):
        factory, engine = await _make_session()
        try:
            resolver = ConfigResolver.__new__(ConfigResolver)
            fake_svc = _FakeConfigService()
            async with factory() as session:
                result = await resolver._resolve_all_provider_configs(fake_svc, session)
            assert "gemini-aistudio" in result
        finally:
            await engine.dispose()


class TestSessionReuse:
    """驗證 session() 上下文管理器的 session 複用行為。"""

    async def test_session_context_manager_reuses_single_session(self):
        """resolver.session() 下多次呼叫只建立 1 個 session。"""
        factory, engine = await _make_session()
        try:
            call_count = 0
            real_call = factory.__call__

            def counting_factory():
                nonlocal call_count
                call_count += 1
                return real_call()

            resolver = ConfigResolver(factory)
            fake_backend = ("gemini-aistudio", "test-model")

            # 不使用 session()：每次呼叫建立新 session
            call_count = 0
            with (
                patch.object(resolver, "_session_factory", side_effect=counting_factory),
                patch.object(resolver, "_resolve_default_video_backend", return_value=fake_backend),
                patch.object(resolver, "_resolve_default_image_backend", return_value=fake_backend),
            ):
                await resolver.default_video_backend()
                await resolver.default_image_backend()
            assert call_count == 2, f"不使用 session() 應建立 2 個 session，實際 {call_count}"

            # 使用 session()：只建立 1 個 session
            call_count = 0
            with patch.object(resolver, "_session_factory", side_effect=counting_factory):
                async with resolver.session() as r:
                    with (
                        patch.object(r, "_resolve_default_video_backend", return_value=fake_backend),
                        patch.object(r, "_resolve_default_image_backend", return_value=fake_backend),
                        patch.object(r, "_resolve_video_generate_audio", return_value=False),
                    ):
                        await r.default_video_backend()
                        await r.default_image_backend()
                        await r.video_generate_audio()
            # session() 自身建立 1 個，內部呼叫複用 bound session 不再建立
            assert call_count == 1, f"使用 session() 應只建立 1 個 session，實際 {call_count}"
        finally:
            await engine.dispose()

    async def test_bound_resolver_shares_session_object(self):
        """bound resolver 的 _open_session 返回同一個 session 物件。"""
        factory, engine = await _make_session()
        try:
            resolver = ConfigResolver(factory)
            sessions_seen = []

            async with resolver.session() as r:
                async with r._open_session() as (s1, _):
                    sessions_seen.append(s1)
                async with r._open_session() as (s2, _):
                    sessions_seen.append(s2)

            assert sessions_seen[0] is sessions_seen[1]
        finally:
            await engine.dispose()

    async def test_unbound_resolver_creates_separate_sessions(self):
        """未繫結的 resolver 每次 _open_session 建立不同 session。"""
        factory, engine = await _make_session()
        try:
            resolver = ConfigResolver(factory)
            sessions_seen = []

            async with resolver._open_session() as (s1, _):
                sessions_seen.append(s1)
            async with resolver._open_session() as (s2, _):
                sessions_seen.append(s2)

            assert sessions_seen[0] is not sessions_seen[1]
        finally:
            await engine.dispose()
