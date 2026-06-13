"""驗證 `gemini-full` provider 路由到 ADK 實作。

`ASSISTANT_GEMINI_FULL_BACKEND` env var 已移除,ADK 是 `gemini-full` 的唯一實作;
此測試確認 registry 中 `gemini-full` key 始終對應 `AdkGeminiFullRuntimeProvider`。
"""

import pytest

from server.agent_runtime.adk_gemini_full_runtime_provider import AdkGeminiFullRuntimeProvider
from server.agent_runtime.openai_full_runtime_provider import OpenAIFullRuntimeProvider
from server.agent_runtime.service import AssistantService
from server.agent_runtime.session_identity import GEMINI_FULL_PROVIDER_ID, OPENAI_FULL_PROVIDER_ID


@pytest.fixture
def project_root(tmp_path):
    (tmp_path / "projects").mkdir()
    return tmp_path


def test_gemini_full_routes_to_adk_provider(project_root):
    service = AssistantService(project_root)
    provider = service.runtime_provider_registry[GEMINI_FULL_PROVIDER_ID]
    assert isinstance(provider, AdkGeminiFullRuntimeProvider)


def test_openai_full_routes_to_openai_agents_provider(project_root):
    service = AssistantService(project_root)
    provider = service.runtime_provider_registry[OPENAI_FULL_PROVIDER_ID]
    assert isinstance(provider, OpenAIFullRuntimeProvider)
