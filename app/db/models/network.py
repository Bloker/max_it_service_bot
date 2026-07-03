"""SQLAlchemy models схемы network."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

from app.db.base import Base


class NetworkToolRun(Base):
    """Запуск сетевого диагностического инструмента."""

    __tablename__ = "tool_runs"
    __table_args__ = (
        Index("idx_network_tool_runs_actor", "actor_user_id", "created_at"),
        Index("idx_network_tool_runs_tool", "tool", "created_at"),
        Index("idx_network_tool_runs_status", "status", "created_at"),
        {"schema": "network"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger)
    actor_name: Mapped[str | None] = mapped_column(Text)
    tool: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_target: Mapped[str | None] = mapped_column(Text)
    policy_decision: Mapped[str | None] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    output_excerpt: Mapped[str | None] = mapped_column(Text)
    error_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    output_truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    feature_enabled: Mapped[bool | None] = mapped_column(Boolean)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


__all__ = ["NetworkToolRun"]
