from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class IndicatorOut(BaseModel):
    id: UUID
    indicator_type: str
    value: str  # defanged for display
    first_seen: datetime
    last_seen: datetime
    sources: list[str]


class IndicatorListOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[IndicatorOut]


class SourceContributionOut(BaseModel):
    source_name: str
    source_first_seen: datetime
    source_last_seen: datetime
    raw_metadata: dict | None


class IndicatorDetailOut(BaseModel):
    id: UUID
    indicator_type: str
    value: str  # defanged for display
    first_seen: datetime
    last_seen: datetime
    sources: list[SourceContributionOut]


class SourceHealthOut(BaseModel):
    source_name: str
    last_run_status: str | None
    last_run_started_at: datetime | None
    last_run_finished_at: datetime | None
    last_run_record_count: int | None
    last_run_error: str | None


class VolumePointOut(BaseModel):
    date: str
    record_count: int


class IngestTriggerOut(BaseModel):
    source: str
    status: str
    record_count: int | None
    error_detail: str | None
