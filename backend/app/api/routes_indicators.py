import csv
import io
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import IndicatorDetailOut, IndicatorListOut, IndicatorOut, SourceContributionOut
from app.db import get_db
from app.defang import defang
from app.models import CanonicalIndicator, IndicatorSource

router = APIRouter(prefix="/api", tags=["indicators"])


def _apply_filters(query, indicator_type: str | None, source: str | None, q: str | None,
                    date_from: datetime | None, date_to: datetime | None):
    if indicator_type:
        query = query.where(CanonicalIndicator.indicator_type == indicator_type)
    if q:
        query = query.where(CanonicalIndicator.value_normalized.ilike(f"%{q}%"))
    if date_from:
        query = query.where(CanonicalIndicator.last_seen >= date_from)
    if date_to:
        query = query.where(CanonicalIndicator.last_seen <= date_to)
    if source:
        query = query.where(
            CanonicalIndicator.id.in_(
                select(IndicatorSource.indicator_id).where(IndicatorSource.source_name == source)
            )
        )
    return query


@router.get("/indicators", response_model=IndicatorListOut)
def list_indicators(
    type: str | None = Query(default=None, alias="type"),
    source: str | None = None,
    q: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=50, le=200, ge=1),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    base = select(CanonicalIndicator)
    base = _apply_filters(base, type, source, q, date_from, date_to)

    count_query = _apply_filters(select(func.count(CanonicalIndicator.id)), type, source, q, date_from, date_to)
    total = db.execute(count_query).scalar_one()
    rows = (
        db.execute(base.order_by(CanonicalIndicator.last_seen.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )

    ids = [r.id for r in rows]
    sources_by_indicator: dict = {}
    if ids:
        for row in db.execute(
            select(IndicatorSource.indicator_id, IndicatorSource.source_name).where(
                IndicatorSource.indicator_id.in_(ids)
            )
        ):
            sources_by_indicator.setdefault(row.indicator_id, []).append(row.source_name)

    items = [
        IndicatorOut(
            id=r.id,
            indicator_type=r.indicator_type,
            value=defang(r.indicator_type, r.value_normalized),
            first_seen=r.first_seen,
            last_seen=r.last_seen,
            sources=sources_by_indicator.get(r.id, []),
        )
        for r in rows
    ]
    return IndicatorListOut(total=total, limit=limit, offset=offset, items=items)


@router.get("/indicators/export")
def export_indicators(
    format: str = Query(default="json", pattern="^(csv|json)$"),
    type: str | None = Query(default=None, alias="type"),
    source: str | None = None,
    q: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    raw: bool = False,
    db: Session = Depends(get_db),
):
    base = select(CanonicalIndicator)
    base = _apply_filters(base, type, source, q, date_from, date_to)
    rows = db.execute(base.order_by(CanonicalIndicator.last_seen.desc())).scalars().all()

    ids = [r.id for r in rows]
    sources_by_indicator: dict = {}
    if ids:
        for row in db.execute(
            select(IndicatorSource.indicator_id, IndicatorSource.source_name).where(
                IndicatorSource.indicator_id.in_(ids)
            )
        ):
            sources_by_indicator.setdefault(row.indicator_id, []).append(row.source_name)

    def render_value(r: CanonicalIndicator) -> str:
        return r.value_normalized if raw else defang(r.indicator_type, r.value_normalized)

    if format == "json":
        payload = [
            {
                "id": str(r.id),
                "indicator_type": r.indicator_type,
                "value": render_value(r),
                "first_seen": r.first_seen.isoformat(),
                "last_seen": r.last_seen.isoformat(),
                "sources": sources_by_indicator.get(r.id, []),
            }
            for r in rows
        ]
        return StreamingResponse(
            io.StringIO(json.dumps(payload, indent=2)),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=indicators.json"},
        )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "indicator_type", "value", "first_seen", "last_seen", "sources"])
    for r in rows:
        writer.writerow(
            [
                str(r.id),
                r.indicator_type,
                render_value(r),
                r.first_seen.isoformat(),
                r.last_seen.isoformat(),
                ";".join(sources_by_indicator.get(r.id, [])),
            ]
        )
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=indicators.csv"},
    )


@router.get("/indicators/{indicator_id}", response_model=IndicatorDetailOut)
def get_indicator(indicator_id: str, db: Session = Depends(get_db)):
    try:
        parsed_id = uuid.UUID(indicator_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="indicator not found")

    row = db.get(CanonicalIndicator, parsed_id)
    if row is None:
        raise HTTPException(status_code=404, detail="indicator not found")

    source_rows = db.execute(
        select(IndicatorSource).where(IndicatorSource.indicator_id == row.id)
    ).scalars().all()

    return IndicatorDetailOut(
        id=row.id,
        indicator_type=row.indicator_type,
        value=defang(row.indicator_type, row.value_normalized),
        first_seen=row.first_seen,
        last_seen=row.last_seen,
        sources=[
            SourceContributionOut(
                source_name=s.source_name,
                source_first_seen=s.source_first_seen,
                source_last_seen=s.source_last_seen,
                raw_metadata=s.raw_metadata,
            )
            for s in source_rows
        ],
    )
