"""Domain helpers: which names belong to the same site (CR-A06, B05, F03, F07).

Uses the public-suffix list that ships inside tldextract (no download), including private suffixes such as wixsite.com and github.io,
so two unrelated small businesses on one site builder are NOT treated as one domain.
"""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from urllib.parse import urlparse

import tldextract

_EXTRACT = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None, include_psl_private_domains=True)


def host_of(value: str) -> str:
    """Lower-case host from a URL or a bare host name (no port, no trailing dot)."""
    text = (value or "").strip()
    host = urlparse(text if "://" in text else "//" + text).hostname or ""
    return host.lower().rstrip(".")


@lru_cache(maxsize=50_000)
def _registrable_for_host(host: str) -> str:
    if not host:
        return ""
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    result = _EXTRACT(host)
    return (result.top_domain_under_public_suffix or host).lower()


def registrable_domain(value: str) -> str:
    """acme.co.uk for www.acme.co.uk; the host itself for IP literals and unknown suffixes."""
    return _registrable_for_host(host_of(value))


def domain_key(value: str) -> str:
    """Key used for politeness and for 'one running task per domain'. A non-default port is part of it (two servers on one IP are two sites)."""
    base = registrable_domain(value)
    text = (value or "").strip()
    try:
        port = urlparse(text if "://" in text else "//" + text).port
    except ValueError:
        port = None
    return f"{base}:{port}" if base and port and port not in (80, 443) else base


def same_site(url_a: str, url_b: str) -> bool:
    """http->https and www<->apex are the same site; a different registrable domain is a cross-domain redirect."""
    a, b = registrable_domain(url_a), registrable_domain(url_b)
    return bool(a) and a == b
