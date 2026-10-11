"""HTTP-first retrieval and robots (CR-D01, D02, D09, F01, F02, F04, F05, F08; issues ISS-02, 14, 15, 16, 24, 26, 31)."""

import asyncio
import gzip
import time
import tracemalloc
import zlib

import httpx
import pytest

from app.crawler import config, politeness
from app.crawler.client import new_client
from app.crawler.fetcher import ATTEMPT_TRACE, FetchError, fetch_page, load_robots, parse_retry_after
from app.settings import ContactPolicyError
from tests.helpers import make_client, stream_response


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def sleeps(monkeypatch):
    """Record the waiting the crawler asks for, without really waiting."""
    seen: list[float] = []

    async def fake_sleep(seconds):
        seen.append(seconds)

    monkeypatch.setattr(politeness, "_sleep", fake_sleep)
    monkeypatch.setattr(config, "RETRY_BACKOFF", 1.0)
    monkeypatch.setattr(config, "RETRY_JITTER", 0.0)
    monkeypatch.setattr(config, "DOMAIN_DELAY_MAX", 0.0)   # no gate slow-down in these tests: only the retry waiting is recorded
    return seen


# --- D01 / D02: HTTP first, headers, redirects, content types -----------------------------------------------


def test_request_identifies_the_crawler_with_one_name_and_contact(monkeypatch):
    monkeypatch.setenv("CRAWLER_MODE", "test")
    monkeypatch.setenv("CRAWLER_CONTACT_URL", "https://policy.acme-research.org/bot")
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, html="<html>x</html>", request=request)

    run(fetch_page(make_client(handler), "https://example.com/"))
    assert seen["user-agent"] == "WebsiteIntelligenceBot/2.0 (+https://policy.acme-research.org/bot)"
    assert "gzip" in seen["accept-encoding"]


def test_ten_redirects_are_followed_the_eleventh_fails():  # ISS-24
    def handler(request):
        n = int(request.url.path.strip("/") or 0)
        if n < 10:
            return httpx.Response(302, headers={"location": f"/{n + 1}"}, request=request)
        return httpx.Response(200, html="<html>end</html>", request=request)

    result = run(fetch_page(make_client(handler), "https://example.com/0"))
    assert result.final_url.endswith("/10") and len(result.redirects) == 10

    def too_long(request):
        n = int(request.url.path.strip("/") or 0)
        return httpx.Response(302, headers={"location": f"/{n + 1}"}, request=request)

    with pytest.raises(FetchError) as exc:
        run(fetch_page(make_client(too_long), "https://example.com/0"))
    assert exc.value.kind == "redirect"


def test_pdf_and_json_are_not_html():
    def pdf(request):
        return httpx.Response(200, content=b"%PDF-1.4 ...", headers={"content-type": "text/html"}, request=request)  # lying header

    with pytest.raises(FetchError) as exc:
        run(fetch_page(make_client(pdf), "https://example.com/"))
    assert exc.value.kind == "not_html"

    def js(request):
        return httpx.Response(200, json={"a": 1}, request=request)

    with pytest.raises(FetchError) as exc:
        run(fetch_page(make_client(js), "https://example.com/"))
    assert exc.value.kind == "not_html"


def test_invalid_host_name_is_an_invalid_kind_with_a_plain_message():  # ISS-36
    def handler(request):
        raise httpx.InvalidURL("bad")

    with pytest.raises(FetchError) as exc:
        run(fetch_page(make_client(handler), "https://example.com/"))
    assert exc.value.kind == "invalid" and "codec" not in exc.value.detail


# --- D09: size, time, decompression --------------------------------------------------------------------------


def test_a_page_a_little_over_two_megabytes_is_fetched():  # ISS-26 (legitimate 2-6 MB pages must work)
    body = b"<html><body>" + b"<p>real text</p>" * 150_000 + b"</body></html>"   # about 2.4 MB
    assert len(body) > 2_000_000

    def handler(request):
        return httpx.Response(200, content=body, headers={"content-type": "text/html"}, request=request)

    assert len(run(fetch_page(make_client(handler), "https://example.com/")).content) == len(body)


def test_body_larger_than_the_cap_fails_without_reading_everything(monkeypatch):
    monkeypatch.setattr(config, "MAX_BYTES_PER_PAGE", 100_000)
    read = {"n": 0}

    class Endless(httpx.AsyncByteStream):
        async def __aiter__(self):
            while True:
                read["n"] += 1
                yield b"x" * 10_000

    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, stream=Endless(), request=request)

    with pytest.raises(FetchError) as exc:
        run(fetch_page(make_client(handler), "https://example.com/"))
    assert exc.value.kind == "too_large"
    assert read["n"] < 40  # stopped soon after the cap, did not drain an endless stream


def test_gzip_bomb_is_stopped_and_memory_stays_bounded():  # ISS-02, CR-D09
    plain_size = 150_000_000
    bomb = gzip.compress(b"\0" * plain_size, 9)
    assert len(bomb) < 500_000

    def handler(request):
        return stream_response(request, bomb, headers={"content-type": "text/html", "content-encoding": "gzip"}, chunk=8192)

    tracemalloc.start()
    try:
        with pytest.raises(FetchError) as exc:
            run(fetch_page(make_client(handler), "https://example.com/"))
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert exc.value.kind == "too_large"
    assert peak < 60_000_000, f"peak memory {peak / 1e6:.0f} MB for a {plain_size / 1e6:.0f} MB expansion"


def test_deflate_bomb_is_stopped_too():
    bomb = zlib.compress(b"\0" * 80_000_000, 9)

    def handler(request):
        return stream_response(request, bomb, headers={"content-type": "text/html", "content-encoding": "deflate"}, chunk=8192)

    with pytest.raises(FetchError) as exc:
        run(fetch_page(make_client(handler), "https://example.com/"))
    assert exc.value.kind == "too_large"


def test_normal_gzip_page_is_decoded():
    html = b"<html><body>" + b"<p>Hello compressed world</p>" * 200 + b"</body></html>"

    def handler(request):
        return stream_response(request, gzip.compress(html), headers={"content-type": "text/html", "content-encoding": "gzip"}, chunk=500)

    assert run(fetch_page(make_client(handler), "https://example.com/")).content == html


def test_damaged_gzip_is_a_clean_error():
    def handler(request):
        return stream_response(request, b"not gzip at all", headers={"content-type": "text/html", "content-encoding": "gzip"})

    with pytest.raises(FetchError):
        run(fetch_page(make_client(handler), "https://example.com/"))


def test_slow_drip_server_is_cut_by_the_total_deadline(monkeypatch):  # ISS-16
    monkeypatch.setattr(config, "TOTAL_TIMEOUT", 0.6)
    monkeypatch.setattr(config, "PAGE_TIMEOUT", 5.0)       # every single read is fast; only the TOTAL is too long

    class Drip(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(1000):
                await asyncio.sleep(0.1)
                yield b"<p>drip</p>"

    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, stream=Drip(), request=request)

    start = time.monotonic()
    with pytest.raises(FetchError) as exc:
        run(fetch_page(make_client(handler), "https://example.com/"))
    assert exc.value.kind == "network" and exc.value.timeout is True
    assert time.monotonic() - start < 4   # 2 attempts x 0.6 s (a timeout is retried once), not 100 s


# --- F04 / F05: retries, back-off, Retry-After -----------------------------------------------------------------


def test_backoff_is_exponential(sleeps):
    def handler(request):
        return httpx.Response(503, request=request)

    with pytest.raises(FetchError):
        run(fetch_page(make_client(handler), "https://example.com/"))
    assert sleeps == [1.0, 2.0]          # 1 s, then 2 s: three attempts in all (RETRIES = 2)


def test_backoff_has_jitter_and_is_capped(monkeypatch):
    monkeypatch.setattr(config, "RETRY_BACKOFF", 4.0)
    monkeypatch.setattr(config, "RETRY_JITTER", 0.25)
    monkeypatch.setattr(config, "RETRY_BACKOFF_MAX", 10.0)
    values = {round(politeness.backoff_delay(3), 3) for _ in range(30)}
    assert len(values) > 1 and all(7.5 <= v <= 12.5 for v in values)       # 4 * 2**2 = 16 -> capped at 10, +/- 25 %
    assert politeness.backoff_delay(1) <= 5.0


def test_retry_after_is_honoured(sleeps):  # ISS-15
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, headers={"retry-after": "7"}, request=request)
        return httpx.Response(200, html="<html>ok</html>", request=request)

    assert run(fetch_page(make_client(handler), "https://example.com/")).status_code == 200
    assert sleeps and sleeps[0] >= 7


def test_429_is_retried_then_reported_as_blocked(sleeps):
    def handler(request):
        return httpx.Response(429, headers={"retry-after": "3"}, request=request)

    with pytest.raises(FetchError) as exc:
        run(fetch_page(make_client(handler), "https://example.com/"))
    assert exc.value.kind == "blocked" and exc.value.status_code == 429 and exc.value.attempts == 3
    assert sleeps and all(s >= 2.9 for s in sleeps)


def test_a_retry_after_longer_than_the_limit_is_not_waited_for(sleeps):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(503, headers={"retry-after": "3600"}, request=request)

    with pytest.raises(FetchError) as exc:
        run(fetch_page(make_client(handler), "https://example.com/"))
    assert calls["n"] == 1 and sleeps == []             # no pointless hour-long wait inside the worker
    assert exc.value.retry_after == 3600                # the caller schedules a later retry


@pytest.mark.parametrize("code", [401, 403, 404, 410])
def test_client_errors_are_not_retried(code, sleeps):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(code, request=request)

    with pytest.raises(FetchError):
        run(fetch_page(make_client(handler), "https://example.com/"))
    assert calls["n"] == 1 and sleeps == []


def test_parse_retry_after_formats():
    assert parse_retry_after("12") == 12
    assert parse_retry_after("0") == 0
    assert parse_retry_after("garbage") is None and parse_retry_after(None) is None
    assert parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT") == 0     # a date in the past


def test_every_attempt_is_traced_for_the_database(sleeps):
    def handler(request):
        return httpx.Response(500, request=request)

    trace: list[dict] = []
    token = ATTEMPT_TRACE.set(trace)
    try:
        with pytest.raises(FetchError):
            run(fetch_page(make_client(handler), "https://example.com/"))
    finally:
        ATTEMPT_TRACE.reset(token)
    assert [t["attempt_no"] for t in trace] == [1, 2, 3] and all(t["http_status"] == 500 for t in trace)


# --- F01: robots.txt (RFC 9309) ----------------------------------------------------------------------------------


def robots_from(handler_or_text, status=200):
    def handler(request):
        if callable(handler_or_text):
            return handler_or_text(request)
        return httpx.Response(status, text=handler_or_text, request=request)

    return run(load_robots(make_client(handler), "https://example.com/x", {}))


def test_robots_allow_beats_disallow_by_longest_match():
    rules = robots_from("User-agent: *\nDisallow: /private\nAllow: /private/open\n")
    assert rules.allowed("https://example.com/private/open/page") is True
    assert rules.allowed("https://example.com/private/secret") is False
    assert rules.allowed("https://example.com/about") is True


def test_robots_wildcards_and_end_anchor():
    rules = robots_from("User-agent: *\nDisallow: /*.pdf$\nDisallow: /tmp*/\n")
    assert rules.allowed("https://example.com/a/file.pdf") is False
    assert rules.allowed("https://example.com/a/file.pdf?x=1") is True
    assert rules.allowed("https://example.com/tmp123/x") is False


def test_robots_specific_group_for_our_bot_wins_over_star():
    rules = robots_from("User-agent: *\nDisallow: /\n\nUser-agent: WebsiteIntelligenceBot\nAllow: /\nDisallow: /admin\n")
    assert rules.allowed("https://example.com/about") is True
    assert rules.allowed("https://example.com/admin/x") is False


def test_robots_disallow_all_blocks_everything():
    rules = robots_from("User-agent: *\nDisallow: /\n")
    assert rules.allowed("https://example.com/") is False


def test_robots_crawl_delay_and_sitemaps_are_exposed():
    rules = robots_from("User-agent: *\nCrawl-delay: 10\nSitemap: https://example.com/s1.xml\nSitemap: https://example.com/s2.xml\n")
    assert rules.crawl_delay() == 10
    assert rules.site_maps() == ["https://example.com/s1.xml", "https://example.com/s2.xml"]


def test_malformed_robots_is_tolerated():
    rules = robots_from("\x00\x01 garbage ### \nDisallow\nUser-agent\n:::\nDisallow: /secret\n")
    assert rules.allowed("https://example.com/about") is True


@pytest.mark.parametrize("status", [404, 410, 401, 403, 400])
def test_robots_4xx_means_no_rules(status):
    rules = robots_from("", status=status)
    assert rules.missing is True and rules.unavailable is False and rules.allowed("https://example.com/anything")


@pytest.mark.parametrize("status", [500, 502, 503, 504, 429])
def test_robots_5xx_and_429_mean_do_not_crawl_now(status, sleeps):
    rules = robots_from("", status=status)
    assert rules.unavailable is True and rules.allowed("https://example.com/") is False
    assert "unavailable" in rules.detail


def test_robots_5xx_is_retried_twice_before_the_decision(sleeps):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(500, request=request)

    rules = robots_from(handler)
    assert calls["n"] == 3 and rules.unavailable


def test_robots_recovering_on_retry_is_used(sleeps):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(503, request=request)
        return httpx.Response(200, text="User-agent: *\nDisallow: /x\n", request=request)

    rules = robots_from(handler)
    assert not rules.unavailable and not rules.allowed("https://example.com/x")


def test_robots_network_error_is_unavailable_with_a_kind(sleeps):
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    rules = robots_from(handler)
    assert rules.unavailable and rules.error_kind == "network"


def test_robots_policy_allow_restores_the_old_fail_open(monkeypatch, sleeps):
    monkeypatch.setenv("ROBOTS_5XX_POLICY", "allow")
    rules = robots_from("", status=503)
    assert rules.unavailable is False and rules.allowed("https://example.com/")


def test_robots_that_is_html_or_huge_means_no_rules():
    rules = robots_from("<html>not a robots file</html>")
    assert rules.parser is not None  # parsed as text: no valid rules, everything allowed
    assert rules.allowed("https://example.com/a")


# --- F02 / F08: contact policy and cookies ------------------------------------------------------------------------


def test_test_contact_is_never_sent_to_a_non_local_host(monkeypatch):
    monkeypatch.setenv("CRAWLER_MODE", "dev")
    monkeypatch.delenv("CRAWLER_CONTACT_URL", raising=False)
    reached = []

    def handler(request):
        reached.append(request.url.host)
        return httpx.Response(200, html="<html>ok</html>", request=request)

    client = new_client(transport=httpx.MockTransport(handler))
    with pytest.raises(ContactPolicyError):
        run(fetch_page(client, "https://www.some-company.com/"))
    assert reached == []                                    # refused BEFORE the request left the client
    ok = run(fetch_page(new_client(transport=httpx.MockTransport(handler)), "http://127.0.0.1:8830/"))
    assert ok.status_code == 200 and reached == ["127.0.0.1"]


def test_production_mode_needs_a_real_contact(monkeypatch):
    monkeypatch.setenv("CRAWLER_MODE", "production")
    monkeypatch.delenv("CRAWLER_CONTACT_URL", raising=False)
    from app.settings import SettingsError

    with pytest.raises(SettingsError):
        run(fetch_page(make_client(lambda r: httpx.Response(200, html="x", request=r)), "https://example.com/"))


def test_cookies_are_not_kept(monkeypatch):  # CR-F08
    monkeypatch.setenv("CRAWLER_CONTACT_URL", "https://policy.acme-research.org/bot")

    def handler(request):
        return httpx.Response(200, html="<html>x</html>", headers={"set-cookie": "sid=abc123; Path=/"}, request=request)

    client = new_client(transport=httpx.MockTransport(handler))
    run(fetch_page(client, "https://example.com/"))
    assert len(client.cookies.jar) == 0
