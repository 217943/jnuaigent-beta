from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    user_role: Mapped[str | None] = mapped_column(String(120))
    modality_pref: Mapped[str | None] = mapped_column(String(120))
    request_text: Mapped[str] = mapped_column(String(500), nullable=False)
    tools_hint: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    triage_json: Mapped[str] = mapped_column(Text, nullable=False)
    triage_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    risk_flags_json: Mapped[str] = mapped_column(Text, nullable=False)

    decision: Mapped["Decision"] = relationship(
        "Decision", back_populates="request", uselist=False
    )


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("requests.id"), nullable=False
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    final_topic: Mapped[str | None] = mapped_column(String(120))
    final_difficulty: Mapped[str | None] = mapped_column(String(120))
    final_handler: Mapped[str | None] = mapped_column(String(120))
    note: Mapped[str | None] = mapped_column(Text)

    request: Mapped[Request] = relationship("Request", back_populates="decision")
