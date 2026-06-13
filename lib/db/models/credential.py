"""Provider credential ORM model."""

from __future__ import annotations

from sqlalchemy import Boolean, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from lib.db.base import Base, TimestampMixin


class ProviderCredential(TimestampMixin, Base):
    """供應商憑證。每個供應商可有多條憑證，其中最多一條 is_active=True。"""

    __tablename__ = "provider_credential"
    __table_args__ = (
        Index("ix_provider_credential_provider", "provider"),
        Index(
            "uq_provider_credential_one_active",
            "provider",
            unique=True,
            sqlite_where=text("is_active = 1"),
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 帳密型供應商（如 ai360）的使用者名稱；password 沿用 api_key 欄不適用，故 username 獨立成欄
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    credentials_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    def overlay_config(self, config: dict[str, str]) -> dict[str, str]:
        """將憑證欄位合併到配置字典中，返回修改後的 config。"""
        if self.api_key:
            config["api_key"] = self.api_key
        if self.username:
            config["username"] = self.username
        if self.credentials_path:
            config["credentials_path"] = self.credentials_path
        if self.base_url:
            config["base_url"] = self.base_url
        return config
