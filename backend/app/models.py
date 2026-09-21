import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ENUM, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

IndicatorType = ENUM(
    "ip", "domain", "url", "hash", "cve",
    name="indicator_type",
    create_type=True,
)


class CanonicalIndicator(Base):
    __tablename__ = "canonical_indicators"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    indicator_type: Mapped[str] = mapped_column(IndicatorType, nullable=False)
    value_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    value_raw: Mapped[str] = mapped_column(Text, nullable=False)
    dedup_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    first_seen: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default="now()")

    sources: Mapped[list["IndicatorSource"]] = relationship(back_populates="indicator", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_canonical_type", "indicator_type"),
        Index("idx_canonical_last_seen", "last_seen"),
    )


class IndicatorSource(Base):
    __tablename__ = "indicator_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    indicator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_indicators.id", ondelete="CASCADE"), nullable=False
    )
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_first_seen: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    source_last_seen: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    raw_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default="now()")

    indicator: Mapped["CanonicalIndicator"] = relationship(back_populates="sources")

    __table_args__ = (
        UniqueConstraint("indicator_id", "source_name", name="uq_indicator_source"),
        Index("idx_sources_indicator", "indicator_id"),
        Index("idx_sources_name", "source_name"),
    )


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('running','success','failed','partial')", name="ck_ingestion_runs_status"),
        Index("idx_runs_source", "source_name", "started_at"),
    )


class RejectedRecord(Base):
    __tablename__ = "rejected_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="SET NULL"), nullable=True
    )
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default="now()")
