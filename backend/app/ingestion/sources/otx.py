from datetime import datetime, timedelta, timezone

from app.config import settings
from app.ingestion.http import request_with_retry
from app.ingestion.sources import RawRecord

SOURCE_NAME = "otx"
BASE_URL = "https://otx.alienvault.com/api/v1/pulses/activity"

# OTX indicator "type" values -> our canonical types. CIDR ranges and
# less-common types (Mutex, YARA, email, ...) are intentionally skipped --
# our schema models single-value indicators, not ranges or rule blobs.
TYPE_MAP = {
    "IPv4": "ip",
    "IPv6": "ip",
    "domain": "domain",
    "hostname": "domain",
    "URL": "url",
    "URI": "url",
    "FileHash-MD5": "hash",
    "FileHash-SHA1": "hash",
    "FileHash-SHA256": "hash",
    "CVE": "cve",
}

MAX_PAGES = 5  # demo-scale guardrail; avoids pulling unbounded history on first run


def fetch(lookback_hours: int = 24) -> list[RawRecord]:
    since = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).strftime("%Y-%m-%dT%H:%M:%S")
    headers = {"X-OTX-API-KEY": settings.otx_api_key}

    records: list[RawRecord] = []
    url = BASE_URL
    params = {"modified_since": since, "limit": 50}

    for _ in range(MAX_PAGES):
        response = request_with_retry("GET", url, headers=headers, params=params)
        payload = response.json()

        for pulse in payload.get("results", []):
            for indicator in pulse.get("indicators", []):
                canonical_type = TYPE_MAP.get(indicator.get("type", ""))
                if canonical_type is None:
                    continue

                created = _parse_date(indicator.get("created"))
                records.append(
                    RawRecord(
                        indicator_type=canonical_type,
                        value=indicator.get("indicator", ""),
                        first_seen=created,
                        last_seen=created,
                        raw_metadata={"pulse_id": pulse.get("id"), "pulse_name": pulse.get("name"), **indicator},
                    )
                )

        next_url = payload.get("next")
        if not next_url:
            break
        url, params = next_url, None  # `next` is a full URL with its own query string

    return records


def _parse_date(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    # OTX inconsistently includes fractional seconds; fromisoformat handles both.
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
