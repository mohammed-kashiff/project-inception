from fastapi import FastAPI

from app.api.routes_indicators import router as indicators_router
from app.api.routes_ingest import router as ingest_router
from app.api.routes_sources import router as sources_router

app = FastAPI(title="Project Inception API")
app.include_router(indicators_router)
app.include_router(sources_router)
app.include_router(ingest_router)


@app.get("/health")
def health():
    return {"status": "ok"}
