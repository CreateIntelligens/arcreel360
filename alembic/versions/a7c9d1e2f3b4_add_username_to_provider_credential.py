"""add username to provider_credential

Revision ID: a7c9d1e2f3b4
Revises: f0b1c2d3e4f5
Create Date: 2026-06-05 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7c9d1e2f3b4"
down_revision: str | Sequence[str] | None = "f0b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("provider_credential", sa.Column("username", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("provider_credential", "username")
