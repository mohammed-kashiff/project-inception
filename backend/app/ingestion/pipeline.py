import uuid
from datetime import datetime, timezone

from app.db import SessionLocal
from app.ingestion.normalize import InvalidIndicator, dedup_key, normalize
from app.ingestion.sources import SOURCE_REGISTRY
from app.models import CanonicalIndicator, IndicatorSource, IngestionRun, RejectedRecord

BATCH_COMMIT_SIZE = 200


def run_source(source_name: str) -> IngestionRun:
    """Fetch + normalize + dedup + persist one source's indicators.

    Always returns a completed IngestionRun row rather than raising -- a
    failure here (network down, source rate-limited, etc.) must not crash
    the caller or block other sources (FR4), and every run must be visible
    in ingestion_runs regardless of outcome (FR3).

    Performance note: this preloads existing rows in bulk and assigns UUIDs
    client-side rather than doing a SELECT + flush per record. A naive
    per-record round trip to a remote Postgres instance (Supabase, often
    100-300ms away) made even a few thousand records take minutes.
    """
    if source_name not in SOURCE_REGISTRY:
        raise ValueError(f"unknown source '{source_name}'")

    db = SessionLocal()
    run = IngestionRun(source_name=source_name, started_at=datetime.now(timezone.utc), status="running")
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        raw_records = SOURCE_REGISTRY[source_name]()
    except Exception as exc:  # noqa: BLE001 -- deliberately broad: any fetch failure ends the run cleanly
        run.status = "failed"
        run.error_detail = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.close()
        return run

    rejected_count = 0
    valid: list[tuple] = []  # (record, normalized_value, dedup_key)

    for record in raw_records:
        try:
            normalized_value = normalize(record.indicator_type, record.value)
            key = dedup_key(record.indicator_type, normalized_value)
            valid.append((record, normalized_value, key))
        except InvalidIndicator as exc:
            db.add(RejectedRecord(run_id=run.id, source_name=source_name, raw_value=record.value, reason=str(exc)))
            rejected_count += 1
        except Exception as exc:  # noqa: BLE001 -- one bad record must not abort the whole run
            db.add(
                RejectedRecord(
                    run_id=run.id, source_name=source_name, raw_value=record.value, reason=f"unexpected error: {exc}"
                )
            )
            rejected_count += 1
    db.commit()

    existing_indicators = {
        row.dedup_key: row
        for row in db.query(CanonicalIndicator)
        .filter(CanonicalIndicator.dedup_key.in_([key for _, _, key in valid]))
        .all()
    }
    existing_ids = [row.id for row in existing_indicators.values()]
    existing_sources = {
        row.indicator_id: row
        for row in (
            db.query(IndicatorSource)
            .filter(IndicatorSource.indicator_id.in_(existing_ids), IndicatorSource.source_name == source_name)
            .all()
            if existing_ids
            else []
        )
    }

    success_count = 0
    for record, normalized_value, key in valid:
        now = datetime.now(timezone.utc)
        indicator = existing_indicators.get(key)
        if indicator is None:
            # created_at/updated_at set explicitly (not left to the column's
            # server_default) so SQLAlchemy doesn't need a RETURNING round
            # trip per row to read them back -- that alone was ~12x slower
            # for bulk inserts over a remote connection.
            indicator = CanonicalIndicator(
                id=uuid.uuid4(),
                indicator_type=record.indicator_type,
                value_normalized=normalized_value,
                value_raw=record.value,
                dedup_key=key,
                first_seen=record.first_seen,
                last_seen=record.last_seen,
                created_at=now,
                updated_at=now,
            )
            db.add(indicator)
            existing_indicators[key] = indicator  # merges duplicate keys within this same batch
        else:
            # Only touch the row (and generate an UPDATE) when a value
            # actually changes -- unconditionally re-writing updated_at on
            # every already-current row turns a re-run into one UPDATE
            # round trip per existing indicator for no reason.
            changed = False
            if record.last_seen > indicator.last_seen:
                indicator.last_seen = record.last_seen
                changed = True
            if record.first_seen < indicator.first_seen:
                indicator.first_seen = record.first_seen
                changed = True
            if changed:
                indicator.updated_at = now

        source_row = existing_sources.get(indicator.id)
        if source_row is None:
            source_row = IndicatorSource(
                id=uuid.uuid4(),
                indicator_id=indicator.id,
                source_name=source_name,
                source_first_seen=record.first_seen,
                source_last_seen=record.last_seen,
                raw_metadata=record.raw_metadata,
                created_at=now,
            )
            db.add(source_row)
            existing_sources[indicator.id] = source_row
        elif source_row.source_last_seen != record.last_seen or source_row.raw_metadata != record.raw_metadata:
            source_row.source_last_seen = record.last_seen
            source_row.raw_metadata = record.raw_metadata

        success_count += 1
        if success_count % BATCH_COMMIT_SIZE == 0:
            db.commit()

    db.commit()

    if success_count == 0 and rejected_count > 0:
        run.status = "failed"
    elif rejected_count > 0:
        run.status = "partial"
    else:
        run.status = "success"

    run.record_count = success_count
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.close()
    return run
