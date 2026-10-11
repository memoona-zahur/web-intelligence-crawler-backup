"""Write what a crawl found into the crawl tables (CR-D07, D10, E07, E08, E09, F09, H02, H05).

The website row keeps the summary (app.profile.apply_crawl_result). This module keeps the details:
pages (one row per discovered/fetched page), page_contents (cleaned text, kept apart from crawl metadata), fetch_attempts (every network
attempt, including retries), crawl_errors (error and retry history). Raw HTML is stored only when RAW_HTML_RETENTION_DAYS > 0.
"""

from __future__ import annotations

import gzip
import hashlib
import os
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import app.settings as settings
from app.crawler import config
from app.crawler.pipeline import CrawlResult
from app.models import CrawlError, FetchAttempt, Page, PageContent, Website


def save_details(session: Session, site: Website, result: CrawlResult, now: datetime, job_id: int | None = None, retry_count: int = 0) -> None:
    """Replace the page rows of this website when the crawl produced pages; always append attempts and errors."""
    if result.page_records:
        old_pages = list(session.scalars(select(Page.id).where(Page.website_id == site.id)))
        if old_pages:
            session.execute(delete(PageContent).where(PageContent.page_id.in_(old_pages)))
            session.execute(delete(Page).where(Page.website_id == site.id))
        for rec in result.page_records:
            page = Page(
                website_id=site.id, job_id=job_id, url=(rec.get("url") or "")[:2048], canonical_url=(rec.get("canonical_url") or None),
                page_type=rec.get("page_type") or "other", discovery_source=rec.get("discovery_source") or "", rank_score=int(rec.get("rank_score") or 0),
                title=(rec.get("title") or None), http_status=rec.get("http_status"), crawl_status=rec.get("crawl_status") or "",
                method=rec.get("method") or "http", content_length=rec.get("content_length"), error=rec.get("error"),
                crawled_at=now,
            )
            session.add(page)
            session.flush()
            if rec.get("text"):
                session.add(PageContent(
                    page_id=page.id, website_id=site.id, text=rec["text"], content_hash=rec.get("content_hash"),
                    extraction_method=rec.get("extraction_method") or "", chars_kept=int(rec.get("chars_kept") or 0),
                    chars_dropped=int(rec.get("chars_dropped") or 0), truncated=bool(result.truncation_note), structured_json=rec.get("structured"),
                    raw_path=_store_raw(site.id, rec),
                ))
    for attempt in result.attempts:
        session.add(FetchAttempt(
            website_id=site.id, url=(attempt.get("url") or "")[:2048], attempt_no=int(attempt.get("attempt_no") or 1), method=attempt.get("method") or "http",
            started_at=now, http_status=attempt.get("http_status"), error_kind=attempt.get("error_kind"), ms=attempt.get("ms"),
            bytes=attempt.get("bytes"), retry_after=attempt.get("retry_after"), note=(attempt.get("note") or None),
        ))
    failed_pages = [r for r in result.page_records if r.get("crawl_status") == "failed"]
    if result.status not in ("crawled", "redirected"):
        session.add(CrawlError(website_id=site.id, job_id=job_id, url=site.normalized_website, category=result.error_category or result.status,
                               message=(result.error or result.status)[:2000], retry_count=retry_count, last_attempt_at=now))
    for rec in failed_pages:
        session.add(CrawlError(website_id=site.id, job_id=job_id, url=(rec.get("url") or "")[:2048], category="page_failed",
                               message=(rec.get("error") or "page failed")[:2000], retry_count=retry_count, last_attempt_at=now))


def _store_raw(website_id: int, rec: dict) -> str | None:
    """Optional gzip copy of the raw HTML outside the database (off by default, CR-E07)."""
    raw = rec.get("raw")
    if not raw or settings.raw_html_retention_days() <= 0:
        return None
    folder = settings.raw_html_dir() / str(website_id)
    folder.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha256((rec.get("url") or "").encode()).hexdigest()[:16] + ".html.gz"
    path = folder / name
    with gzip.open(path, "wb") as handle:
        handle.write(raw)
    return str(path)


def purge_raw_html(now: float | None = None) -> int:
    """Delete raw HTML files older than the retention period. Returns the number of files removed."""
    days = settings.raw_html_retention_days()
    root = settings.raw_html_dir()
    if days <= 0 or not root.exists():
        return 0
    cutoff = (now or time.time()) - days * 86400
    removed = 0
    for path in root.rglob("*.html.gz"):
        try:
            if path.stat().st_mtime < cutoff:
                os.remove(path)
                removed += 1
        except OSError:
            continue
    return removed
