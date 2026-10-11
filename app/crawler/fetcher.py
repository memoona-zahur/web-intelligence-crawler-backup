"""HTTP fetching: guarded redirects, bounded size and time, polite retries, robots.txt (RFC 9309).

What changed against Phase 1 (issue ids in brackets):
- the body is streamed and counted while it is read: decoded-size cap and decompression-ratio cap [ISS-02]
- one total deadline per request, not only per read [ISS-16]
- up to 10 redirects, every hop passes the SSRF guard [ISS-24, ISS-01 for HTTP]
- exponential back-off with jitter, Retry-After honoured, 3 attempts [ISS-15]
- robots.txt parsed by Protego; 5xx / 429 / unreachable means 'do not crawl now' unless ROBOTS_5XX_POLICY=allow [ISS-14, pending sir confirmation]
- every attempt is traced so the database can keep fetch attempts and retry history [ISS-13]
"""

from __future__ import annotations

import asyncio
import contextvars
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from protego import Protego

import app.settings as settings
from app.crawler import config, politeness
from app.crawler.guard import GuardError, assert_public_url

_REDIRECT_CODES = (301, 302, 303, 307, 308)

# Collector for per-attempt records. crawl_one sets a list; fetch_page appends to it. Empty (None) outside a crawl.
ATTEMPT_TRACE: contextvars.ContextVar[list | None] = contextvars.ContextVar("attempt_trace", default=None)


class FetchError(Exception):
    """A page could not be fetched. `.kind` decides the row status."""

    def __init__(self, kind: str, detail: str, status_code: int | None = None, retry_after: float | None = None, timeout: bool = False):
        super().__init__(detail)
        self.kind = kind
        self.detail = detail
        self.status_code = status_code
        self.retry_after = retry_after
        self.timeout = timeout
        self.attempts = 1


@dataclass
class FetchResult:
    requested_url: str
    final_url: str
    status_code: int
    content: bytes
    content_type: str
    elapsed_ms: int = 0
    redirects: list[str] = field(default_factory=list)   # URLs visited before final_url
    attempts: int = 1


def _request_headers() -> dict[str, str]:
    return {
        "User-Agent": config.user_agent(),
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
        "Accept-Language": "en, *;q=0.5",
    }


def parse_retry_after(value: str | None) -> float | None:
    """Seconds from a Retry-After header (number or HTTP date). None when absent or unreadable."""
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return None


def record_attempt(**fields) -> None:
    trace = ATTEMPT_TRACE.get()
    if trace is not None:
        trace.append(fields)


async def _guard(url: str) -> None:
    """SSRF check off the event loop (DNS can block). Looked up by name so tests and the harness can replace it."""
    await asyncio.to_thread(assert_public_url, url)


async def _read_body(response: httpx.Response, cap: int) -> bytes:
    """Read at most `cap` decoded bytes. Raises FetchError('too_large') for oversize bodies and decompression bombs (ISS-02)."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > cap:
            raise FetchError("too_large", f"page larger than {cap} bytes")
        raw = max(response.num_bytes_downloaded, 1)
        if total > 1_000_000 and total > config.MAX_DECODED_RATIO * raw:
            raise FetchError("too_large", f"decompressed size is more than {config.MAX_DECODED_RATIO}x the transferred size (possible decompression bomb)")
        chunks.append(chunk)
    return b"".join(chunks)


async def _one_attempt(client: httpx.AsyncClient, url: str, expect_html: bool) -> FetchResult:
    started = time.perf_counter()
    spent = 0.0  # time inside requests; waiting for the domain gate (politeness) does not count against the deadline
    cap = config.MAX_BYTES_PER_PAGE if expect_html else config.SITEMAP_MAX_BYTES
    current = url
    visited: list[str] = []
    for _ in range(config.MAX_REDIRECTS + 1):
        await _guard(current)
        if config.TOTAL_TIMEOUT - spent <= 0:
            raise FetchError("network", f"timeout fetching {current} (total time limit)", timeout=True)
        gate = politeness.get_gate()
        try:
            async with gate.slot(current) as key:
                slot_started = time.perf_counter()
                try:
                    async with asyncio.timeout(config.TOTAL_TIMEOUT - spent):
                        async with client.stream(
                            "GET", current, headers=_request_headers(), follow_redirects=False, timeout=config.PAGE_TIMEOUT
                        ) as response:
                            status = response.status_code
                            retry_after = parse_retry_after(response.headers.get("retry-after"))
                            if status in (429, 403, 503, 502, 504) or retry_after is not None:
                                gate.slow_down(key)
                            if retry_after:
                                gate.delay_until(key, min(retry_after, config.RETRY_AFTER_MAX))

                            if status in _REDIRECT_CODES:
                                location = response.headers.get("location")
                                if not location:
                                    raise FetchError("redirect", f"redirect without Location from {current}", status)
                                visited.append(current)
                                current = urljoin(current, location)
                                continue

                            if status in (401, 403, 429):
                                raise FetchError("blocked", f"HTTP {status} from {current}", status, retry_after)
                            if not 200 <= status < 300:
                                raise FetchError("http", f"HTTP {status} from {current}", status, retry_after)

                            content_type = response.headers.get("content-type", "").lower()
                            if expect_html and "html" not in content_type and content_type:
                                raise FetchError("not_html", f"content-type {content_type!r} from {current}", status)
                            declared = response.headers.get("content-length")
                            encoded = response.headers.get("content-encoding", "identity").lower() in ("", "identity")
                            if encoded and declared and declared.isdigit() and int(declared) > cap:
                                raise FetchError("too_large", f"page larger than {cap} bytes")
                            body = await _read_body(response, cap)
                            if expect_html and body[:5] == b"%PDF-":
                                raise FetchError("not_html", f"PDF document served from {current}", status)
                            return FetchResult(
                                elapsed_ms=int((time.perf_counter() - started) * 1000),
                                requested_url=url,
                                final_url=str(response.url),
                                status_code=status,
                                content=body,
                                content_type=content_type,
                                redirects=visited,
                            )
                except TimeoutError as exc:
                    raise FetchError("network", f"timeout fetching {current} (total time limit)", timeout=True) from exc
                finally:
                    spent += time.perf_counter() - slot_started
        except FetchError:
            raise
        except GuardError:
            raise
        except httpx.TimeoutException as exc:
            raise FetchError("network", f"timeout fetching {current}", timeout=True) from exc
        except httpx.InvalidURL as exc:
            raise FetchError("invalid", f"invalid URL {current}: {exc}") from exc
        except httpx.HTTPError as exc:
            raise FetchError("network", f"connection error fetching {current}: {exc}") from exc
        except UnicodeError as exc:
            raise FetchError("invalid", f"invalid host name in {current}") from exc

    raise FetchError("redirect", f"more than {config.MAX_REDIRECTS} redirects from {url}")


def _retryable(exc: FetchError, attempt: int) -> bool:
    if exc.kind == "network":
        return not (exc.timeout and attempt >= 1)  # a slow server gets one retry only
    if exc.kind == "http" and exc.status_code is not None and exc.status_code >= 500:
        return True
    if exc.kind == "blocked" and exc.status_code == 429:
        return True
    return False


async def fetch_page(client: httpx.AsyncClient, url: str, expect_html: bool = True) -> FetchResult:
    """Fetch one URL. Retries transient failures (network, 5xx, 429) with exponential back-off and Retry-After (CR-F04)."""
    last_error: FetchError | None = None
    for attempt in range(config.RETRIES + 1):
        if attempt:
            retry_after = last_error.retry_after if last_error else None
            if retry_after is not None and retry_after > config.RETRY_AFTER_MAX:
                break  # too long to wait here: the caller schedules a later retry (last_error.retry_after says when)
            await politeness._sleep(politeness.backoff_delay(attempt, retry_after))
        started = time.perf_counter()
        try:
            result = await _one_attempt(client, url, expect_html)
        except FetchError as exc:
            exc.attempts = attempt + 1
            record_attempt(url=url, attempt_no=attempt + 1, ms=int((time.perf_counter() - started) * 1000), http_status=exc.status_code,
                           error_kind=exc.kind, retry_after=exc.retry_after, note=exc.detail[:300])
            if _retryable(exc, attempt):
                last_error = exc
                continue
            raise
        except GuardError as exc:
            record_attempt(url=url, attempt_no=attempt + 1, ms=int((time.perf_counter() - started) * 1000), error_kind="guard", note=str(exc)[:300])
            raise
        result.attempts = attempt + 1
        record_attempt(url=url, attempt_no=attempt + 1, ms=result.elapsed_ms, http_status=result.status_code, bytes=len(result.content),
                       note=f"final {result.final_url}" if result.final_url != url else None)
        return result
    raise last_error if last_error else FetchError("network", f"failed to fetch {url}")


@dataclass
class RobotsRules:
    """robots.txt for one origin.

    missing      no rules apply (404 and other 4xx: RFC 9309 2.3.1.3), or the allow-on-error policy is on
    unavailable  could not be read (5xx / 429 / network) and the policy is 'disallow' (RFC 9309 2.3.1.4): do not crawl now
    """

    origin: str
    parser: Protego | None = None
    missing: bool = False
    unavailable: bool = False
    detail: str = ""
    retry_after: float | None = None
    error_kind: str = ""        # FetchError kind when robots.txt could not be read: network | http | blocked ...

    def allowed(self, url: str) -> bool:
        if self.unavailable:
            return False
        if self.missing or self.parser is None:
            return True
        return bool(self.parser.can_fetch(url, config.user_agent()))

    def site_maps(self) -> list[str]:
        return list(self.parser.sitemaps) if self.parser is not None else []

    def crawl_delay(self) -> float | None:
        if self.parser is None:
            return None
        delay = self.parser.crawl_delay(config.user_agent())
        return float(delay) if delay else None


async def load_robots(client: httpx.AsyncClient, url: str, cache: dict[str, RobotsRules]) -> RobotsRules:
    """Fetch robots.txt for the URL's origin (CR-F01).

    2xx: parse. 4xx (not 429): no rules. 5xx, 429, network error after retries: unavailable -> not crawled now
    (ROBOTS_5XX_POLICY=disallow, the default; pending sir confirmation) or treated as missing (=allow).
    """
    parsed = urlparse(url)
    origin = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
    if origin in cache:
        return cache[origin]

    rules = RobotsRules(origin=origin)
    fail_open = settings.robots_5xx_policy() == "allow"
    try:
        result = await fetch_page(client, f"{origin}/robots.txt", expect_html=False)
        text = result.content.decode("utf-8", errors="replace")
        rules.parser = Protego.parse(text)
    except FetchError as exc:
        status = exc.status_code
        rules.detail = exc.detail
        rules.retry_after = exc.retry_after
        rules.error_kind = exc.kind
        if exc.kind in ("http", "blocked") and status is not None and 400 <= status < 500 and status != 429:
            rules.missing = True  # 401/403/404/410 ...: no rules
        elif exc.kind in ("too_large", "not_html"):
            rules.missing = True  # not a usable robots file: no rules apply
        elif fail_open:
            rules.missing = True
        else:
            rules.unavailable = True
            rules.detail = f"robots.txt unavailable ({exc.detail})"
    cache[origin] = rules
    return rules
