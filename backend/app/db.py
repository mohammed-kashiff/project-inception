from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


def _psycopg3_url(url: str) -> str:
    # Supabase gives a plain postgresql:// URI; force the psycopg3 driver
    # (SQLAlchemy defaults postgresql:// to psycopg2, which lacks Python 3.14 wheels).
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


engine = create_engine(_psycopg3_url(settings.database_url), pool_pre_ping=True)
# expire_on_commit=False: the default (True) invalidates every loaded object
# after each commit, so the next attribute access on any of them re-fetches
# that single row individually. Fine for occasional commits, but the
# ingestion pipeline commits periodically mid-loop over thousands of
# preloaded rows -- with the default this turned a ~2s bulk query into a
# 200s loop of one-row-at-a-time SELECTs against a remote DB.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
