from datetime import datetime, timezone

from app.config import settings
from app.ingestion.http import request_with_retry
from app.ingestion.sources import RawRecord

SOURCE_NAME = "threatfox"
API_URL = "https://threatfox-api.abuse.ch/api/v1/"

# ThreatFox ioc_type values -> our canonical types. Anything not listed here
# (e.g. "url_asn", "sha3-384_hash" variants we haven't seen) is skipped rather
# than guessed at.
TYPE_MAP = {
    "domain": "domain",
    "url": "url",
    "ip:port": "ip",
    "md5_hash": "hash",
    "sha1_hash": "hash",
    "sha256_hash": "hash",
}


def fetch(days: int = 3) -> list[RawRecord]:
    response = request_with_retry(
        "POST",
        API_URL,
        headers={"Auth-Key": settings.abusech_auth_key},
        json={"query": "get_iocs", "days": days},
    )
    payload = response.json()

    records = []
    for entry in payload.get("data", []):
        canonical_type = TYPE_MAP.get(entry.get("ioc_type", ""))
        if canonical_type is None:
            continue

        value = entry.get("ioc", "")
        if canonical_type == "ip":
            value = value.split(":")[0]

        first_seen = _parse_date(entry.get("first_seen")) or datetime.now(timezone.utc)
        last_seen = _parse_date(entry.get("last_seen")) or first_seen

        records.append(
            RawRecord(
                indicator_type=canonical_type,
                value=value,
                first_seen=first_seen,
                last_seen=last_seen,
                raw_metadata=entry,
            )
        )
    return records


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
