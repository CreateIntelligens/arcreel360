"""TextGenerator — 文字生成 + 用量追蹤包裝層。

類似 MediaGenerator，組合 TextBackend + UsageTracker，
呼叫方無需關心 usage tracking 細節。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from lib.text_backends.base import (
    TextGenerationRequest,
    TextGenerationResult,
    TextTaskType,
)
from lib.text_backends.factory import create_text_backend_for_task
from lib.usage_tracker import UsageTracker

if TYPE_CHECKING:
    from lib.text_backends.base import TextBackend

logger = logging.getLogger(__name__)


class TextGenerator:
    """組合 TextBackend + UsageTracker，統一封裝文字生成 + 用量追蹤。"""

    def __init__(self, backend: TextBackend, usage_tracker: UsageTracker):
        self.backend = backend
        self.usage_tracker = usage_tracker

    @property
    def model(self) -> str:
        """當前 backend 的模型名稱。"""
        return self.backend.model

    @classmethod
    async def create(
        cls,
        task_type: TextTaskType,
        project_name: str | None = None,
    ) -> TextGenerator:
        """工廠方法：根據任務型別建立對應的 backend + usage_tracker。"""
        backend = await create_text_backend_for_task(task_type, project_name)
        usage_tracker = UsageTracker()
        return cls(backend, usage_tracker)

    @classmethod
    async def create_with_model_str(
        cls,
        model_str: str,
    ) -> TextGenerator:
        """根據指定的 model_str 建立對應的 backend + usage_tracker。"""
        from lib.text_backends.factory import create_text_backend_by_model_str

        backend = await create_text_backend_by_model_str(model_str)
        usage_tracker = UsageTracker()
        return cls(backend, usage_tracker)

    async def generate(
        self,
        request: TextGenerationRequest,
        project_name: str | None = None,
    ) -> TextGenerationResult:
        """生成文字並自動記錄用量。"""
        call_id = await self.usage_tracker.start_call(
            project_name=project_name or "",
            call_type="text",
            model=self.backend.model,
            prompt=request.prompt[:500],
            provider=self.backend.name,
        )
        try:
            result = await self.backend.generate(request)
            await self.usage_tracker.finish_call(
                call_id,
                status="success",
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
            )
            return result
        except Exception as e:
            await self.usage_tracker.finish_call(
                call_id,
                status="failed",
                error_message=str(e)[:500],
            )
            raise
