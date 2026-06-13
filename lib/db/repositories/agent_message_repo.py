"""Async repository for agent transcript messages."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select

from lib.db.models.agent_message import AgentMessage
from lib.db.repositories.base import BaseRepository


class AgentMessageRepository(BaseRepository):
    async def append(self, sdk_session_id: str, message: dict[str, Any]) -> int:
        next_seq = await self._next_seq(sdk_session_id)
        row = AgentMessage(
            sdk_session_id=sdk_session_id,
            seq=next_seq,
            payload=json.dumps(message, ensure_ascii=False),
        )
        self.session.add(row)
        await self.session.commit()
        return next_seq

    async def list(self, sdk_session_id: str) -> list[dict[str, Any]]:
        stmt = (
            select(AgentMessage).where(AgentMessage.sdk_session_id == sdk_session_id).order_by(AgentMessage.seq.asc())
        )
        result = await self.session.execute(stmt)
        return [json.loads(row.payload) for row in result.scalars().all()]

    async def delete_for_session(self, sdk_session_id: str) -> int:
        result = await self.session.execute(
            sa_delete(AgentMessage).where(AgentMessage.sdk_session_id == sdk_session_id)
        )
        await self.session.commit()
        return result.rowcount or 0

    async def _next_seq(self, sdk_session_id: str) -> int:
        stmt = select(func.coalesce(func.max(AgentMessage.seq), -1)).where(
            AgentMessage.sdk_session_id == sdk_session_id
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one()) + 1
