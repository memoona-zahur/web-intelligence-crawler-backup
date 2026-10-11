"""SSRF guard: one rule (is_global), DNS failure kept apart from unsafe targets, redirects and rebinding (CR-B09, B10, issues ISS-03, ISS-11)."""

import socket

import httpx
import pytest

from app.crawler import guard
from app.crawler.guard import DnsFailure, GuardError, UnsafeTarget, assert_public_url, is_safe_import_target


@pytest.mark.parametrize(
    "address",
    [
        "100.64.0.1", "100.100.100.200", "100.127.255.254",            # shared address space (ISS-03), includes the Alibaba metadata address
        "169.254.169.254", "169.254.0.1",                              # link-local / cloud metadata
        "127.0.0.1", "127.255.255.254", "0.0.0.0", "10.0.0.1", "172.16.5.4", "172.31.255.255", "192.168.1.1",
        "192.0.0.8", "192.0.2.5", "198.51.100.7", "203.0.113.9",       # IETF / documentation ranges
        "198.18.0.1", "198.19.255.255",                                # benchmarking
        "224.0.0.1", "239.1.1.1", "240.0.0.1", "255.255.255.255",       # multicast / reserved / broadcast
        "::1", "::", "fe80::1", "fc00::1", "fd12:3456::1", "ff02::1", "2001:db8::1",
        "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:169.254.169.254",   # IPv4 hidden inside IPv6
        "2002:7f00:0001::", "2002:0a00:0001::",                        # 6to4 wrapping 127.0.0.1 / 10.0.0.1
        "64:ff9b::7f00:1", "64:ff9b::a00:1",                           # NAT64 wrapping 127.0.0.1 / 10.0.0.1
    ],
)
def test_every_non_global_address_is_refused(address):
    host = f"[{address}]" if ":" in address else address
    assert is_safe_import_target(f"https://{host}/") is False
    with pytest.raises(UnsafeTarget):
        assert_public_url(f"http://{host}/x")


@pytest.mark.parametrize("address", ["8.8.8.8", "1.1.1.1", "93.184.216.34", "100.63.255.255", "100.128.0.1", "2606:4700:4700::1111", "64:ff9b::808:808"])
def test_public_addresses_pass(address):
    host = f"[{address}]" if ":" in address else address
    assert is_safe_import_target(f"https://{host}/") is True
    assert assert_public_url(f"http://{host}/") == f"http://{host}/"


@pytest.mark.parametrize("host", ["2130706433", "0x7f.0.0.1", "0177.0.0.1", "127.1", "0x7f000001", "017700000001", "2852039166", "0xa9fea9fe"])
def test_unusual_spellings_of_private_addresses_are_refused(host):
    assert is_safe_import_target(f"http://{host}/") is False
    with pytest.raises(UnsafeTarget):
        assert_public_url(f"http://{host}/")


@pytest.mark.parametrize("host", ["localhost", "LOCALHOST", "foo.localhost", "metadata.google.internal", "db.internal", "printer.local", "router.home.arpa", "host.lan", "intranet.corp"])
def test_internal_names_are_refused(host):
    assert is_safe_import_target(f"https://{host}") is False
    with pytest.raises(UnsafeTarget):
        assert_public_url(f"https://{host}/")


@pytest.mark.parametrize("url", ["ftp://example.com", "file:///etc/passwd", "gopher://x.com", "javascript:alert(1)", "data:text/html,hi", "http://", "https:///x"])
def test_only_http_and_https_with_a_host(url):
    assert is_safe_import_target(url) is False
    with pytest.raises(GuardError):
        assert_public_url(url)


def test_dns_failure_and_unsafe_target_are_different_errors(monkeypatch):  # ISS-11
    def fail(*_a, **_k):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", fail)
    with pytest.raises(DnsFailure):
        assert_public_url("https://does-not-exist.test/")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_a, **_k: [(2, 1, 6, "", ("10.1.2.3", 0))])
    with pytest.raises(UnsafeTarget):
        assert_public_url("https://sneaky.test/")
    assert issubclass(DnsFailure, GuardError) and issubclass(UnsafeTarget, GuardError)


def test_a_name_with_one_private_answer_is_refused(monkeypatch):
    """DNS rebinding style: one public and one private address for the same name."""
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_a, **_k: [(2, 1, 6, "", ("93.184.216.34", 0)), (2, 1, 6, "", ("192.168.0.9", 0))])
    with pytest.raises(UnsafeTarget):
        assert_public_url("https://mixed.test/")


def test_ipv6_zone_ids_and_shared_space_via_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_a, **_k: [(23, 1, 6, "", ("fe80::1%eth0", 0, 0, 0))])
    with pytest.raises(UnsafeTarget):
        assert_public_url("https://zone.test/")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_a, **_k: [(2, 1, 6, "", ("100.100.100.200", 0))])
    with pytest.raises(UnsafeTarget):
        assert_public_url("https://alibaba-metadata.test/")


def test_bad_idna_label_is_unsafe_not_a_crash(monkeypatch):
    def boom(*_a, **_k):
        raise UnicodeError("label too long")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    with pytest.raises(UnsafeTarget):
        assert_public_url("https://" + "a" * 70 + ".com/")


def test_every_redirect_hop_is_checked_with_the_real_guard(monkeypatch):
    """CR-B10: the guard runs on each hop; the private target is never requested."""
    from app.crawler.fetcher import fetch_page
    from tests.helpers import make_client
    import asyncio

    monkeypatch.setattr("app.crawler.fetcher.assert_public_url", guard.assert_public_url)
    answers = {"safe.test": "93.184.216.34", "evil.test": "10.9.9.9", "meta.test": "169.254.169.254"}
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *_a, **_k: [(2, 1, 6, "", (answers[host], 0))])
    seen = []

    def handler(request):
        seen.append(request.url.host)
        if request.url.host == "safe.test":
            return httpx.Response(302, headers={"location": "https://evil.test/secret"}, request=request)
        return httpx.Response(200, text="SECRET", request=request)

    with pytest.raises(UnsafeTarget):
        asyncio.run(fetch_page(make_client(handler), "https://safe.test/"))
    assert seen == ["safe.test"]          # evil.test was never contacted

    seen.clear()

    def handler2(request):
        seen.append(request.url.host)
        return httpx.Response(301, headers={"location": "http://meta.test/latest/meta-data/"}, request=request)

    with pytest.raises(UnsafeTarget):
        asyncio.run(fetch_page(make_client(handler2), "https://safe.test/"))
    assert seen == ["safe.test"]


def test_redirect_to_a_non_http_scheme_is_refused(monkeypatch):
    from app.crawler.fetcher import fetch_page
    from tests.helpers import make_client
    import asyncio

    monkeypatch.setattr("app.crawler.fetcher.assert_public_url", guard.assert_public_url)
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *_a, **_k: [(2, 1, 6, "", ("93.184.216.34", 0))])

    def handler(request):
        return httpx.Response(302, headers={"location": "file:///etc/passwd"}, request=request)

    with pytest.raises(GuardError):
        asyncio.run(fetch_page(make_client(handler), "https://safe.test/"))
