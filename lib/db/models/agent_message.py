"""Agent message ORM model — persistent transcript for assistant sessions."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from lib.db.base import Base, TimestampMixin


class AgentMessage(TimestampMixin, Base):
    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sdk_session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("agent_sessions.sdk_session_id", ondelete="CASCADE"),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("idx_agent_messages_session_seq", "sdk_session_id", "seq"),)
