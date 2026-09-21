from dataclasses import dataclass
from datetime import datetime


@dataclass
class RawRecord:
    indicator_type: str  # ip | domain | url | hash | cve -- pre-canonical-type mapping
    value: str
    first_seen: datetime
    last_seen: datetime
    raw_metadata: dict


from app.ingestion.sources import cisa_kev, otx, threatfox, urlhaus  # noqa: E402

SOURCE_REGISTRY = {
    "otx": otx.fetch,
    "urlhaus": urlhaus.fetch,
    "threatfox": threatfox.fetch,
    "cisa_kev": cisa_kev.fetch,
}
