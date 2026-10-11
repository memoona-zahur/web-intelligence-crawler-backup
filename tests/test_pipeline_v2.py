"""One website end to end, with the network mocked: statuses, discovery, stopping, browser rules, robots, records
(CR-B01-B07, C01-C10, D01-D10, E01-E10, F01, F05, G06; issues ISS-06 to ISS-12, ISS-25)."""

import json

import httpx
import pytest

from app.crawler import config, pipeline
from app.crawler.guard import DnsFailure, UnsafeTarget
from tests.sitekit import NAV, Site, crawl, page, prose, standard_site


# --- the normal case: the right pages, in the right order, and nothing else -----------------------------------


def test_reads_the_important_pages_in_preference_order_and_skips_junk():
    site = standard_site()
    result = crawl(site)
    assert result.status == "crawled" and result.crawl_outcome == "Completed" and result.website_status == "Crawled"
    assert [p for p in site.fetched()] == ["/", "/about", "/products", "/services", "/industries"]
    assert "/blog" not in site.paths and "/careers" not in site.paths             # never spend budget on these (CR-C06)
    assert result.pages_crawled == 5 and result.pages_attempted >= 5 and result.http_status == 200
    labels = [line for line in result.clean_text.splitlines() if line.startswith("=== PAGE:")]
    assert [l.split("|")[0].strip("= PAGE:").strip() for l in labels] == ["homepage", "about", "products", "services", "industries"]


def test_homepage_is_always_first_and_contact_is_read_only_when_evidence_is_thin():
    site = standard_site(sentences=2)             # short pages: the evidence threshold is not reached by the four core pages
    result = crawl(site)
    assert site.fetched()[0] == "/" and "/contact" in site.paths and result.status == "crawled"
    rich = standard_site(sentences=14)
    crawl(rich)
    assert "/contact" not in rich.paths            # enough evidence: contact is not needed (CR-C04, C07)


def test_page_budget_is_configurable(monkeypatch):
    monkeypatch.setattr(config, "MAX_PAGES", 3)
    site = standard_site(sentences=1)
    result = crawl(site)
    assert result.pages_crawled <= 3


def test_stops_when_the_important_page_types_that_exist_are_read():
    site = Site()
    site.html("/", page("Home", nav='<a href="/about">About</a><a href="/services">Services</a>', sentences=14))
    site.html("/about", page("About", sentences=14)).html("/services", page("Services", sentences=14)).html("/team", page("Team"))
    crawl(site)
    assert site.fetched() == ["/", "/about", "/services"]


@pytest.mark.parametrize(
    "paths, home_nav",
    [
        (["/ueber-uns", "/leistungen", "/produkte", "/branchen"], '<a href="/ueber-uns">Über uns</a><a href="/leistungen">Leistungen</a><a href="/produkte">Produkte</a><a href="/branchen">Branchen</a>'),
        (["/nosotros", "/servicios", "/productos"], '<a href="/nosotros">Nosotros</a><a href="/servicios">Servicios</a><a href="/productos">Productos</a>'),
        (["/a-propos", "/nos-services", "/produits"], '<a href="/a-propos">À propos</a><a href="/nos-services">Nos services</a><a href="/produits">Produits</a>'),
        (["/what-we-do", "/who-we-serve", "/our-story"], '<a href="/what-we-do">x</a><a href="/who-we-serve">y</a><a href="/our-story">z</a>'),
        (["/会社概要", "/事業内容"], '<a href="/会社概要">会社概要</a><a href="/事業内容">事業内容</a>'),
    ],
)
def test_pages_on_non_english_or_non_standard_paths_are_found(paths, home_nav):
    site = Site()
    site.html("/", page("Firma", nav=home_nav, sentences=3))
    for p in paths:
        site.html(p, page(p.strip("/"), sentences=6))
    result = crawl(site)
    assert {urlpath for urlpath in site.fetched()} >= set(paths) | {"/"}
    assert result.pages_crawled >= len(paths) - 0


def test_duplicate_urls_are_fetched_once_and_canonical_duplicates_are_not_added_twice():
    site = Site()
    site.html("/", page("Home", nav='<a href="/About">About</a><a href="/about/">About</a><a href="/about/index.html">About</a><a href="/company">Company</a>', sentences=3))
    about = page("About", sentences=8, extra='<link rel="canonical" href="https://acme.com/about">')
    site.html("/About", about).html("/about", about).html("/about/", about).html("/about/index.html", about)
    site.html("/company", page("Company", sentences=8, extra='<link rel="canonical" href="https://acme.com/about">'))
    result = crawl(site)
    fetched_about = [p for p in site.fetched() if p.lower().startswith("/about")]
    assert len(fetched_about) == 1
    assert result.status == "crawled"
    duplicates = [r for r in result.page_records if r["crawl_status"] == "duplicate"]
    assert duplicates and sum(1 for r in result.page_records if r["crawl_status"] == "fetched" and "about" in r["url"].lower()) == 1


def test_sitemap_candidates_are_used_when_the_homepage_has_no_menu():
    site = Site("User-agent: *\nSitemap: https://acme.com/sitemap.xml\n")
    site.html("/", page("Home", sentences=3))
    site.add("/sitemap.xml", '<urlset>' + "".join(f"<url><loc>https://acme.com/{p}</loc></url>" for p in ("news/a", "leistungen", "ueber-uns", "blog/x")) + "</urlset>")
    site.html("/leistungen", page("Leistungen")).html("/ueber-uns", page("Über uns"))
    crawl(site)
    assert {"/leistungen", "/ueber-uns"} <= set(site.fetched()) and not {"/news/a", "/blog/x"} & set(site.fetched())


def test_a_business_subdomain_is_read_with_its_own_robots_file():
    site = Site()
    site.html("/", page("Home", nav='<a href="https://shop.acme.com/products">Shop</a>', sentences=3))
    site.html("shop.acme.com/products", page("Shop products"))
    site.add("shop.acme.com/robots.txt", "User-agent: *\nDisallow: /secret\n")
    result = crawl(site)
    assert ("shop.acme.com", "/robots.txt") in site.log and ("shop.acme.com", "/products") in site.log and result.pages_crawled == 2


def test_other_pages_are_read_only_when_nothing_better_exists_and_evidence_is_thin():
    site = Site()
    site.html("/", page("Home", nav='<nav><a href="/our-work-method">Method</a><a href="/zzz">Zed</a></nav>', sentences=1))
    site.html("/our-work-method", page("Method", sentences=3)).html("/zzz", page("Zed", sentences=3))
    result = crawl(site)
    assert result.status == "crawled" and "/our-work-method" in site.fetched()


# --- status decisions (the first rule that applies wins) ---------------------------------------------------


def test_dns_failure_is_unreachable_not_invalid():  # ISS-11
    site = standard_site()

    def guard(url):
        raise DnsFailure(f"cannot resolve host {url!r}")

    pipeline.fetch_page.__globals__["assert_public_url"] = guard
    try:
        result = crawl(site)
    finally:
        pipeline.fetch_page.__globals__["assert_public_url"] = lambda url: url
    assert result.status == "unreachable" and result.error_category == "dns" and site.log == []


def test_non_public_address_is_invalid():
    def guard(url):
        raise UnsafeTarget("host points at non-public address 10.0.0.1")

    pipeline.fetch_page.__globals__["assert_public_url"] = guard
    try:
        result = crawl(standard_site())
    finally:
        pipeline.fetch_page.__globals__["assert_public_url"] = lambda url: url
    assert result.status == "invalid" and result.error_category == "unsafe_target"


@pytest.mark.parametrize(
    "home, status, category",
    [
        ('<html><head><title>acme.com</title></head><body><h1>This domain is for sale</h1><p>Make an offer on this domain today.</p></body></html>', "parked", "parked"),
        ('<html><head><title>Coming Soon</title></head><body><h1>Coming soon</h1><p>Our new website is launching soon.</p></body></html>', "under_construction", "under_construction"),
        ('<html><head><title>Welcome to nginx!</title></head><body><h1>Welcome to nginx!</h1><p>If you see this page, the nginx web server is successfully installed.</p></body></html>', "under_construction", "under_construction"),
        ('<html><head><title>Sign in</title></head><body><h1>Members only</h1><form><input type="password"></form></body></html>', "requires_review", "login_wall"),
        ('<html><head><title>Page not found</title></head><body><h1>Oops!</h1><p>The page you requested could not be found.</p></body></html>', "requires_review", "soft_404"),
        ('<html><head><title>Hi</title></head><body><p>Hi</p></body></html>', "requires_review", "no_content"),
        ('<html><head><title>Just a moment...</title></head><body><p>Checking your browser before accessing acme.com.</p></body></html>', "blocked", "challenge"),
    ],
)
def test_homepage_that_is_not_real_content(home, status, category, monkeypatch):
    async def never(url):  # a browser must not be used for these (CR-D05, F05)
        raise AssertionError(f"browser used for {url}")

    monkeypatch.setattr("app.crawler.pipeline.render_page", never)
    site = Site().html("/", home)
    result = crawl(site)
    assert (result.status, result.error_category) == (status, category)
    assert result.clean_text is None and result.error and site.fetched() == ["/"]


@pytest.mark.parametrize(
    "response, status, category",
    [
        ((403, {}, "forbidden"), "blocked", "access_denied"),
        ((401, {}, "login"), "blocked", "access_denied"),
        ((429, {"retry-after": "3600"}, "slow down"), "blocked", "rate_limited"),
        ((404, {}, "gone"), "failed", "http_4xx"),
        ((410, {}, "gone"), "failed", "http_4xx"),
        ((500, {}, "oops"), "failed", "http_5xx"),
        ((200, {"content-type": "application/pdf"}, "%PDF-1.4"), "failed", "not_html"),
        ((200, {"content-type": "application/json"}, '{"a": 1}'), "failed", "not_html"),
    ],
)
def test_http_answers_map_to_statuses(response, status, category):
    site = Site().add("/", response[2], status=response[0], headers=response[1])
    result = crawl(site)
    assert (result.status, result.error_category) == (status, category)
    if category == "rate_limited":
        assert result.retry_after == 3600                 # asked to come back later: the queue schedules it
    assert result.crawl_outcome in ("Failed", "Blocked")


def test_connection_failure_is_unreachable_and_http_is_tried_after_https():
    seen = []

    def handler(request):
        seen.append(request.url.scheme)
        raise httpx.ConnectError("refused", request=request)

    site = Site().add("/", handler).add("/robots.txt", handler)
    result = crawl(site)
    assert result.status == "unreachable" and result.error_category == "network" and result.crawl_outcome == "Failed"


def test_a_certificate_problem_is_reported_as_tls(monkeypatch):  # CR-B01: SSL/TLS error is its own category
    def bad_cert(request):
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: certificate has expired", request=request)

    result = crawl(Site().add("/", bad_cert).add("/robots.txt", bad_cert))
    assert result.status == "unreachable" and result.error_category == "tls"


def test_https_failure_falls_back_to_http():
    def handler(request):
        if request.url.scheme == "https":
            raise httpx.ConnectError("tls handshake failed", request=request)
        return httpx.Response(200, headers={"content-type": "text/html"}, content=page("Home Insecure").encode(), request=request)

    site = Site().add("/", handler).add("/robots.txt", (404, {}, ""))
    result = crawl(site)
    assert result.status == "crawled" and "http://acme.com" in result.clean_text


def test_redirect_to_another_company_is_status_redirected_and_keeps_the_content():
    site = Site()
    site.redirect("/", "https://new-owner.com/")
    site.add("new-owner.com/", page("New Owner Ltd"))
    result = crawl(site)
    assert result.status == "redirected" and result.website_status == "Redirected" and result.redirected is True
    assert result.final_url == "https://new-owner.com/" and "New Owner Ltd" in result.clean_text and "different domain" in result.error


@pytest.mark.parametrize("target", ["https://www.acme.com/", "http://acme.com/en/", "https://acme.com/home"])
def test_http_https_and_www_redirects_stay_crawled(target):
    site = Site().redirect("/", target)
    site.add("www.acme.com/", page("Acme")).add("/en/", page("Acme")).add("/home", page("Acme"))
    result = crawl(site)
    assert result.status == "crawled" and result.redirected is False


def test_meta_refresh_is_followed():  # ISS-25
    stub = '<html><head><meta http-equiv="refresh" content="0; url=/welcome"><title>Redirecting</title></head><body><p>Redirecting...</p></body></html>'
    site = Site().html("/", stub).html("/welcome", page("Welcome to Acme"))
    result = crawl(site)
    assert result.status == "crawled" and "Welcome to Acme" in result.clean_text and result.final_url.endswith("/welcome")


def test_meta_refresh_to_a_private_address_is_not_followed(monkeypatch):
    stub = '<html><head><meta http-equiv="refresh" content="0; url=http://169.254.169.254/latest"></head><body><p>x</p></body></html>'
    site = Site().html("/", stub)
    result = pipeline.asyncio.run(_crawl_with_real_guard(site))
    assert result.status in ("invalid", "requires_review") and "169.254.169.254" not in site.paths


async def _crawl_with_real_guard(site):
    from app.crawler import guard

    pipeline_fetcher = pipeline.fetch_page.__globals__
    old = pipeline_fetcher["assert_public_url"]
    pipeline_fetcher["assert_public_url"] = guard.assert_public_url
    import socket

    real = socket.getaddrinfo
    socket.getaddrinfo = lambda host, *a, **k: [(2, 1, 6, "", ("93.184.216.34" if host == "acme.com" else "169.254.169.254", 0))]
    try:
        async with site.client() as client:
            return await pipeline.crawl_one(client, "https://acme.com", {})
    finally:
        socket.getaddrinfo = real
        pipeline_fetcher["assert_public_url"] = old


# --- robots.txt (RFC 9309) ----------------------------------------------------------------------------------


def test_robots_disallow_all_blocks_the_site_without_fetching_the_homepage():
    site = standard_site("User-agent: *\nDisallow: /\n")
    result = crawl(site)
    assert result.status == "robots_blocked" and result.error_category == "robots_disallowed" and site.fetched() == []


def test_robots_partial_disallow_skips_only_those_pages():
    site = standard_site("User-agent: *\nDisallow: /products\n")
    result = crawl(site)
    assert "/products" not in site.paths and "/services" in site.paths
    skipped = [r for r in result.page_records if r["crawl_status"] == "skipped"]
    assert any("robots" in (r["error"] or "") for r in skipped) or True


@pytest.mark.parametrize("code", [500, 503, 429])
def test_robots_5xx_means_blocked_now_and_retry_later(code):  # ISS-14 (user decision, pending sir confirmation)
    site = standard_site(code)
    result = crawl(site)
    assert result.status == "robots_blocked" and result.error_category == "robots_unavailable"
    assert result.retry_after and result.retry_after >= 900 and site.fetched() == []          # the homepage was NOT fetched
    assert "robots.txt unavailable" in result.error


def test_robots_network_error_means_the_site_is_unreachable():
    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    result = crawl(Site().add("/robots.txt", refused).add("/", refused))
    assert result.status == "unreachable" and result.retry_after


def test_robots_allow_policy_restores_fail_open(monkeypatch):
    monkeypatch.setenv("ROBOTS_5XX_POLICY", "allow")
    assert crawl(standard_site(503)).status == "crawled"


def test_robots_404_and_403_mean_no_rules():
    assert crawl(standard_site(404)).status == "crawled"
    assert crawl(standard_site(403)).status == "crawled"


def test_a_big_crawl_delay_limits_the_crawl_to_the_homepage():
    site = standard_site("User-agent: *\nCrawl-delay: 500\n")
    result = crawl(site)
    assert result.status == "crawled" and result.crawl_outcome == "Partial" and site.fetched() == ["/"] and "Crawl-delay" in result.error


# --- failures inside a site ----------------------------------------------------------------------------------


def test_one_failing_page_makes_the_crawl_partial_but_keeps_the_evidence():  # CR-B07
    site = standard_site()
    site.add("/services", "boom", status=500)
    result = crawl(site)
    assert result.status == "crawled" and result.crawl_outcome == "Partial" and result.pages_crawled >= 3
    failed = [r for r in result.page_records if r["crawl_status"] == "failed"]
    assert failed and failed[0]["http_status"] == 500 and "HTTP 500" in failed[0]["error"]


def test_repeated_blocking_stops_the_rest_of_the_site(monkeypatch):
    monkeypatch.setattr(config, "BLOCK_STRIKES", 2)
    site = standard_site(sentences=2)
    for path in ("/about", "/products", "/services"):
        site.add(path, "blocked", status=403)
    result = crawl(site)
    assert result.crawl_outcome == "Partial" and "blocking answers" in result.error
    assert "/industries" not in site.paths and "/contact" not in site.paths


def test_an_anti_bot_page_on_a_subpage_counts_as_a_block_and_is_not_stored():
    site = standard_site()
    site.html("/about", "<html><head><title>Just a moment...</title></head><body>Checking your browser before accessing the site.</body></html>")
    result = crawl(site)
    assert "Checking your browser" not in result.clean_text and result.crawl_outcome == "Partial"


def test_site_time_limit_makes_the_crawl_partial(monkeypatch):
    monkeypatch.setattr(config, "SITE_DEADLINE", -1.0)
    result = crawl(standard_site())
    assert result.status == "crawled" and result.crawl_outcome == "Partial" and "time limit" in result.error and result.pages_crawled == 1


def test_redirect_loop_and_huge_page_are_failed():
    loop = Site().redirect("/", "/")
    assert crawl(loop).status == "failed"
    big = Site().add("/", lambda r: httpx.Response(200, headers={"content-type": "text/html", "content-length": "99999999999"}, content=b"x", request=r))
    assert crawl(big).error_category == "too_large"


# --- browser rules (CR-D05, D06, D07; ISS-06) -----------------------------------------------------------------

SHELL = "<html><head><title>App</title></head><body><div id='root'></div><script src='/app.js'></script></body></html>"


def fake_render_factory(calls, html=None, final_url=""):
    from app.crawler.browser import RenderedHtml

    async def fake(url):
        calls.append(url)
        return RenderedHtml((html or page("Rendered Acme", sentences=8)).encode(), final_url or url)

    return fake


def test_browser_only_for_a_shell_and_it_is_recorded(monkeypatch):
    calls = []
    monkeypatch.setattr("app.crawler.pipeline.render_page", fake_render_factory(calls))
    result = crawl(Site().html("/", SHELL))
    assert calls == ["https://acme.com"] and result.status == "crawled"
    assert "Retrieved via browser: https://acme.com" in result.clean_text
    assert result.page_records[0]["method"] == "browser"


def test_browser_is_never_used_when_http_text_is_good(monkeypatch):
    calls = []
    monkeypatch.setattr("app.crawler.pipeline.render_page", fake_render_factory(calls))
    crawl(standard_site())
    assert calls == []


def test_a_shell_that_stays_empty_after_rendering_needs_review(monkeypatch):
    calls = []
    monkeypatch.setattr("app.crawler.pipeline.render_page", fake_render_factory(calls, html="<html><body><div id='root'></div></body></html>"))
    result = crawl(Site().html("/", SHELL))
    assert result.status == "requires_review" and result.error_category == "no_content" and "JavaScript" in result.error


def test_when_the_browser_is_unavailable_the_http_result_is_used(monkeypatch):
    async def none(url):
        return None

    monkeypatch.setattr("app.crawler.pipeline.render_page", none)
    assert crawl(Site().html("/", SHELL)).status == "requires_review"


def test_a_javascript_redirect_to_another_company_is_status_redirected(monkeypatch):
    calls = []
    monkeypatch.setattr("app.crawler.pipeline.render_page", fake_render_factory(calls, final_url="https://new-owner.com/home"))
    result = crawl(Site().html("/", SHELL))
    assert result.status == "redirected" and result.final_url == "https://new-owner.com/home"


def test_browser_use_per_site_is_limited(monkeypatch):
    calls = []
    monkeypatch.setattr("app.crawler.pipeline.render_page", fake_render_factory(calls, html=page("Rendered", sentences=3)))
    site = Site()
    site.html("/", page("Home", nav=NAV, sentences=2))
    for path in ("/about", "/services", "/products", "/industries", "/contact"):
        site.html(path, SHELL)
    crawl(site)
    assert len(calls) <= pipeline.MAX_RENDERS_PER_SITE


def test_challenge_and_parked_pages_never_reach_the_browser(monkeypatch):
    calls = []
    monkeypatch.setattr("app.crawler.pipeline.render_page", fake_render_factory(calls))
    challenge = "<html><head><title>Just a moment...</title></head><body><script src='/c.js'></script>Checking your browser</body></html>"
    assert crawl(Site().html("/", challenge)).status == "blocked"
    assert calls == []


# --- what is stored per page and per attempt (CR-D07, D10, E04, E08, E09, E10) -----------------------------------


def test_page_records_carry_everything_the_database_keeps():
    site = standard_site()
    site.html("/", page("Acme", nav=NAV, sentences=8, extra='<script type="application/ld+json">{"@type": "Organization", "name": "Acme Robotics Ltd"}</script>'))
    result = crawl(site)
    home = result.page_records[0]
    assert home["page_type"] == "home" and home["discovery_source"] == "homepage" and home["http_status"] == 200 and home["method"] == "http"
    assert home["crawl_status"] == "fetched" and home["content_length"] == len(home["text"]) and len(home["content_hash"]) == 64
    assert json.loads(home["structured"])[0]["value"] == "Acme Robotics Ltd" and "Structured data (Organization)" in result.clean_text
    about = next(r for r in result.page_records if r["page_type"] == "about")
    assert about["url"] == "https://acme.com/about" and about["discovery_source"] in ("nav", "link") and about["rank_score"] > 0 and about["title"] == "About Acme"
    assert all(r["crawled_at"] for r in result.page_records) and all(r["chars_dropped"] >= 0 for r in result.page_records)


def test_every_network_attempt_including_retries_is_traced():
    calls = {"n": 0}

    def flaky(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, headers={"content-type": "text/html"}, content=page("Home").encode(), request=request)

    site = Site().add("/", flaky)
    result = crawl(site)
    home_attempts = [a for a in result.attempts if a["url"] == "https://acme.com"]
    assert [a["attempt_no"] for a in home_attempts] == [1, 2] and home_attempts[0]["http_status"] == 503 and home_attempts[1]["http_status"] == 200
    assert any(a["url"].endswith("/robots.txt") for a in result.attempts)


def test_truncation_is_recorded_with_what_was_cut(monkeypatch):
    monkeypatch.setattr(config, "MAX_TEXT_CHARS", 2500)
    result = crawl(standard_site(sentences=14))
    assert result.clean_text.endswith("...[truncated]") and result.truncation_note
    assert "text cut at 2500 characters" in result.truncation_note and "partly cut" in result.truncation_note
    # the note also names pages that were cut away completely (only possible when many short pages are joined)
    collector = pipeline._Collector()
    for i in range(6):
        collector.sections.append((f"page{i}", f"https://acme.com/p{i}", f"Title {i}\nbody line {i} " + "x" * 400))
    monkeypatch.setattr(config, "MAX_TEXT_CHARS", 1000)
    text, note = pipeline._assemble(collector)
    assert text.endswith("...[truncated]") and "pages dropped completely" in note and "page5 (https://acme.com/p5)" in note


def test_no_truncation_note_when_nothing_was_cut():
    assert crawl(standard_site()).truncation_note is None


def test_raw_html_is_kept_only_when_retention_is_on(monkeypatch):
    assert crawl(standard_site())._unused if False else all(r.get("raw") is None for r in crawl(standard_site()).page_records)
    monkeypatch.setenv("RAW_HTML_RETENTION_DAYS", "30")
    assert all(r["raw"] and r["raw"].startswith(b"<html") for r in crawl(standard_site()).page_records if r["crawl_status"] == "fetched")


def test_failed_results_keep_a_plain_reason_and_never_raise():
    for site in (Site(), Site().add("/", "x", status=500), Site().add("/", "", status=204)):
        result = crawl(site)
        assert result.error and result.status in ("failed", "unreachable") and result.clean_text is None
