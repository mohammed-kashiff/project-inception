"""enable row level security on all public tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-21

"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TABLES = [
    "canonical_indicators",
    "indicator_sources",
    "ingestion_runs",
    "rejected_records",
    "alembic_version",
]


def upgrade() -> None:
    # No policies defined on purpose: the app connects as the table owner,
    # which bypasses RLS by default, so this only blocks other roles
    # (e.g. Supabase's anon/authenticated roles) from touching these tables.
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
