"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Create the enum type explicitly, then use create_type=False on the column
    # definition below -- otherwise create_table() tries to CREATE TYPE a second
    # time in the same transaction and the migration aborts on a duplicate-object error.
    postgresql.ENUM("ip", "domain", "url", "hash", "cve", name="indicator_type").create(
        op.get_bind(), checkfirst=True
    )
    indicator_type = postgresql.ENUM(
        "ip", "domain", "url", "hash", "cve", name="indicator_type", create_type=False
    )

    op.create_table(
        "canonical_indicators",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("indicator_type", indicator_type, nullable=False),
        sa.Column("value_normalized", sa.Text(), nullable=False),
        sa.Column("value_raw", sa.Text(), nullable=False),
        sa.Column("dedup_key", sa.Text(), nullable=False, unique=True),
        sa.Column("first_seen", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_seen", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_canonical_type", "canonical_indicators", ["indicator_type"])
    op.create_index("idx_canonical_last_seen", "canonical_indicators", ["last_seen"])

    op.create_table(
        "indicator_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "indicator_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("canonical_indicators.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("source_first_seen", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("source_last_seen", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("raw_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("indicator_id", "source_name", name="uq_indicator_source"),
    )
    op.create_index("idx_sources_indicator", "indicator_sources", ["indicator_id"])
    op.create_index("idx_sources_name", "indicator_sources", ["source_name"])

    op.create_table(
        "ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('running','success','failed','partial')", name="ck_ingestion_runs_status"),
    )
    op.create_index("idx_runs_source", "ingestion_runs", ["source_name", "started_at"])

    op.create_table(
        "rejected_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("rejected_records")
    op.drop_index("idx_runs_source", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_index("idx_sources_name", table_name="indicator_sources")
    op.drop_index("idx_sources_indicator", table_name="indicator_sources")
    op.drop_table("indicator_sources")
    op.drop_index("idx_canonical_last_seen", table_name="canonical_indicators")
    op.drop_index("idx_canonical_type", table_name="canonical_indicators")
    op.drop_table("canonical_indicators")
    postgresql.ENUM(name="indicator_type").drop(op.get_bind(), checkfirst=True)
