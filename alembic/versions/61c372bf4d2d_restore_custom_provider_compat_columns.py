"""restore custom provider compatibility columns

Revision ID: 61c372bf4d2d
Revises: 0426endpointrefactor
Create Date: 2026-04-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "61c372bf4d2d"
down_revision: str | Sequence[str] | None = "0426endpointrefactor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    with op.batch_alter_table("custom_provider", schema=None) as batch_op:
        batch_op.add_column(sa.Column("api_format", sa.String(length=32), nullable=True))

    bind.execute(
        sa.text(
            "UPDATE custom_provider SET api_format = CASE discovery_format "
            "WHEN 'google' THEN 'google' "
            "WHEN 'openai' THEN 'openai' "
            "ELSE NULL END"
        )
    )
    unmapped_provider = (
        bind.execute(sa.text("SELECT COUNT(*) FROM custom_provider WHERE api_format IS NULL")).scalar() or 0
    )
    if unmapped_provider:
        raise RuntimeError(f"custom_provider: {unmapped_provider} 條記錄的 discovery_format 無法對映回 api_format")

    with op.batch_alter_table("custom_provider", schema=None) as batch_op:
        batch_op.alter_column("api_format", nullable=False)

    with op.batch_alter_table("custom_provider_model", schema=None) as batch_op:
        batch_op.add_column(sa.Column("media_type", sa.String(length=16), nullable=True))

    bind.execute(
        sa.text(
            "UPDATE custom_provider_model SET media_type = CASE endpoint "
            "WHEN 'openai-chat' THEN 'text' "
            "WHEN 'gemini-generate' THEN 'text' "
            "WHEN 'openai-images' THEN 'image' "
            "WHEN 'gemini-image' THEN 'image' "
            "WHEN 'openai-video' THEN 'video' "
            "WHEN 'newapi-video' THEN 'video' "
            "ELSE NULL END"
        )
    )
    unmapped_model = (
        bind.execute(sa.text("SELECT COUNT(*) FROM custom_provider_model WHERE media_type IS NULL")).scalar() or 0
    )
    if unmapped_model:
        raise RuntimeError(f"custom_provider_model: {unmapped_model} 條記錄的 endpoint 無法對映回 media_type")

    with op.batch_alter_table("custom_provider_model", schema=None) as batch_op:
        batch_op.alter_column("media_type", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("custom_provider_model", schema=None) as batch_op:
        batch_op.drop_column("media_type")

    with op.batch_alter_table("custom_provider", schema=None) as batch_op:
        batch_op.drop_column("api_format")
