"""Phase 2 crawl schema: crawl facts on websites, queue, pages, contents, attempts, errors, import issues, domain health.

Idempotent on purpose: a database created with Base.metadata.create_all (unit tests, the evaluation harness) already has these objects.

Revision ID: 0002_phase2_crawl_schema
Revises: 0001_baseline
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_phase2_crawl_schema"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

WEBSITE_COLUMNS = [
    ("source_file", sa.String(255)), ("source_record_id", sa.String(255)), ("domain_key", sa.String(255)),
    ("final_url", sa.String(2048)), ("http_status", sa.Integer()), ("website_status", sa.String(32)),
    ("crawl_outcome", sa.String(32)), ("crawl_error_category", sa.String(32)), ("pages_attempted", sa.Integer()),
    ("retry_count", sa.Integer()), ("next_retry_at", sa.DateTime()), ("content_crawled_at", sa.DateTime()),
    ("content_is_stale", sa.Boolean()), ("truncation_note", sa.Text()),
]
JOB_COLUMNS = [("total", sa.Integer()), ("done_count", sa.Integer()), ("failed_count", sa.Integer()), ("source_file", sa.String(255))]
DOMAIN_COLUMNS = [
    ("avg_latency_ms", sa.Integer()), ("consecutive_failures", sa.Integer()), ("last_attempt_at", sa.DateTime()),
    ("backoff_until", sa.DateTime()), ("crawl_delay", sa.Float()), ("blocked_at", sa.DateTime()), ("blocked_reason", sa.String(255)),
]
ACTIVE = "state IN ('queued','claimed','crawling','extracting','retry_scheduled')"
RUNNING = "state IN ('claimed','crawling','extracting')"


def _insp():
    return sa.inspect(op.get_bind())


def _add_columns(table: str, columns) -> None:
    have = {c["name"] for c in _insp().get_columns(table)}
    for name, type_ in columns:
        if name not in have:
            op.add_column(table, sa.Column(name, type_, nullable=True))
    # numeric defaults for rows that existed before
    zero = {"retry_count": 0, "content_is_stale": False, "total": 0, "done_count": 0, "failed_count": 0, "consecutive_failures": 0}
    for name, value in zero.items():
        if name in {n for n, _t in columns}:
            op.execute(sa.text(f"UPDATE {table} SET {name} = :v WHERE {name} IS NULL").bindparams(v=value))


def _index(name: str, table: str, cols, unique=False, where=None) -> None:
    if name in {i["name"] for i in _insp().get_indexes(table)}:
        return
    kwargs = {}
    if where:
        kwargs = {"postgresql_where": sa.text(where), "sqlite_where": sa.text(where)}
    op.create_index(name, table, cols, unique=unique, **kwargs)


def upgrade() -> None:
    _add_columns("websites", WEBSITE_COLUMNS)
    _add_columns("jobs", JOB_COLUMNS)
    _add_columns("domain_stats", DOMAIN_COLUMNS)
    _index("ix_websites_domain_key", "websites", ["domain_key"])
    existing = set(_insp().get_table_names())

    if "crawl_tasks" not in existing:
        op.create_table(
            "crawl_tasks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("website_id", sa.Integer(), sa.ForeignKey("websites.id"), nullable=False),
            sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=True),
            sa.Column("domain_key", sa.String(255), nullable=False),
            sa.Column("state", sa.String(24), nullable=False),
            sa.Column("attempt", sa.Integer(), nullable=False),
            sa.Column("max_attempts", sa.Integer(), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False),
            sa.Column("not_before", sa.DateTime(), nullable=True),
            sa.Column("lease_until", sa.DateTime(), nullable=True),
            sa.Column("worker_id", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
        )
    _index("ix_crawl_tasks_website_id", "crawl_tasks", ["website_id"])
    _index("ix_crawl_tasks_job_id", "crawl_tasks", ["job_id"])
    _index("ix_crawl_tasks_state", "crawl_tasks", ["state", "not_before"])
    _index("ix_crawl_tasks_domain", "crawl_tasks", ["domain_key"])
    _index("uq_crawl_tasks_active_website", "crawl_tasks", ["website_id"], unique=True, where=ACTIVE)
    _index("uq_crawl_tasks_running_domain", "crawl_tasks", ["domain_key"], unique=True, where=RUNNING)

    if "pages" not in existing:
        op.create_table(
            "pages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("website_id", sa.Integer(), sa.ForeignKey("websites.id"), nullable=False),
            sa.Column("job_id", sa.Integer(), nullable=True),
            sa.Column("url", sa.String(2048), nullable=False),
            sa.Column("canonical_url", sa.String(2048), nullable=True),
            sa.Column("page_type", sa.String(32), nullable=False),
            sa.Column("discovery_source", sa.String(32), nullable=False),
            sa.Column("rank_score", sa.Integer(), nullable=False),
            sa.Column("title", sa.Text(), nullable=True),
            sa.Column("http_status", sa.Integer(), nullable=True),
            sa.Column("crawl_status", sa.String(24), nullable=False),
            sa.Column("method", sa.String(16), nullable=False),
            sa.Column("content_length", sa.Integer(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("crawled_at", sa.DateTime(), nullable=True),
        )
    _index("ix_pages_website_id", "pages", ["website_id"])

    if "page_contents" not in existing:
        op.create_table(
            "page_contents",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("page_id", sa.Integer(), sa.ForeignKey("pages.id"), nullable=False, unique=True),
            sa.Column("website_id", sa.Integer(), sa.ForeignKey("websites.id"), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=True),
            sa.Column("extraction_method", sa.String(32), nullable=False),
            sa.Column("chars_kept", sa.Integer(), nullable=False),
            sa.Column("chars_dropped", sa.Integer(), nullable=False),
            sa.Column("truncated", sa.Boolean(), nullable=False),
            sa.Column("structured_json", sa.Text(), nullable=True),
            sa.Column("raw_path", sa.String(512), nullable=True),
        )
    _index("ix_page_contents_website_id", "page_contents", ["website_id"])

    if "fetch_attempts" not in existing:
        op.create_table(
            "fetch_attempts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("website_id", sa.Integer(), sa.ForeignKey("websites.id"), nullable=False),
            sa.Column("url", sa.String(2048), nullable=False),
            sa.Column("attempt_no", sa.Integer(), nullable=False),
            sa.Column("method", sa.String(16), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("http_status", sa.Integer(), nullable=True),
            sa.Column("error_kind", sa.String(32), nullable=True),
            sa.Column("ms", sa.Integer(), nullable=True),
            sa.Column("bytes", sa.Integer(), nullable=True),
            sa.Column("retry_after", sa.Float(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
        )
    _index("ix_fetch_attempts_website_id", "fetch_attempts", ["website_id"])

    if "crawl_errors" not in existing:
        op.create_table(
            "crawl_errors",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("website_id", sa.Integer(), sa.ForeignKey("websites.id"), nullable=False),
            sa.Column("job_id", sa.Integer(), nullable=True),
            sa.Column("url", sa.String(2048), nullable=True),
            sa.Column("category", sa.String(32), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("retry_count", sa.Integer(), nullable=False),
            sa.Column("last_attempt_at", sa.DateTime(), nullable=False),
        )
    _index("ix_crawl_errors_website_id", "crawl_errors", ["website_id"])

    if "import_issues" not in existing:
        op.create_table(
            "import_issues",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id"), nullable=False),
            sa.Column("line_no", sa.Integer(), nullable=False),
            sa.Column("raw", sa.Text(), nullable=False),
            sa.Column("decision", sa.String(16), nullable=False),
            sa.Column("reason", sa.String(255), nullable=False),
        )
    _index("ix_import_issues_job_id", "import_issues", ["job_id"])


def downgrade() -> None:
    for table in ("import_issues", "crawl_errors", "fetch_attempts", "page_contents", "pages", "crawl_tasks"):
        op.drop_table(table)
    # added columns are left in place (SQLite cannot drop them without a table rebuild)
