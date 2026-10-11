"""Crawl one website: homepage first, then the business pages that exist (CR-C01-C10, D01-D10, E01-E10, B01-B10).

Result contract for the rest of the team (unchanged names, new fields have defaults):
    status      one of crawler.config status values (crawled, redirected, parked, under_construction, requires_review,
                blocked, robots_blocked, unreachable, invalid, failed)
    clean_text  consolidated pages (or None when nothing usable was found)
    error       short failure reason for Websites.crawl_error
    page_records / attempts   what the database keeps per page and per network attempt

Order of decisions for one site (the first that applies wins):
  address unsafe -> Invalid | name does not resolve -> Unreachable | robots.txt unreadable (5xx/429/network) -> Blocked, retry later |
  robots disallows the homepage -> Blocked | 401/403/429 or anti-bot challenge page -> Blocked (never bypassed) |
  other HTTP/format error -> Failed | connection/TLS/timeout -> Unreachable | login wall / soft 404 / no usable text -> Requires Review |
  parked -> Parked | coming soon or default server page -> Under Construction | other registrable domain -> Redirected | else Crawled
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

import app.settings as settings
from app.crawler import config, politeness
from app.crawler.browser import render_page
from app.crawler.discover import ORDER, PageLink, canonical_key, classify, discover_pages, merge_candidates
from app.crawler.extract import Extracted, extract_detailed
from app.crawler.fetcher import ATTEMPT_TRACE, FetchError, FetchResult, RobotsRules, fetch_page, load_robots
from app.crawler.guard import DnsFailure, GuardError, UnsafeTarget
from app.crawler.quality import assess_page, looks_like_shell, page_is_useful
from app.crawler.sitemap import sitemap_urls
from app.crawler.structured import structured_data, structured_lines
from app.domains import domain_key, same_site

_STATUS_BY_ERROR = {
    "network": config.STATUS_UNREACHABLE,
    "blocked": config.STATUS_BLOCKED,
    "http": config.STATUS_FAILED,
    "redirect": config.STATUS_FAILED,
    "too_large": config.STATUS_FAILED,
    "not_html": config.STATUS_FAILED,
    "invalid": config.STATUS_INVALID,
}
_OUTCOME_BY_STATUS = {
    config.STATUS_BLOCKED: "Blocked", config.STATUS_ROBOTS_BLOCKED: "Blocked", config.STATUS_UNREACHABLE: "Failed",
    config.STATUS_INVALID: "Failed", config.STATUS_FAILED: "Failed", config.STATUS_PARKED: "Failed",
    config.STATUS_UNDER_CONSTRUCTION: "Failed", config.STATUS_REQUIRES_REVIEW: "Failed",
}
CORE_TYPES = ("about", "products", "services", "industries")
MIN_EVIDENCE_CHARS = 2500       # core pages read AND at least this much text = enough evidence (CR-C07)
MAX_RENDERS_PER_SITE = 3        # the browser is a fallback, not a habit (CR-D05)
MAX_META_REFRESH = 2

_WS = re.compile(r"\s+")


@dataclass
class CrawlResult:
    status: str
    clean_text: str | None
    error: str | None
    pages_crawled: int
    final_url: str | None = None
    latency_ms: int | None = None
    http_status: int | None = None
    pages_attempted: int = 0
    crawl_outcome: str = ""            # Completed | Partial | Failed | Blocked (CR-B07)
    error_category: str = ""
    truncation_note: str | None = None
    retry_after: float | None = None   # seconds: try this site again later (robots 5xx, long Retry-After)
    redirected: bool = False
    website_status: str = ""           # requirement word (CR-B06)
    page_records: list[dict] = field(default_factory=list)
    attempts: list[dict] = field(default_factory=list)
    job_id: int | None = None          # set by the runner before saving
    attempt_no: int = 0                # which attempt of the queue task this result belongs to


def _page_label(url: str) -> str:
    path = (urlparse(url).path or "/").rstrip("/")
    if not path:
        return "homepage"
    segment = path.rsplit("/", 1)[-1]
    return re.sub(r"[-_]+", " ", segment)[:40] or "homepage"


def _homepage_candidates(normalized_url: str) -> list[str]:
    """https first (the stored form); plain http as a fallback for old sites."""
    candidates = [normalized_url]
    if normalized_url.startswith("https://"):
        candidates.append("http://" + normalized_url[len("https://"):])
    return candidates


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def _fail(status: str, error: str, category: str, *, retry_after: float | None = None, final_url: str | None = None,
          http_status: int | None = None, pages_attempted: int = 0, records: list[dict] | None = None) -> CrawlResult:
    return CrawlResult(status, None, error[:500], 0, final_url, None, http_status, pages_attempted, _OUTCOME_BY_STATUS.get(status, "Failed"),
                       category, None, retry_after, False, "", records or [])


def _guard_result(exc: GuardError) -> CrawlResult:
    if isinstance(exc, DnsFailure):
        return _fail(config.STATUS_UNREACHABLE, str(exc), "dns")
    return _fail(config.STATUS_INVALID, str(exc), "unsafe_target")


def _fetch_error_result(exc: FetchError) -> CrawlResult:
    if exc.kind == "robots":
        return _fail(config.STATUS_ROBOTS_BLOCKED, exc.detail, "robots_disallowed")
    status = _STATUS_BY_ERROR.get(exc.kind, config.STATUS_FAILED)
    if exc.kind == "network":
        category = "timeout" if exc.timeout else "network"
    elif exc.kind == "http":
        category = "http_5xx" if (exc.status_code or 0) >= 500 else "http_4xx"
    elif exc.kind == "blocked":
        category = "rate_limited" if exc.status_code == 429 else "access_denied"
    else:
        category = exc.kind
    retry_after = exc.retry_after if exc.kind in ("blocked", "http") and (exc.status_code in (429, 503)) else None
    if exc.kind == "network" and any(w in exc.detail.lower() for w in ("ssl", "certificate", "tls")):
        category = "tls"
    return _fail(status, exc.detail, category, retry_after=retry_after, http_status=exc.status_code)


async def _fetch_homepage(client: httpx.AsyncClient, robots: RobotsRules, normalized_url: str) -> FetchResult:
    last: FetchError | None = None
    for candidate in _homepage_candidates(normalized_url):
        if not robots.allowed(candidate):
            raise FetchError("robots", "disallowed by robots.txt")
        try:
            return await fetch_page(client, candidate)
        except FetchError as exc:
            if exc.kind == "network":
                last = exc
                continue
            raise
    raise last if last else FetchError("network", normalized_url)


def _meta_refresh_target(markup: str, base_url: str) -> str | None:
    """The target of <meta http-equiv=refresh content='0;url=...'> when it fires within 10 seconds."""
    try:
        soup = BeautifulSoup(markup, "lxml")
    except Exception:  # noqa: BLE001
        return None
    tag = soup.find("meta", attrs={"http-equiv": re.compile("^refresh$", re.I)})
    content = str(tag.get("content", "")) if tag is not None else ""
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*[;,]\s*(?:url\s*=\s*)?['\"]?([^'\"]+)", content, re.I)
    if not m or float(m.group(1)) > 10:
        return None
    target = urljoin(base_url, m.group(2).strip())
    return target if urlparse(target).scheme in ("http", "https") else None


def _with_structure(html: bytes, text: str, url: str = "") -> tuple[str, list[dict]]:
    items = structured_data(html, url)
    extra = [line for line in structured_lines(html, url) if line.lower() not in text.lower()]
    if not extra:
        return text, items
    block = "\n".join(extra)
    return (f"{text}\n{block}" if text else block), items


async def _maybe_render(fetched: FetchResult, title: str, text: str) -> tuple[bytes, str, str, str]:
    """Use the browser only when HTTP returned a shell with too little text."""
    html = fetched.content
    if page_is_useful(text) or not looks_like_shell(text, html):
        return html, title, text, "http"
    rendered = await render_page(fetched.final_url)
    if not rendered:
        return html, title, text, "http"
    rendered_title, rendered_text = _title_text(rendered, fetched.final_url)
    if len(rendered_text) <= len(text):
        return html, title, text, "http"
    return rendered, rendered_title, rendered_text, "browser"


def _title_text(html: bytes, url: str, content_type: str | None = None) -> tuple[str, str]:
    extracted = extract_detailed(html, url, content_type)
    return extracted.title, extracted.text


def _raw(html) -> bytes | None:
    """Raw HTML is kept only when RAW_HTML_RETENTION_DAYS > 0 (CR-E07)."""
    return bytes(html) if settings.raw_html_retention_days() > 0 else None


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _Collector:
    """Collects page sections without repeating lines across pages (CR-E03, E05) and keeps one record per page (CR-D10, E08, E09)."""

    def __init__(self) -> None:
        self.sections: list[tuple[str, str, str]] = []   # (label, url, text)
        self.seen_lines: set[str] = set()
        self.records: list[dict] = []
        self.total = 0

    def record(self, **fields) -> dict:
        rec = {"url": "", "canonical_url": None, "page_type": "other", "discovery_source": "", "rank_score": 0, "title": "", "http_status": None,
               "crawl_status": "", "method": "http", "content_length": 0, "error": None, "text": "", "content_hash": None, "chars_kept": 0,
               "chars_dropped": 0, "extraction_method": "", "structured": None, "crawled_at": _now()}
        rec.update(fields)
        self.records.append(rec)
        return rec

    def absorb(self, label: str, url: str, title: str, text: str, method: str) -> int:
        kept = []
        for line in text.splitlines():
            key = line.lower()
            if key in self.seen_lines:
                continue
            self.seen_lines.add(key)
            kept.append(line)
        body = "\n".join(kept)
        if not body:
            return 0
        note = f"Retrieved via {method}: {url}"
        self.sections.append((label, url, f"{title}\n{note}\n{body}" if title else f"{note}\n{body}"))
        self.total += len(body)
        return len(body)


def _assemble(collector: _Collector) -> tuple[str, str | None]:
    """Join the sections; cut at MAX_TEXT_CHARS on a line boundary and say what was cut (CR-E10)."""
    parts = [f"=== PAGE: {label} | {url}\n{text}" for label, url, text in collector.sections]
    profile = "\n\n".join(parts)
    if len(profile) <= config.MAX_TEXT_CHARS:
        return profile, None
    cut = profile[: config.MAX_TEXT_CHARS].rsplit("\n", 1)[0]
    removed = len(profile) - len(cut)
    kept_sections = cut.count("=== PAGE: ")
    lost = [f"{label} ({url})" for label, url, _t in collector.sections[kept_sections:]]
    note = f"text cut at {config.MAX_TEXT_CHARS} characters: {removed} characters removed"
    if lost:
        note += "; pages dropped completely: " + ", ".join(lost[:10])
    if kept_sections and kept_sections <= len(collector.sections):
        note += f"; last kept page partly cut: {collector.sections[kept_sections - 1][0]}"
    return cut + "\n...[truncated]", note


async def crawl_one(
    client: httpx.AsyncClient,
    normalized_url: str,
    robots_cache: dict[str, RobotsRules],
) -> CrawlResult:
    """Fetch and clean a single website. Never raises for normal failures; every attempt is traced for the database."""
    trace: list[dict] = []
    token = ATTEMPT_TRACE.set(trace)
    try:
        result = await _crawl(client, normalized_url, robots_cache)
    except settings.SettingsError as exc:  # contact policy / missing configuration: a clear failure, not a crash
        result = _fail(config.STATUS_FAILED, f"configuration: {exc}", "configuration")
    finally:
        ATTEMPT_TRACE.reset(token)
    result.attempts = trace
    result.website_status = config.WEBSITE_STATUS_WORD.get(result.status, "")
    if not result.crawl_outcome:
        result.crawl_outcome = _OUTCOME_BY_STATUS.get(result.status, "Completed")
    return result


async def _crawl(client: httpx.AsyncClient, normalized_url: str, robots_cache: dict[str, RobotsRules]) -> CrawlResult:
    started = time.monotonic()
    try:
        robots = await load_robots(client, normalized_url, robots_cache)
        if robots.unavailable and robots.error_kind == "network" and normalized_url.startswith("https://"):
            # https may simply not be served: try the plain-http robots.txt before giving up (same rule as for the homepage)
            alt = await load_robots(client, "http://" + normalized_url[len("https://"):], robots_cache)
            if not alt.unavailable:
                robots = alt
        if robots.unavailable and robots.error_kind == "network":
            # The site cannot be reached at all: that is Unreachable (not Blocked). Nothing is crawled; the task is retried later.
            timed_out = "timeout" in (robots.detail or "").lower()
            return _fail(config.STATUS_UNREACHABLE, robots.detail or "cannot reach the site", "timeout" if timed_out else "network", retry_after=900.0)
        if robots.unavailable:  # the server answered robots.txt with 5xx / 429: not crawled now (ROBOTS_5XX_POLICY=disallow), retried later
            return _fail(config.STATUS_ROBOTS_BLOCKED, robots.detail or "robots.txt unavailable", "robots_unavailable",
                         retry_after=robots.retry_after or 900.0)
        homepage = await _fetch_homepage(client, robots, normalized_url)
    except GuardError as exc:
        return _guard_result(exc)
    except FetchError as exc:
        return _fetch_error_result(exc)

    collector = _Collector()
    home_url = homepage.final_url
    attempted = 1
    http_status = homepage.status_code
    html = homepage.content
    ctype = homepage.content_type

    # --- meta refresh redirect (ISS-25): a near-empty page that forwards the visitor ---
    extracted = extract_detailed(html, home_url, ctype)
    hops = 0
    while hops < MAX_META_REFRESH and len(extracted.text) < 200:
        target = _meta_refresh_target(html.decode("utf-8", errors="ignore") if isinstance(html, bytes) else str(html), home_url)
        if not target or canonical_key(target) == canonical_key(home_url):
            break
        try:
            target_robots = robots if urlparse(target).netloc == urlparse(home_url).netloc else await load_robots(client, target, robots_cache)
            if not target_robots.allowed(target):
                break
            followed = await fetch_page(client, target)
        except GuardError as exc:
            return _guard_result(exc)
        except FetchError as exc:
            return _fetch_error_result(exc)
        attempted += 1
        hops += 1
        home_url, http_status, html, ctype = followed.final_url, followed.status_code, followed.content, followed.content_type
        extracted = extract_detailed(html, home_url, ctype)

    host = urlparse(home_url).hostname or ""
    method = "http"
    renders = 0
    assessment = assess_page(extracted.text, extracted.title, html, host)
    if assessment.kind in ("js_shell", "thin") and renders < MAX_RENDERS_PER_SITE:
        renders += 1
        rendered = await render_page(home_url)
        if rendered:
            r_ext = extract_detailed(rendered, home_url)
            if len(r_ext.text) > len(extracted.text):
                extracted, html, method = r_ext, bytes(rendered), "browser"
                new_url = getattr(rendered, "final_url", "") or home_url
                if new_url and canonical_key(new_url) != canonical_key(home_url):
                    home_url = new_url
                    host = urlparse(home_url).hostname or host
                assessment = assess_page(extracted.text, extracted.title, html, host)
    redirected = not same_site(normalized_url, home_url)

    # --- what is this page? ---
    reason = "; ".join(assessment.reasons[:2])
    if assessment.kind == "challenge":
        return _fail(config.STATUS_BLOCKED, f"anti-bot challenge page detected ({reason}); not bypassed", "challenge", final_url=home_url, http_status=http_status, pages_attempted=attempted)
    if assessment.kind == "parked":
        return _fail(config.STATUS_PARKED, f"parked or for-sale domain ({reason})", "parked", final_url=home_url, http_status=http_status, pages_attempted=attempted)
    if assessment.kind == "under_construction":
        return _fail(config.STATUS_UNDER_CONSTRUCTION, f"under construction or default server page ({reason})", "under_construction", final_url=home_url, http_status=http_status, pages_attempted=attempted)
    if assessment.kind == "login":
        return _fail(config.STATUS_REQUIRES_REVIEW, f"login or password wall ({reason})", "login_wall", final_url=home_url, http_status=http_status, pages_attempted=attempted)
    if assessment.kind == "soft_404":
        return _fail(config.STATUS_REQUIRES_REVIEW, f"error page served with HTTP 200 ({reason})", "soft_404", final_url=home_url, http_status=http_status, pages_attempted=attempted)
    if assessment.kind in ("thin", "js_shell"):
        why = "page needs JavaScript and the browser added nothing" if assessment.kind == "js_shell" else "no usable text found"
        return _fail(config.STATUS_REQUIRES_REVIEW, why, "no_content", final_url=home_url, http_status=http_status, pages_attempted=attempted)

    # --- homepage accepted ---
    home_text, items = _with_structure(html, extracted.text, home_url)
    collector.absorb("homepage", home_url, extracted.title, home_text, method)
    collector.record(url=home_url, canonical_url=extracted.canonical or None, page_type="home", discovery_source="homepage", title=extracted.title,
                     http_status=http_status, crawl_status="fetched", method=method, content_length=len(home_text), text=home_text,
                     content_hash=_hash(home_text), chars_kept=len(home_text), chars_dropped=extracted.dropped_chars, raw=_raw(html),
                     extraction_method=extracted.method + ("+structured" if items else ""), structured=json.dumps(items, ensure_ascii=False) if items else None)

    seen_keys = {canonical_key(home_url), canonical_key(normalized_url)}
    gate = politeness.get_gate()
    key = domain_key(home_url)
    delay_note = ""
    homepage_only = False
    crawl_delay = robots.crawl_delay()
    if crawl_delay:
        gate.set_crawl_delay(key, crawl_delay)
        if crawl_delay > config.CRAWL_DELAY_MAX:
            homepage_only, delay_note = True, f"robots.txt Crawl-delay {crawl_delay:g}s is above the {config.CRAWL_DELAY_MAX:g}s limit: only the homepage was read"

    failures = 0
    stop_note = delay_note
    if len(collector.sections) < config.MAX_PAGES and not homepage_only:
        parsed = urlparse(home_url)
        origin = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
        extra = await sitemap_urls(client, robots, origin, parsed.hostname or "")
        candidates = merge_candidates(discover_pages(html, home_url), extra)
        failures, attempted_pages, stop_note2 = await _read_pages(client, robots, robots_cache, collector, candidates, seen_keys, started, renders)
        attempted += attempted_pages
        stop_note = "; ".join(x for x in (stop_note, stop_note2) if x)

    total = collector.total
    if not collector.sections or total < config.MIN_TEXT_CHARS:
        return _fail(config.STATUS_REQUIRES_REVIEW, "no usable text found", "no_content", final_url=home_url, http_status=http_status,
                     pages_attempted=attempted, records=collector.records)

    profile, truncation = _assemble(collector)
    status = config.STATUS_REDIRECTED if redirected else config.STATUS_CRAWLED
    outcome = "Partial" if (failures or stop_note) else "Completed"
    error = None
    if redirected:
        error = f"redirected to {home_url} (different domain)"
    if outcome == "Partial" and stop_note:
        error = (error + "; " if error else "") + stop_note
    return CrawlResult(status, profile, error, len(collector.sections), home_url, homepage.elapsed_ms, http_status, attempted, outcome, "", truncation,
                       None, redirected, config.WEBSITE_STATUS_WORD[status], collector.records)


async def _read_pages(client, robots, robots_cache, collector: _Collector, candidates: list[PageLink], seen_keys: set[str], started: float,
                      renders: int) -> tuple[int, int, str]:
    """Fetch the best business pages until the evidence is enough or the budget is used. Returns (failures, attempts, note)."""
    typed = [c for c in candidates if c.page_type != "other"]
    other = [c for c in candidates if c.page_type == "other"]
    by_type: dict[str, list[PageLink]] = {}
    for link in typed:
        by_type.setdefault(link.page_type, []).append(link)
    covered: Counter = Counter()
    available_core = {t for t in CORE_TYPES if by_type.get(t)}
    failures = attempts = strikes = 0
    note = ""
    plan: list[PageLink] = []
    for nth in range(config.PER_TYPE_PAGES):  # one page of every type first, then second pages
        for kind in ORDER:
            if len(by_type.get(kind, [])) > nth:
                plan.append(by_type[kind][nth])

    def enough() -> bool:
        return all(covered[t] >= 1 for t in available_core) and collector.total >= MIN_EVIDENCE_CHARS

    async def fetch_one(link: PageLink) -> bool:
        nonlocal failures, attempts, strikes, renders
        rec_base = dict(url=link.url, page_type=link.page_type, discovery_source=link.source, rank_score=link.score)
        key = canonical_key(link.url)
        if key in seen_keys:
            return False
        seen_keys.add(key)
        try:
            page_robots = robots if urlparse(link.url).netloc == urlparse(robots.origin).netloc else await load_robots(client, link.url, robots_cache)
        except (GuardError, FetchError):
            collector.record(**rec_base, crawl_status="skipped", error="robots.txt of this host could not be read")
            return False
        if not page_robots.allowed(link.url):
            collector.record(**rec_base, crawl_status="skipped", error="disallowed by robots.txt")
            return False
        attempts += 1
        try:
            result = await fetch_page(client, link.url)
        except GuardError as exc:
            collector.record(**rec_base, crawl_status="failed", error=str(exc)[:300])
            return False
        except FetchError as exc:
            failures += 1
            collector.record(**rec_base, crawl_status="failed", http_status=exc.status_code, error=exc.detail[:300])
            if exc.kind == "blocked":
                strikes += 1
            return False
        if not same_site(link.url, result.final_url):
            collector.record(**rec_base, crawl_status="skipped", http_status=result.status_code, error=f"redirected away to {result.final_url}")
            return False
        final_key = canonical_key(result.final_url)
        if final_key != key and final_key in seen_keys:
            collector.record(**rec_base, crawl_status="duplicate", http_status=result.status_code, error=f"same page as {result.final_url}")
            return False
        seen_keys.add(final_key)
        ext = extract_detailed(result.content, result.final_url, result.content_type)
        if ext.canonical:
            canon_key = canonical_key(urljoin(result.final_url, ext.canonical))
            if canon_key != final_key and canon_key in seen_keys:
                collector.record(**rec_base, canonical_url=ext.canonical, crawl_status="duplicate", http_status=result.status_code, title=ext.title,
                                 error="canonical URL points to a page already read")
                return False
            seen_keys.add(canon_key)
        page_html, text, title, method = result.content, ext.text, ext.title, "http"
        if renders < MAX_RENDERS_PER_SITE and not page_is_useful(text) and looks_like_shell(text, page_html):
            renders += 1
            page_html, title, text, method = await _maybe_render(result, title, text)
            if method == "browser":
                ext = extract_detailed(page_html, result.final_url)
        verdict = assess_page(text, title, page_html, urlparse(result.final_url).hostname or "")
        if verdict.kind in ("challenge",):
            strikes += 1
            failures += 1
            collector.record(**rec_base, crawl_status="failed", http_status=result.status_code, title=title, error="anti-bot challenge page")
            return False
        if verdict.kind in ("login", "soft_404", "thin", "js_shell", "parked", "under_construction"):
            collector.record(**rec_base, crawl_status="thin" if verdict.kind in ("thin", "js_shell") else verdict.kind, http_status=result.status_code,
                             title=title, error=f"{verdict.kind}: {'; '.join(verdict.reasons[:2])}")
            return False
        text, items = _with_structure(page_html, text, result.final_url)
        # the title/heading confirms (or corrects) the page type that the link suggested
        confirmed = link.page_type
        if confirmed == "other":
            guessed, score = classify("", f"{title} {' '.join(ext.headings[:2])}")
            confirmed = guessed if guessed in ORDER else "other"
        added = collector.absorb(_page_label(result.final_url), result.final_url, title, text, method)
        collector.record(**{**rec_base, "page_type": confirmed}, canonical_url=ext.canonical or None, title=title, http_status=result.status_code,
                         crawl_status="fetched" if added else "duplicate", method=method, content_length=len(text), text=text, content_hash=_hash(text),
                         chars_kept=len(text), chars_dropped=ext.dropped_chars, raw=_raw(page_html), extraction_method=ext.method + ("+structured" if items else ""),
                         structured=json.dumps(items, ensure_ascii=False) if items else None)
        if added:
            covered[confirmed] += 1
        return bool(added)

    async def stop_reason() -> str | None:
        if time.monotonic() - started > config.SITE_DEADLINE:
            return f"site time limit of {config.SITE_DEADLINE:g}s reached"
        if strikes >= config.BLOCK_STRIKES:
            return f"stopped after {strikes} blocking answers"
        if collector.total >= config.MAX_TEXT_CHARS:
            return None
        return None

    for link in plan:
        if len(collector.sections) >= config.MAX_PAGES or enough() or collector.total >= config.MAX_TEXT_CHARS:
            break
        reason = await stop_reason()
        if reason:
            note = reason
            break
        await fetch_one(link)

    if not note and not enough() and len(collector.sections) < config.MAX_PAGES and collector.total < MIN_EVIDENCE_CHARS:
        for link in other[:2]:  # other pages only when the evidence is not sufficient (CR-C04)
            if len(collector.sections) >= config.MAX_PAGES:
                break
            reason = await stop_reason()
            if reason:
                note = reason
                break
            await fetch_one(link)
    return failures, attempts, note
