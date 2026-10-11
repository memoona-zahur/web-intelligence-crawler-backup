"""Turn a messy URL into one canonical website address (CR-A06, A07, A08, B05, F08).

Two different-looking links can be the same company:

    https://www.Stripe.com/about
    http://stripe.com./
    ＳＴＲＩＰＥ．ｃｏｍ

All become:

    https://stripe.com

That canonical form is what we use to avoid saving the same company twice. A non-default port is kept (https://host:8443).
`normalize_website` never raises: a bad line returns None, and `explain_invalid` says why (ISS-04, ISS-36).
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

from app.crawler.guard import parse_ip_literal

_INVISIBLE = dict.fromkeys(map(ord, "﻿​‌‍⁠ "), None)
_SCHEME = re.compile(r"^([a-z][a-z0-9+.\-]*):(?!\d+(?:[/?#]|$))", re.I)   # 'mailto:' / 'ftp:' but not 'example.com:443'
_LABEL = re.compile(r"^[a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9_])?$")
_CREDENTIALS = re.compile(r"^([a-z][a-z0-9+.\-]*://)[^/?#@\s]*@", re.I)


def redact_credentials(raw: str) -> str:
    """Remove user:password@ from a URL before it is stored (CR-F08). Everything else stays as received (CR-A07)."""
    return _CREDENTIALS.sub(lambda m: m.group(1), raw.strip(), count=1) if "@" in raw and "://" in raw else raw.strip()


def _clean(raw: str) -> str:
    text = unicodedata.normalize("NFKC", raw).translate(_INVISIBLE).strip()
    text = text.strip("\"'`<>,; \t")
    return text.strip()


def explain_invalid(raw: str) -> str:
    """Short reason why a line is not a usable website (for the import review)."""
    result = _parse(raw)
    return result[1] if result[0] is None else ""


def _parse(raw: str) -> tuple[str | None, str]:
    """Return (normalized, '') or (None, reason). Never raises."""
    try:
        return _parse_inner(raw)
    except Exception as exc:  # noqa: BLE001 - one bad line must never stop an import
        return None, f"not a valid address ({type(exc).__name__})"


def _parse_inner(raw: str) -> tuple[str | None, str]:
    text = _clean(raw if isinstance(raw, str) else str(raw))
    if not text or text.startswith("#"):
        return None, "empty line or comment"
    if len(text) > 2048:
        return None, "URL longer than 2048 characters"
    if any(ch in text for ch in " \t\r\n"):
        return None, "contains spaces"

    scheme = ""
    if text.startswith("//"):
        text = "https:" + text
    m = _SCHEME.match(text)
    if m:
        scheme = m.group(1).lower()
        if scheme not in ("http", "https") or not text[len(m.group(0)):].startswith("//"):
            return None, f"unsupported scheme '{scheme}:'"
    elif "://" in text:
        return None, "malformed scheme"
    else:
        text = "https://" + text

    after = text.split("://", 1)[1]
    netloc = re.split(r"[/?#]", after, maxsplit=1)[0]
    if "@" in netloc:  # user:password@host - credentials are dropped (CR-F08)
        netloc = netloc.rsplit("@", 1)[1]
    if not netloc:
        return None, "no host"

    parsed = urlparse("//" + netloc)
    try:
        port = parsed.port
    except ValueError:
        return None, "invalid port"
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        return None, "no host"

    ip = parse_ip_literal(host)
    if ip is not None:
        if ip.version == 4 and not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
            return None, "IP address written in an unusual form (not a website name)"
        host = f"[{ip}]" if ip.version == 6 else str(ip)
    else:
        host = host.removeprefix("www.")
        if not host or "." not in host:
            return None, "host has no dot (not a public domain name)"
        if len(host) > 253:
            return None, "host name longer than 253 characters"
        if not host.isascii():
            try:
                host = host.encode("idna").decode("ascii")  # münchen.de -> xn--mnchen-3ya.de
            except UnicodeError:
                return None, "invalid international host name"
        labels = host.split(".")
        if any(len(label) > 63 for label in labels):
            return None, "a part of the host name is longer than 63 characters"
        if any(not _LABEL.match(label) for label in labels):
            return None, "invalid characters in the host name"
        if labels[-1].isdigit():
            return None, "top-level domain cannot be numeric"
    if port is not None and not 1 <= port <= 65535:
        return None, "invalid port"
    suffix = f":{port}" if port and port not in (80, 443) else ""
    return f"https://{host}{suffix}", ""


def normalize_website(raw: str) -> str | None:
    """Return https://domain[:port], or None if this is not a usable website address. Never raises."""
    return _parse(raw)[0]
