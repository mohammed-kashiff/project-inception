from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import SourceHealthOut, VolumePointOut
from app.db import get_db
from app.ingestion.sources import SOURCE_REGISTRY
from app.models import IngestionRun

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("", response_model=list[SourceHealthOut])
def list_source_health(db: Session = Depends(get_db)):
    results = []
    for source_name in SOURCE_REGISTRY:
        latest = db.execute(
            select(IngestionRun)
            .where(IngestionRun.source_name == source_name)
            .order_by(IngestionRun.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        results.append(
            SourceHealthOut(
                source_name=source_name,
                last_run_status=latest.status if latest else None,
                last_run_started_at=latest.started_at if latest else None,
                last_run_finished_at=latest.finished_at if latest else None,
                last_run_record_count=latest.record_count if latest else None,
                last_run_error=latest.error_detail if latest else None,
            )
        )
    return results


@router.get("/{source_name}/volume", response_model=list[VolumePointOut])
def source_volume(source_name: str, days: int = Query(default=30, le=365, ge=1), db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    day_col = func.date(IngestionRun.started_at)

    rows = db.execute(
        select(day_col.label("day"), func.coalesce(func.sum(IngestionRun.record_count), 0).label("total"))
        .where(
            IngestionRun.source_name == source_name,
            IngestionRun.started_at >= since,
            IngestionRun.status.in_(["success", "partial"]),
        )
        .group_by(day_col)
        .order_by(day_col)
    ).all()

    return [VolumePointOut(date=str(r.day), record_count=r.total) for r in rows]
