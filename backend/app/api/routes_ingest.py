from fastapi import APIRouter, Header, HTTPException

from app.api.schemas import IngestTriggerOut
from app.config import settings
from app.ingestion.pipeline import run_source
from app.ingestion.sources import SOURCE_REGISTRY

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/ingest/{source}", response_model=IngestTriggerOut)
def trigger_ingest(source: str, x_ingest_secret: str = Header(default="")):
    # Spoofing mitigation from the TRD threat model: without this, anyone
    # who found the URL could trigger ingestion runs at will.
    if not settings.ingest_shared_secret or x_ingest_secret != settings.ingest_shared_secret:
        raise HTTPException(status_code=401, detail="invalid or missing X-Ingest-Secret")

    if source not in SOURCE_REGISTRY:
        raise HTTPException(status_code=404, detail=f"unknown source '{source}'")

    run = run_source(source)
    return IngestTriggerOut(
        source=source,
        status=run.status,
        record_count=run.record_count,
        error_detail=run.error_detail,
    )
