"""Central settings: .env is loaded once here, so the CLI, ops, workers and web app all see the same values (ISS-21).

Policy choices that the project owner's supervisor has not confirmed yet are marked PENDING_SIR. Each one sits behind a setting with a
safe default and is described in docs/open-questions-for-sir.md. Nothing below is hard-coded policy.
"""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=False)

PENDING_SIR = "pending sir confirmation"

# The only placeholder contact the crawler accepts, and only in dev/test mode against local hosts (see check_contact_for_host).
TEST_CONTACT = "test@example.invalid"

MODES = ("production", "dev", "test")
ROBOTS_POLICIES = ("disallow", "allow")


class SettingsError(RuntimeError):
    """A required setting is missing or wrong. The message says what to set."""


class ContactPolicyError(SettingsError):
    """A placeholder contact was about to be sent to a non-local host."""


def mode() -> str:
    """production (default) | dev | test. Production needs a real CRAWLER_CONTACT_URL."""
    value = os.environ.get("CRAWLER_MODE", "production").strip().lower() or "production"
    if value not in MODES:
        raise SettingsError(f"CRAWLER_MODE must be one of {MODES}, not {value!r}")
    return value


def robots_5xx_policy() -> str:
    """What to do when robots.txt answers 5xx / 429 / cannot be reached after retries. PENDING_SIR.

    disallow (default, RFC 9309 s2.3.1.4): do not crawl the site now, retry later.
    allow: treat it like a missing robots.txt (the Phase 1 behaviour).
    """
    value = os.environ.get("ROBOTS_5XX_POLICY", "disallow").strip().lower() or "disallow"
    if value not in ROBOTS_POLICIES:
        raise SettingsError(f"ROBOTS_5XX_POLICY must be one of {ROBOTS_POLICIES}, not {value!r}")
    return value


def configured_contact() -> str:
    return os.environ.get("CRAWLER_CONTACT_URL", "").strip()


def contact_is_placeholder(contact: str) -> bool:
    """True for the test contact and for obviously fake domains (.invalid, .test, .example, example.com/org/net)."""
    text = contact.strip().lower()
    if text.startswith("mailto:"):
        text = text[len("mailto:"):]
    host = text.rsplit("@", 1)[-1] if "@" in text else text.split("://", 1)[-1].split("/", 1)[0]
    host = host.split(":", 1)[0].strip(".")
    return (
        host.endswith((".invalid", ".test", ".example", ".localhost"))
        or host in {"example.com", "example.org", "example.net", "localhost"}
        or host.endswith((".example.com", ".example.org", ".example.net"))
    )


def effective_contact() -> str:
    """The contact placed in the User-Agent. Production: must be set and must not be a placeholder."""
    contact = configured_contact()
    if mode() == "production":
        if not contact:
            raise SettingsError(
                "CRAWLER_CONTACT_URL is required in production mode (a real policy page or mailto: address). "
                "For local tests set CRAWLER_MODE=dev or test."
            )
        if contact_is_placeholder(contact):
            raise SettingsError(f"CRAWLER_CONTACT_URL {contact!r} is a placeholder; production mode needs a real contact")
        return contact
    return contact or TEST_CONTACT


def user_agent() -> str:
    """One descriptive name for every request (ISS-31)."""
    return f"WebsiteIntelligenceBot/2.0 (+{effective_contact()})"


def is_local_host(host: str | None) -> bool:
    """localhost, *.localhost and loopback addresses (127.0.0.0/8, ::1)."""
    if not host:
        return False
    host = host.strip("[]").lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False


def check_contact_for_host(host: str | None) -> None:
    """Refuse to talk to a non-local host while the contact is a placeholder (including the test contact)."""
    contact = effective_contact() if mode() != "production" else configured_contact()
    if contact and contact_is_placeholder(contact) and not is_local_host(host):
        raise ContactPolicyError(
            f"refusing to contact {host!r}: CRAWLER_CONTACT_URL is the placeholder {contact!r}; "
            "a placeholder contact may only be sent to local hosts"
        )


def database_url() -> str:
    """PostgreSQL in production (DATABASE_URL); the local SQLite file otherwise. PENDING_SIR for PostgreSQL."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url
    return f"sqlite:///{ROOT / 'data' / 'websites.db'}"


def raw_html_retention_days() -> int:
    """0 (default) = raw HTML is not stored. >0 = keep gzip raw HTML outside the database for that many days (CR-E07)."""
    try:
        return max(0, int(os.environ.get("RAW_HTML_RETENTION_DAYS", "0") or 0))
    except ValueError:
        return 0


def raw_html_dir() -> Path:
    configured = os.environ.get("RAW_HTML_DIR", "").strip()
    return Path(configured) if configured else ROOT / "data" / "raw_html"
