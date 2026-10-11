"""Resource limits. Environment values override the defaults."""

from __future__ import annotations

import os

import app.settings  # noqa: F401  - loads .env once, so these limits see it in every entry point (ISS-21)


def _int(name: str, default: int, low: int, high: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return min(high, max(low, value))


def max_upload_bytes() -> int:
    # 25 MB: a 60,000-line URL list is 2-3 MB; Excel files are larger (ISS-17)
    return _int("MAX_UPLOAD_BYTES", 25_000_000, 1_000, 200_000_000)


def max_import_chars() -> int:
    return _int("MAX_IMPORT_CHARS", 25_000_000, 1_000, 200_000_000)


def stuck_minutes() -> int:
    return _int("CRAWL_STUCK_MINUTES", 30, 1, 24 * 60)


def backup_keep() -> int:
    return _int("BACKUP_KEEP", 7, 1, 100)


def crawl_concurrency() -> int:
    return _int("CRAWL_CONCURRENCY", 10, 1, 20)
