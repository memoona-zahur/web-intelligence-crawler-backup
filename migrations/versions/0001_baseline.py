"""Baseline: the schema as it was at the end of Phase 1 (tag crawler-baseline-v1).

Idempotent: tables that already exist (an old data/websites.db, or a test database made with create_all) are left alone.

Revision ID: 0001_baseline
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    existing = _tables()
    if "jobs" not in existing:
        op.create_table(
            "jobs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("added", sa.Integer(), nullable=False),
            sa.Column("duplicates", sa.Integer(), nullable=False),
            sa.Column("invalid", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
        )
        op.create_index("ix_jobs_status", "jobs", ["status"])
        op.create_index("ix_jobs_kind", "jobs", ["kind"])
    if "websites" not in existing:
        op.create_table(
            "websites",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("original_url", sa.String(2048), nullable=False),
            sa.Column("normalized_website", sa.String(2048), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=True),
            sa.Column("source_batch", sa.String(255), nullable=True),
            sa.Column("clean_text", sa.Text(), nullable=True),
            sa.Column("crawl_error", sa.Text(), nullable=True),
            sa.Column("pages_crawled", sa.Integer(), nullable=True),
            sa.Column("last_crawled_at", sa.DateTime(), nullable=True),
            sa.Column("claimed_at", sa.DateTime(), nullable=True),
            sa.Column("company_name", sa.String(512), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("business_type", sa.String(64), nullable=True),
            sa.Column("industry", sa.String(128), nullable=True),
            sa.Column("niche", sa.String(128), nullable=True),
            sa.Column("products", sa.Text(), nullable=True),
            sa.Column("services", sa.Text(), nullable=True),
            sa.Column("confidence", sa.Integer(), nullable=True),
            sa.Column("evidence", sa.Text(), nullable=True),
            sa.Column("classification_meta", sa.Text(), nullable=True),
            sa.Column("crawl_status", sa.String(32), nullable=True),
            sa.Column("classification_status", sa.String(32), nullable=True),
            sa.Column("content_hash", sa.String(64), nullable=True),
            sa.Column("secondary_industry", sa.String(255), nullable=True),
            sa.Column("sub_niche", sa.String(255), nullable=True),
            sa.Column("business_model", sa.String(255), nullable=True),
            sa.Column("geographic_markets", sa.String(512), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_websites_normalized_website", "websites", ["normalized_website"], unique=True)
        op.create_index("ix_websites_job_id", "websites", ["job_id"])
        for name, col in (
            ("ix_websites_status", "status"), ("ix_websites_industry", "industry"),
            ("ix_websites_business_type", "business_type"), ("ix_websites_confidence", "confidence"),
            ("ix_websites_crawl_status", "crawl_status"), ("ix_websites_classification_status", "classification_status"),
        ):
            op.create_index(name, "websites", [col])
    if "evidence_records" not in existing:
        op.create_table(
            "evidence_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("website_id", sa.Integer(), sa.ForeignKey("websites.id"), nullable=False),
            sa.Column("field", sa.String(64), nullable=False),
            sa.Column("quote", sa.Text(), nullable=False),
            sa.Column("page", sa.String(80), nullable=False),
            sa.Column("source_url", sa.String(2048), nullable=False),
            sa.Column("method", sa.String(32), nullable=False),
            sa.Column("quality", sa.String(32), nullable=False),
            sa.Column("confidence", sa.Integer(), nullable=True),
            sa.Column("retrieved_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_evidence_records_website_id", "evidence_records", ["website_id"])
    if "domain_stats" not in existing:
        op.create_table(
            "domain_stats",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("domain", sa.String(255), unique=True, nullable=False),
            sa.Column("last_latency_ms", sa.Integer(), nullable=True),
            sa.Column("last_status", sa.String(32), nullable=False),
            sa.Column("last_success_at", sa.DateTime(), nullable=True),
            sa.Column("success_count", sa.Integer(), nullable=False),
            sa.Column("failure_count", sa.Integer(), nullable=False),
        )


def downgrade() -> None:
    for table in ("domain_stats", "evidence_records", "websites", "jobs"):
        op.drop_table(table)
