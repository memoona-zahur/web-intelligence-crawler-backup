"""Crawl bookkeeping that sits beside the company row.

A content hash decides whether a new fetch should clear the classification.
Quotes are stored as evidence rows. Domain timing is stored per hostname.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

from sqlalchemy import delete, select
from sqlalchemy.orm import object_session

from app.crawler.pipeline import CrawlResult
from app.database import get_session
from app.domains import domain_key, health_key
from app.models import DomainStat, EvidenceRecord, Website
from app.recovery import utcnow

# Outcomes that say the SERVER is unhealthy (cannot be reached, refuses, rate-limits). Content verdicts are not health problems.
HEALTH_FAILURE_STATUSES = {"unreachable", "blocked", "robots_blocked", "failed"}
CONTENT_CATEGORIES = {"http_4xx", "not_html", "too_large", "redirect", "robots_disallowed", "parked", "under_construction", "login_wall", "soft_404", "no_content", "invalid_host"}
_PAGE = re.compile(r"^=== PAGE: (.*?) \| (\S+)\s*$", re.MULTILINE)
_METHOD = re.compile(r"Retrieved via (http|browser):")


def content_hash(text: str | None) -> str | None:
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def page_sources(clean_text: str | None) -> dict[str, tuple[str, str]]:
    """Map a page label to (url, retrieval method)."""
    if not clean_text:
        return {}
    matches = list(_PAGE.finditer(clean_text))
    found: dict[str, tuple[str, str]] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(clean_text)
        section = clean_text[match.end() : end]
        method_match = _METHOD.search(section)
        method = method_match.group(1) if method_match else ""
        found[match.group(1).strip().casefold()] = (match.group(2), method)
    return found


def clear_classification(site: Website) -> None:
    site.classification_status = None
    site.company_name = None
    site.description = None
    site.business_type = None
    site.industry = None
    site.secondary_industry = None
    site.niche = None
    site.sub_niche = None
    site.products = None
    site.confidence = None
    site.evidence = None
    site.classification_meta = None
    site.business_model = None
    site.geographic_markets = None
    session = object_session(site)
    if session is not None and site.id is not None:
        session.execute(delete(EvidenceRecord).where(EvidenceRecord.website_id == site.id))


def apply_crawl_result(site: Website, result: CrawlResult, now: datetime | None = None, retry_count: int | None = None) -> None:
    """Write crawl fields. Keep a classification when the text did not change.

    A crawl that produced no new text never overwrites older text silently: the old text stays, but the row is marked stale (ISS-27, CR-B08).
    """
    now = now or utcnow()
    new_hash = content_hash(result.clean_text)
    previous = site.content_hash or content_hash(site.clean_text)
    changed = bool(previous and new_hash and previous != new_hash)
    site.crawl_status = result.status
    site.crawl_error = result.error
    site.pages_crawled = result.pages_crawled
    site.last_crawled_at = now
    site.claimed_at = None
    # facts the requirements ask for (CR-D10, H03, H04)
    site.final_url = (result.final_url or None) and result.final_url[:2048]
    site.http_status = result.http_status
    site.pages_attempted = result.pages_attempted
    site.website_status = result.website_status or None
    site.crawl_outcome = result.crawl_outcome or None
    site.crawl_error_category = result.error_category or None
    site.truncation_note = result.truncation_note
    if retry_count is not None:
        site.retry_count = retry_count
    if result.retry_after:
        site.next_retry_at = now + timedelta(seconds=result.retry_after)
    else:
        site.next_retry_at = None
    if not site.domain_key:
        site.domain_key = domain_key(site.normalized_website)
    if result.clean_text:
        site.clean_text = result.clean_text
        site.content_hash = new_hash
        site.content_crawled_at = now
        site.content_is_stale = False
        if changed:
            clear_classification(site)
            site.status = result.status
        elif site.classification_status:
            site.status = site.classification_status
        else:
            site.status = result.status
        return
    if site.clean_text:
        site.content_is_stale = True  # this crawl failed; the text below is from an earlier crawl
    site.status = result.status


def record_domain(website: str, result: CrawlResult, now: datetime | None = None) -> None:
    """Write domain health that the queue READS before claiming more work for the same host (CR-F06, F07, ISS-22)."""
    host = health_key(website)
    if not host:
        return
    now = now or utcnow()
    ok = result.status in ("crawled", "redirected")
    # Domain HEALTH is about the server, not about what the site says: a parked page, a login wall or a 404 homepage prove the host answers.
    unhealthy = result.status in HEALTH_FAILURE_STATUSES and result.error_category not in CONTENT_CATEGORIES
    with get_session() as session:
        stat = session.scalar(select(DomainStat).where(DomainStat.domain == host))
        if stat is None:
            stat = DomainStat(domain=host, success_count=0, failure_count=0, consecutive_failures=0)
            session.add(stat)
        stat.last_status = result.status
        stat.last_attempt_at = now
        if result.latency_ms is not None:
            stat.last_latency_ms = result.latency_ms
            stat.avg_latency_ms = result.latency_ms if not stat.avg_latency_ms else int(0.7 * stat.avg_latency_ms + 0.3 * result.latency_ms)
        if ok:
            stat.success_count = (stat.success_count or 0) + 1
            stat.last_success_at = now
            stat.consecutive_failures = 0
            stat.backoff_until = None
        else:
            stat.failure_count = (stat.failure_count or 0) + 1
            stat.consecutive_failures = (stat.consecutive_failures or 0) + 1 if unhealthy else 0
            if not unhealthy:
                stat.backoff_until = None
            blocking = result.status in ("blocked", "robots_blocked") or result.error_category in ("rate_limited", "robots_unavailable", "challenge")
            if blocking:
                stat.blocked_at = now
                stat.blocked_reason = (result.error or result.status)[:255]
            if unhealthy and (stat.consecutive_failures >= 3 or (blocking and result.retry_after)):
                wait = max(result.retry_after or 0, 900 * 2 ** min(stat.consecutive_failures - 1, 6))
                stat.backoff_until = now + timedelta(seconds=min(wait, 24 * 3600))
        session.commit()

def replace_evidence(site: Website, items: list[dict], confidence: int | None, when: datetime | None = None) -> list[dict]:
    """Replace quote rows for this website and return items enriched with source and method."""
    when = when or utcnow()
    sources = page_sources(site.clean_text)
    enriched: list[dict] = []
    session = object_session(site)
    if session is not None and site.id is not None:
        session.execute(delete(EvidenceRecord).where(EvidenceRecord.website_id == site.id))
    for item in items:
        if not isinstance(item, dict) or not item.get("quote"):
            continue
        page = str(item.get("page") or "")
        source_url, method = sources.get(page.strip().casefold(), ("", ""))
        quality = "explicit" if item.get("explicit", True) else "inferred"
        stored = dict(item)
        stored["source_url"] = source_url
        stored["method"] = method
        stored["quality"] = quality
        enriched.append(stored)
        if session is not None and site.id is not None:
            session.add(
                EvidenceRecord(
                    website_id=site.id,
                    field=str(item.get("field") or "")[:64],
                    quote=str(item.get("quote")),
                    page=page[:80],
                    source_url=source_url[:2048],
                    method=method[:32],
                    quality=quality,
                    confidence=confidence,
                    retrieved_at=when,
                )
            )
    return enriched
