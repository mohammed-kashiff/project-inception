from datetime import datetime, timezone

from app.ingestion.http import request_with_retry
from app.ingestion.sources import RawRecord

SOURCE_NAME = "cisa_kev"
FEED_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"


def fetch() -> list[RawRecord]:
    response = request_with_retry("GET", FEED_URL)
    data = response.json()

    records = []
    for vuln in data.get("vulnerabilities", []):
        date_added = _parse_date(vuln.get("dateAdded"))
        records.append(
            RawRecord(
                indicator_type="cve",
                value=vuln.get("cveID", ""),
                first_seen=date_added,
                last_seen=date_added,
                raw_metadata=vuln,
            )
        )
    return records


def _parse_date(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
