"""Crawler settings. Every limit the crawler respects lives here.

Defaults can be overridden with CRAWL_* environment variables (read once at import; .env is loaded by app.settings).
Tests change the module attributes directly (monkeypatch).
"""

import os

import app.settings as settings  # noqa: F401  - loads .env


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def user_agent() -> str:
    """One descriptive name with a real contact (CR-F02). Production refuses to run without CRAWLER_CONTACT_URL."""
    return settings.user_agent()


# Useful pages per website (homepage + ranked business pages), CR-C07: about 5-10, adjustable.
# The crawl stops earlier when every important page type that exists on the site has been read (coverage), not on text length (ISS-08).
MAX_PAGES = _int("CRAWL_MAX_PAGES", 8)
PER_TYPE_PAGES = 2            # at most this many pages of one page type
SUFFICIENT_TEXT_CHARS = 12_000   # kept for compatibility; no longer an early-stop rule

# Networking.
PAGE_TIMEOUT = _float("CRAWL_PAGE_TIMEOUT", 12.0)        # connect / read, per step
TOTAL_TIMEOUT = _float("CRAWL_TOTAL_TIMEOUT", 25.0)      # whole response incl. body, per request (ISS-16)
SITE_DEADLINE = _float("CRAWL_SITE_DEADLINE", 150.0)     # whole site, all pages
ROBOTS_TIMEOUT = 8.0
MAX_REDIRECTS = _int("CRAWL_MAX_REDIRECTS", 10)          # ISS-24
RETRIES = _int("CRAWL_RETRIES", 2)                       # extra attempts after the first (3 attempts in all)
RETRY_BACKOFF = _float("CRAWL_RETRY_BACKOFF", 1.0)       # 1, 2, 4 ... seconds (exponential, with jitter)
RETRY_BACKOFF_MAX = 20.0
RETRY_AFTER_MAX = _float("CRAWL_RETRY_AFTER_MAX", 120.0) # longer Retry-After => schedule a later retry instead of waiting
RETRY_JITTER = 0.25                                      # +/- fraction of the delay
MAX_BYTES_PER_PAGE = _int("CRAWL_MAX_BYTES", 6_000_000)  # decoded bytes kept; larger pages are cut, not failed (ISS-26)
MAX_DECODED_RATIO = 100                                  # decoded/encoded size limit (decompression bomb guard, ISS-02)
SITEMAP_MAX_BYTES = 5_000_000

# Concurrency across different websites. Inside one site, and per domain, requests are sequential.
CONCURRENCY = 10

# How much cleaned text one website may store (keeps the DB and later LLM calls manageable).
MAX_TEXT_CHARS = 60_000
MIN_TEXT_CHARS = 80

# Link and sitemap discovery. Sitemaps are candidates only; they are ranked with the same rules as homepage links.
MAX_LINKS_SCANNED = 800
MAX_SITEMAPS = 5
MAX_SITEMAP_URLS = 200
MAX_DISCOVERED_PER_SITE = 400   # trap guard: candidates kept per site
MAX_PATH_DEPTH = 5
MAX_QUERY_URLS = 0              # URLs with query strings are not followed (calendars, facets, sessions)

# Politeness per domain (CR-F03, F05, F07). One request at a time per domain.
DOMAIN_DELAY = _float("CRAWL_DOMAIN_MIN_INTERVAL", 1.0)   # minimum seconds between two requests to one domain
DOMAIN_DELAY_MAX = 8.0                                   # adaptive slow-down ceiling after blocking answers
CRAWL_DELAY_MAX = _float("CRAWL_DELAY_MAX", 60.0)        # robots Crawl-delay honoured up to this many seconds
BLOCK_STRIKES = 2

# Content quality (CR-D04). Thresholds are configurable.
MIN_USEFUL_PAGE_CHARS = _int("CRAWL_MIN_USEFUL_CHARS", 80)
THIN_PAGE_CHARS = _int("CRAWL_THIN_CHARS", 200)
BROWSER_TIMEOUT = _float("CRAWL_BROWSER_TIMEOUT", 15.0)
BROWSER_SETTLE = _float("CRAWL_BROWSER_SETTLE", 6.0)     # wait for the text to stop changing, at most this long
BROWSER_MAX_REQUESTS = 60
BROWSER_MAX_BYTES = 8_000_000

# Status values written to Websites.status. Lifecycle words first, then outcomes (CR-B06, A13).
STATUS_PENDING = "pending"
STATUS_QUEUED = "queued"
STATUS_CRAWLING = "crawling"
STATUS_EXTRACTING = "extracting"
STATUS_CRAWLED = "crawled"
STATUS_REDIRECTED = "redirected"
STATUS_PARKED = "parked"
STATUS_UNDER_CONSTRUCTION = "under_construction"
STATUS_REQUIRES_REVIEW = "requires_review"
STATUS_EMPTY = "empty"            # no longer produced by the crawler; kept so old rows still read
STATUS_UNREACHABLE = "unreachable"
STATUS_BLOCKED = "blocked"
STATUS_ROBOTS_BLOCKED = "robots_blocked"
STATUS_INVALID = "invalid"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

# The requirement vocabulary (CR-B06) for each status word.
WEBSITE_STATUS_WORD = {
    STATUS_PENDING: "Pending", STATUS_QUEUED: "Pending", STATUS_CRAWLING: "Pending", STATUS_EXTRACTING: "Pending",
    STATUS_CRAWLED: "Crawled", STATUS_REDIRECTED: "Redirected", STATUS_PARKED: "Parked",
    STATUS_UNDER_CONSTRUCTION: "Under Construction", STATUS_REQUIRES_REVIEW: "Requires Review", STATUS_EMPTY: "Under Construction",
    STATUS_UNREACHABLE: "Unreachable", STATUS_BLOCKED: "Blocked", STATUS_ROBOTS_BLOCKED: "Blocked",
    STATUS_INVALID: "Invalid", STATUS_FAILED: "Failed", STATUS_CANCELLED: "Failed",
}
# Statuses where the crawl produced usable evidence.
STATUSES_WITH_CONTENT = {STATUS_CRAWLED, STATUS_REDIRECTED}
