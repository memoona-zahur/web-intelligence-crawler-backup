"""Crawl data for export and monitoring: the crawl columns, the Crawled Pages and Errors sheets, and run metrics (CR-G04, G09, H04, H05, E11).

Everything is read in chunks (yield_per), so a 60,000-site export never holds the whole table in memory.
"""

from __future__ import annotations

import csv
import statistics
from datetime import datetime, timedelta
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.crawler import queue
from app.models import CrawlError, FetchAttempt, Page, Website
from app.recovery import utcnow
from app.sanitize import sanitize_cell

CRAWL_COLUMNS = (
    "Record ID", "Source / Batch", "Original URL", "Normalized Website", "Final / Redirect URL", "Website Status", "HTTP Status",
    "Pages Crawled Count", "Pages Attempted Count", "Crawl Status", "Crawl Error / Notes", "Last Crawled At",
)
PAGE_COLUMNS = ("Website ID", "Page URL", "Page Type", "Title", "HTTP Status", "Crawl Status", "Content Length", "Error", "Crawled At")
ERROR_COLUMNS = ("Website ID", "Normalized Website", "URL", "Error Category", "Error Message", "Retry Count", "Last Attempt At")


def _when(value: datetime | None) -> str:
    return value.isoformat(sep=" ", timespec="seconds") if isinstance(value, datetime) else ""


def crawl_rows(session: Session):
    stmt = select(Website).order_by(Website.id)
    for site in session.scalars(stmt).yield_per(500):
        yield [
            site.id, site.source_batch or site.source_file or "", site.original_url or "", site.normalized_website or "", site.final_url or "",
            site.website_status or "", site.http_status if site.http_status is not None else "", site.pages_crawled if site.pages_crawled is not None else "",
            site.pages_attempted if site.pages_attempted is not None else "", site.crawl_outcome or site.crawl_status or "", site.crawl_error or "",
            _when(site.last_crawled_at),
        ]


def page_rows(session: Session):
    for page in session.scalars(select(Page).order_by(Page.website_id, Page.id)).yield_per(500):
        yield [page.website_id, page.url, page.page_type, page.title or "", page.http_status if page.http_status is not None else "", page.crawl_status,
               page.content_length if page.content_length is not None else "", page.error or "", _when(page.crawled_at)]


def error_rows(session: Session):
    stmt = select(CrawlError, Website.normalized_website).join(Website, Website.id == CrawlError.website_id).order_by(CrawlError.id)
    for error, website in session.execute(stmt).yield_per(500):
        yield [error.website_id, website, error.url or "", error.category, error.message, error.retry_count, _when(error.last_attempt_at)]


def write_crawl_export(session: Session, path: Path) -> dict[str, int]:
    """.xlsx: three sheets. .csv: the main file plus <name>_pages.csv and <name>_errors.csv. Every cell is sanitised (CR-E11)."""
    counts = {"websites": 0, "pages": 0, "errors": 0}
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        book = Workbook(write_only=True)
        for title, columns, rows, key in (("Website Intelligence", CRAWL_COLUMNS, crawl_rows(session), "websites"), ("Crawled Pages", PAGE_COLUMNS, page_rows(session), "pages"),
                                          ("Errors - Failed URLs", ERROR_COLUMNS, error_rows(session), "errors")):
            sheet = book.create_sheet(title)
            sheet.append(list(columns))
            for row in rows:
                sheet.append([sanitize_cell(cell) for cell in row])
                counts[key] += 1
        book.save(path)
        return counts
    stem = path.with_suffix("")
    for target, columns, rows, key in ((path, CRAWL_COLUMNS, crawl_rows(session), "websites"),
                                       (Path(f"{stem}_pages.csv"), PAGE_COLUMNS, page_rows(session), "pages"),
                                       (Path(f"{stem}_errors.csv"), ERROR_COLUMNS, error_rows(session), "errors")):
        with target.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            for row in rows:
                writer.writerow([sanitize_cell(cell) for cell in row])
                counts[key] += 1
    return counts


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(len(ordered) * p))], 1)


def crawl_metrics(session: Session, now: datetime | None = None) -> dict:
    """Success rate, latency, errors, throughput (CR-G04). Numbers describe the data in this database only; nothing is extrapolated."""
    now = now or utcnow()
    by_status = {status: n for status, n in session.execute(select(Website.status, func.count()).group_by(Website.status)).all()}
    unfinished = {"pending", "queued", "crawling", "extracting"}
    finished = sum(n for s, n in by_status.items() if s not in unfinished and s is not None)
    ok = sum(by_status.get(s, 0) for s in ("crawled", "redirected"))
    latencies = [float(ms) for (ms,) in session.execute(select(FetchAttempt.ms).where(FetchAttempt.http_status == 200, FetchAttempt.method == "http",
                                                                                      FetchAttempt.ms.is_not(None)).limit(500_000)).all()]
    errors = {cat: n for cat, n in session.execute(select(CrawlError.category, func.count()).group_by(CrawlError.category)).all()}
    hour_ago = now - timedelta(hours=1)
    last_hour = session.scalar(select(func.count()).select_from(Website).where(Website.last_crawled_at >= hour_ago)) or 0
    first, last = session.execute(select(func.min(Website.last_crawled_at), func.max(Website.last_crawled_at))).one()
    browser_sites = session.scalar(select(func.count(func.distinct(Page.website_id))).where(Page.method == "browser")) or 0
    retries = session.scalar(select(func.count()).select_from(FetchAttempt).where(FetchAttempt.attempt_no > 1)) or 0
    return {
        "websites": sum(by_status.values()), "finished": finished, "by_status": by_status,
        "success_rate": round(ok / finished, 4) if finished else None,
        "page_latency_ms_p50": _percentile(latencies, 0.5), "page_latency_ms_p95": _percentile(latencies, 0.95),
        "page_latency_ms_mean": round(statistics.fmean(latencies), 1) if latencies else None,
        "errors_by_category": errors, "retried_attempts": retries, "browser_fallback_sites": browser_sites,
        "sites_finished_last_hour": last_hour,
        "first_crawl_at": _when(first), "last_crawl_at": _when(last),
        "queue": queue.counts_by_state(session),
        "note": "Counts and timings of this database only. They are not a forecast for 60,000 sites.",
    }
