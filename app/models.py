"""One row per company.

The address and status are filled when a URL is saved.
clean_text is filled by the crawler.
The company fields are filled by the AI classification.
Until then those columns stay empty.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Job(Base):
    """One durable record per import. Survives a restart; websites point at it."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), default="import")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    added: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    invalid: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # batch progress (CR-A12, G02)
    total: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    done_count: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    failed_count: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_kind", "kind"),
    )


class Website(Base):
    __tablename__ = "websites"

    id: Mapped[int] = mapped_column(primary_key=True)
    original_url: Mapped[str] = mapped_column(String(2048))
    normalized_website: Mapped[str] = mapped_column(String(2048), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True, index=True)
    source_batch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    clean_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    crawl_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    pages_crawled: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    niche: Mapped[str | None] = mapped_column(String(128), nullable=True)
    products: Mapped[str | None] = mapped_column(Text, nullable=True)
    services: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification_meta: Mapped[str | None] = mapped_column(Text, nullable=True)
    crawl_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    classification_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    secondary_industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sub_niche: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    geographic_markets: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # --- crawl facts added in Phase 2 (CR-D10, H02-H04, A07, B06-B08, F09) ---
    source_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    domain_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    final_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    website_status: Mapped[str | None] = mapped_column(String(32), nullable=True)   # requirement word (CR-B06)
    crawl_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)    # Completed / Partial / Failed / Blocked ... (CR-B07)
    crawl_error_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pages_attempted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    content_crawled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    content_is_stale: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)
    truncation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_of_id: Mapped[int | None] = mapped_column(Integer, nullable=True)   # this site redirects to another site that is already in the list (CR-B05)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    __table_args__ = (
        Index("ix_websites_status", "status"),
        Index("ix_websites_industry", "industry"),
        Index("ix_websites_business_type", "business_type"),
        Index("ix_websites_confidence", "confidence"),
        Index("ix_websites_crawl_status", "crawl_status"),
        Index("ix_websites_classification_status", "classification_status"),
    )


class EvidenceRecord(Base):
    """One grounded quote. The website row still keeps the same quotes as JSON."""

    __tablename__ = "evidence_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    website_id: Mapped[int] = mapped_column(ForeignKey("websites.id"), index=True)
    field: Mapped[str] = mapped_column(String(64), default="")
    quote: Mapped[str] = mapped_column(Text)
    page: Mapped[str] = mapped_column(String(80), default="")
    source_url: Mapped[str] = mapped_column(String(2048), default="")
    method: Mapped[str] = mapped_column(String(32), default="")
    quality: Mapped[str] = mapped_column(String(32), default="explicit")
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )


class DomainStat(Base):
    """Latest timing and success count for one hostname."""

    __tablename__ = "domain_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True)
    last_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_status: Mapped[str] = mapped_column(String(32), default="")
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    # health that the scheduler READS (CR-F06, F07, ISS-22)
    avg_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    consecutive_failures: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    backoff_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    crawl_delay: Mapped[float | None] = mapped_column(Float, nullable=True)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


TASK_ACTIVE_STATES = ("queued", "claimed", "crawling", "extracting", "retry_scheduled")
TASK_RUNNING_STATES = ("claimed", "crawling", "extracting")


class CrawlTask(Base):
    """The durable queue (CR-A12, A13, G01, G02). One active task per website, one running task per domain."""

    __tablename__ = "crawl_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    website_id: Mapped[int] = mapped_column(ForeignKey("websites.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True, index=True)
    domain_key: Mapped[str] = mapped_column(String(255), default="")
    # queued -> claimed -> crawling -> extracting -> done | retry_scheduled | failed | cancelled | insufficient_evidence
    state: Mapped[str] = mapped_column(String(24), default="queued")
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    not_before: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_crawl_tasks_state", "state", "not_before"),
        Index("ix_crawl_tasks_domain", "domain_key"),
        Index(
            "uq_crawl_tasks_active_website", "website_id", unique=True,
            postgresql_where=text("state IN ('queued','claimed','crawling','extracting','retry_scheduled')"),
            sqlite_where=text("state IN ('queued','claimed','crawling','extracting','retry_scheduled')"),
        ),
        Index(
            "uq_crawl_tasks_running_domain", "domain_key", unique=True,
            postgresql_where=text("state IN ('claimed','crawling','extracting')"),
            sqlite_where=text("state IN ('claimed','crawling','extracting')"),
        ),
    )


class Page(Base):
    """One discovered/fetched page of a website (CR-D10, H02, H05 'Crawled Pages' sheet)."""

    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    website_id: Mapped[int] = mapped_column(ForeignKey("websites.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    url: Mapped[str] = mapped_column(String(2048))
    canonical_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    page_type: Mapped[str] = mapped_column(String(32), default="other")
    discovery_source: Mapped[str] = mapped_column(String(32), default="")   # homepage | nav | link | sitemap
    rank_score: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crawl_status: Mapped[str] = mapped_column(String(24), default="")       # fetched | failed | skipped | duplicate | thin
    method: Mapped[str] = mapped_column(String(16), default="http")         # http | browser
    content_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    crawled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PageContent(Base):
    """Cleaned text of a page, kept apart from crawl metadata (CR-E07, E08, E09)."""

    __tablename__ = "page_contents"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"), unique=True)
    website_id: Mapped[int] = mapped_column(ForeignKey("websites.id"), index=True)
    text: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(32), default="")  # html-text | html-text+structured | browser-text
    chars_kept: Mapped[int] = mapped_column(Integer, default=0)
    chars_dropped: Mapped[int] = mapped_column(Integer, default=0)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    structured_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_path: Mapped[str | None] = mapped_column(String(512), nullable=True)


class FetchAttempt(Base):
    """Every network attempt, including retries (CR-F04, F09, G05)."""

    __tablename__ = "fetch_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    website_id: Mapped[int] = mapped_column(ForeignKey("websites.id"), index=True)
    url: Mapped[str] = mapped_column(String(2048))
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    method: Mapped[str] = mapped_column(String(16), default="http")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)           # robots / guard decision, redirect target


class CrawlError(Base):
    """Error and retry history (CR-F09, H05 'Errors / Failed URLs' sheet)."""

    __tablename__ = "crawl_errors"

    id: Mapped[int] = mapped_column(primary_key=True)
    website_id: Mapped[int] = mapped_column(ForeignKey("websites.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    category: Mapped[str] = mapped_column(String(32), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ImportIssue(Base):
    """Lines the importer refused or recognised as duplicates, reviewable after the import (CR-A10)."""

    __tablename__ = "import_issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    line_no: Mapped[int] = mapped_column(Integer, default=0)
    raw: Mapped[str] = mapped_column(Text, default="")
    decision: Mapped[str] = mapped_column(String(16), default="invalid")   # invalid | duplicate
    reason: Mapped[str] = mapped_column(String(255), default="")
