"""Stop the crawler from being pointed at private/internal addresses (SSRF), CR-B09, B10.

Imported URLs are untrusted input. Without this guard a row containing http://127.0.0.1:8080 or
http://169.254.169.254/latest/meta-data/ would make the crawler probe our own machine or cloud metadata endpoints.
Every URL - including each redirect hop and every browser request - must pass through here.

The single rule is `ip.is_global`: anything that is not a globally routable address is refused. That also covers the shared address space
100.64.0.0/10 (includes the Alibaba metadata address 100.100.100.200, ISS-03), documentation ranges, 6to4/NAT64 wrappers of private IPv4, etc.

Two different failures are kept apart (ISS-11):
  UnsafeTarget - the address is not a public website  -> status Invalid
  DnsFailure   - the name does not resolve            -> status Unreachable
Both are GuardError, so old code that catches GuardError keeps working.
"""

import ipaddress
import re
import socket
from urllib.parse import urlparse


class GuardError(Exception):
    """The address is not a public website we are allowed to fetch."""


class UnsafeTarget(GuardError):
    """Not a public address (private, loopback, link-local, shared, reserved) or not an http(s) URL."""


class DnsFailure(GuardError):
    """The host name does not resolve."""


_BLOCKED_HOSTS = {
    "localhost",
    "metadata.google.internal",
    "metadata",
    "instance-data",
}
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain", ".home.arpa", ".lan", ".corp", ".intranet")
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_LOOSE_IPV4 = re.compile(r"^(0x[0-9a-f]+|\d+)(\.(0x[0-9a-f]+|\d+)){0,3}$", re.I)


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True only for globally routable addresses. IPv4 hidden inside IPv6 is checked as IPv4."""
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return _is_public(ip.ipv4_mapped)
        if ip.sixtofour is not None and not _is_public(ip.sixtofour):
            return False
        if ip.teredo is not None:
            return False
        if ip in _NAT64:
            return _is_public(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
    return ip.is_global and not (ip.is_multicast or ip.is_unspecified)


def parse_ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse '127.0.0.1', '[::1]', and the loose forms browsers accept: 2130706433, 0x7f.1, 127.1, 0177.0.0.1."""
    host = host.strip("[]").split("%")[0]
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    if _LOOSE_IPV4.match(host):
        try:
            return ipaddress.IPv4Address(socket.inet_aton(host))
        except (OSError, ValueError):
            return None
    return None


def is_safe_import_target(url: str) -> bool:
    """Reject obvious non-public hosts before a row is stored.

    Literal private, loopback, link-local and shared-space addresses (also in decimal/hex/octal spelling) are refused here.
    Normal domain names are accepted; the crawler still checks DNS on every fetch.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    if not host or host in _BLOCKED_HOSTS or host.endswith(_BLOCKED_SUFFIXES):
        return False
    ip = parse_ip_literal(host)
    if ip is not None:
        return _is_public(ip)
    return True


def assert_public_url(url: str) -> str:
    """Return the URL when its host resolves only to public addresses.

    Raises UnsafeTarget (bad scheme/host, non-public address) or DnsFailure (name does not resolve). Both are GuardError.
    """
    try:
        parsed = urlparse(url)
        host = parsed.hostname
    except ValueError as exc:
        raise UnsafeTarget(f"malformed URL: {exc}") from exc
    if parsed.scheme not in ("http", "https"):
        raise UnsafeTarget(f"unsupported scheme: {parsed.scheme or '(none)'}")
    if not host:
        raise UnsafeTarget("URL has no host")
    lowered = host.lower().rstrip(".")
    if lowered in _BLOCKED_HOSTS or lowered.endswith(_BLOCKED_SUFFIXES):
        raise UnsafeTarget(f"host {host!r} is a local or internal name")

    literal = parse_ip_literal(lowered)
    if literal is not None:
        if not _is_public(literal):
            raise UnsafeTarget(f"host {host!r} points at non-public address {literal}")
        return url

    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise DnsFailure(f"cannot resolve host {host!r}") from exc
    except UnicodeError as exc:  # label too long / bad IDNA
        raise UnsafeTarget(f"invalid host name {host!r}") from exc
    if not infos:
        raise DnsFailure(f"cannot resolve host {host!r}")

    addresses = {info[4][0] for info in infos}
    for raw in addresses:
        ip = ipaddress.ip_address(raw.split("%")[0])
        if not _is_public(ip):
            raise UnsafeTarget(f"host {host!r} points at non-public address {ip}")

    return url
