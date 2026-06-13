"""rename ark provider to byteplus

Revision ID: f0b1c2d3e4f5
Revises: a1b2c3d4e5f6
Create Date: 2026-05-25 18:35:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "f0b1c2d3e4f5"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE provider_config SET provider = 'byteplus' WHERE provider = 'ark'")
    op.execute("UPDATE provider_credential SET provider = 'byteplus' WHERE provider = 'ark'")
    op.execute("UPDATE api_calls SET provider = 'byteplus' WHERE provider = 'ark'")
    op.execute("UPDATE system_setting SET value = REPLACE(value, 'ark/', 'byteplus/') WHERE value LIKE 'ark/%'")


def downgrade() -> None:
    op.execute("UPDATE provider_config SET provider = 'ark' WHERE provider = 'byteplus'")
    op.execute("UPDATE provider_credential SET provider = 'ark' WHERE provider = 'byteplus'")
    op.execute("UPDATE api_calls SET provider = 'ark' WHERE provider = 'byteplus'")
    op.execute("UPDATE system_setting SET value = REPLACE(value, 'byteplus/', 'ark/') WHERE value LIKE 'byteplus/%'")
