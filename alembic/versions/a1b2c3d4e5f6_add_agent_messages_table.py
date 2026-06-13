"""add agent_messages table for persistent assistant transcript

Revision ID: a1b2c3d4e5f6
Revises: 61c372bf4d2d
Create Date: 2026-05-07 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "61c372bf4d2d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sdk_session_id", sa.String(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["sdk_session_id"],
            ["agent_sessions.sdk_session_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "idx_agent_messages_session_seq",
        "agent_messages",
        ["sdk_session_id", "seq"],
    )


def downgrade() -> None:
    op.drop_index("idx_agent_messages_session_seq", table_name="agent_messages")
    op.drop_table("agent_messages")
