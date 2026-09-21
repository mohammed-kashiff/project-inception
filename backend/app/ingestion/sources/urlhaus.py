from datetime import datetime, timezone

from app.config import settings
from app.ingestion.http import request_with_retry
from app.ingestion.sources import RawRecord

SOURCE_NAME = "urlhaus"
FEED_URL = "https://urlhaus-api.abuse.ch/v1/urls/recent/"


def fetch() -> list[RawRecord]:
    response = request_with_retry(
        "GET", FEED_URL, headers={"Auth-Key": settings.abusech_auth_key}
    )
    data = response.json()

    records = []
    for entry in data.get("urls", []):
        seen = _parse_date(entry.get("date_added"))
        records.append(
            RawRecord(
                indicator_type="url",
                value=entry.get("url", ""),
                first_seen=seen,
                last_seen=seen,
                raw_metadata=entry,
            )
        )
    return records


def _parse_date(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    value = value.removesuffix(" UTC")
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
