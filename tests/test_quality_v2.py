"""Page-quality detectors: parked, under construction, login, soft 404, challenge, JS shell, thin (CR-B02, B03, B04, D04; issues ISS-09, ISS-10)."""

import pytest

from app.crawler.extract import extract_page
from app.crawler.quality import assess_page, looks_like_shell, page_is_useful


def assess(html: str, host: str = "acme.com"):
    title, text = extract_page(html.encode(), f"https://{host}/")
    return assess_page(text, title, html.encode(), host)


PARKED = [
    "<html><head><title>acme.com</title></head><body><h1>acme.com</h1><p>This domain is for sale. Make an offer on this domain today.</p></body></html>",
    "<html><body><h1>Buy this domain</h1><p>The domain acme.com may be for sale. Contact the domain owner.</p></body></html>",
    "<html><head><title>acme.com - HugeDomains</title></head><body><p>acme.com is available for purchase. Buy now.</p><script src='https://hugedomains.com/x.js'></script></body></html>",
    "<html><body><p>Related Searches</p><p>Sponsored Listings</p><ul><li>cheap cars</li><li>car loans</li></ul><p>The Sponsored Listings displayed above are served automatically</p></body></html>",
    "<html><body><h1>This web page is parked free, courtesy of GoDaddy.com</h1></body></html>",
    "<html><body><h1>Domain Expired</h1><p>This domain has expired. Renew this domain to restore service.</p></body></html>",
    "<html><body><iframe src='https://sedoparking.com/frmpark/acme.com'></iframe><p>acme.com</p></body></html>",
]


@pytest.mark.parametrize("html", PARKED)
def test_parked_domains_are_recognised(html):
    assert assess(html).kind == "parked"


def test_landing_on_a_domain_marketplace_is_parked():
    html = "<html><body>" + "<p>Great domain names for your business and brand.</p>" * 20 + "</body></html>"
    assert assess_page("x" * 3000, "Brand", html.encode(), "hugedomains.com").kind == "parked"


def test_a_real_shop_that_says_items_are_for_sale_is_not_parked():
    html = "<html><head><title>Acme Hardware</title></head><body><h1>Acme Hardware</h1>" + "".join(f"<p>Item {i}: all items for sale in our store come with a two year warranty and free delivery across the country.</p>" for i in range(40)) + "</body></html>"
    assert assess(html).kind == "ok"


UNDER_CONSTRUCTION = [
    "<html><head><title>Coming Soon</title></head><body><h1>Coming soon</h1><p>Our new website is launching soon. Stay tuned!</p></body></html>",
    "<html><body><h1>Under construction</h1><p>This site is under construction. Please check back later.</p></body></html>",
    "<html><head><title>Welcome to nginx!</title></head><body><h1>Welcome to nginx!</h1><p>If you see this page, the nginx web server is successfully installed and working.</p></body></html>",
    "<html><head><title>Apache2 Ubuntu Default Page: It works</title></head><body><h1>Apache2 Ubuntu Default Page</h1><p>It works! This is the default welcome page used to test the correct operation of the Apache2 server.</p></body></html>",
    "<html><head><title>IIS Windows Server</title></head><body><p>Internet Information Services</p></body></html>",
    "<html><head><title>Site not found</title></head><body><p>The web server software is running but no content has been added, yet.</p></body></html>",
    "<html><body><h1>Account Suspended</h1><p>This account has been suspended. Contact your hosting provider.</p></body></html>",
    "<html><body><h1>Seite im Aufbau</h1><p>Unsere Webseite ist im Aufbau.</p></body></html>",
]


@pytest.mark.parametrize("html", UNDER_CONSTRUCTION)
def test_placeholder_and_default_server_pages(html):
    assert assess(html).kind == "under_construction"


def test_a_company_that_mentions_coming_soon_in_a_long_page_is_fine():
    html = "<html><head><title>Acme Robotics</title></head><body><h1>Acme Robotics</h1>" + "".join(f"<p>Product line {i}: we build picking and sorting robots for warehouses, with deployments in forty countries.</p>" for i in range(12)) + "<p>New models coming soon.</p></body></html>"
    assert assess(html).kind == "ok"


LOGIN = [
    "<html><head><title>Opening soon</title></head><body><h1>This store is password protected</h1><form><input type='password' name='password'></form></body></html>",
    "<html><head><title>Sign in</title></head><body><h1>Members only</h1><form><input type='text' name='u'><input type='password' name='p'></form></body></html>",
    "<html><body><p>Restricted access. Please log in to view this page.</p></body></html>",
]


@pytest.mark.parametrize("html", LOGIN)
def test_login_and_password_walls(html):
    assert assess(html).kind == "login"


def test_a_normal_page_with_a_small_login_form_is_not_a_login_wall():
    html = "<html><head><title>Acme</title></head><body><h1>Acme Corp</h1>" + "".join(f"<p>Service {i}: we provide accounting and payroll services to small companies in the region.</p>" for i in range(15)) + "<form><input type='password'></form></body></html>"
    assert assess(html).kind == "ok"


SOFT_404 = [
    "<html><head><title>Page not found</title></head><body><h1>Oops!</h1><p>The page you requested could not be found.</p></body></html>",
    "<html><head><title>404</title></head><body><p>Error 404 - nothing here</p></body></html>",
    "<html><head><title>Seite nicht gefunden</title></head><body><p>Diese Seite wurde nicht gefunden.</p></body></html>",
    "<html><body><p>Sorry, the page you are looking for does not exist.</p></body></html>",   # found by the harness run: was read as a default server page
]


@pytest.mark.parametrize("html", SOFT_404)
def test_soft_404_pages(html):
    assert assess(html).kind == "soft_404"


CHALLENGE = [
    "<html><head><title>Just a moment...</title></head><body><p>Checking your browser before accessing the site. Enable JavaScript and cookies to continue.</p></body></html>",
    "<html><head><title>Attention Required! | Cloudflare</title></head><body><h1>Sorry, you have been blocked</h1><p>You are unable to access this site.</p></body></html>",
    "<html><body><h1>Pardon Our Interruption</h1><p>As you were browsing something about your browser made us think you were a bot.</p></body></html>",
    "<html><body><p>Please verify you are a human</p><div class='g-recaptcha'></div></body></html>",
    "<html><body><div id='px-captcha'></div><p>Press and hold the button</p></body></html>",
    "<html><body><h1>Access Denied</h1><p>Request blocked by security policy. Captcha required.</p></body></html>",
]


@pytest.mark.parametrize("html", CHALLENGE)
def test_challenge_and_anti_bot_pages_are_recognised(html):
    assert assess(html).kind == "challenge"


def test_javascript_shell_vs_thin():
    shell = "<html><head><title>App</title></head><body><div id='root'></div><script src='/app.js'></script></body></html>"
    assert assess(shell).kind == "js_shell"
    assert assess("<html><body><noscript>Please enable JavaScript to use this app</noscript></body></html>").kind == "js_shell"
    assert assess("<html><head><title>Hi</title></head><body><p>Hi</p></body></html>").kind == "thin"
    assert assess("").kind == "under_construction"        # nothing at all: an empty website (CR-B03)


def test_japanese_and_chinese_pages_are_judged_by_meaning_not_by_character_count():
    """Found by the local scenario run: 70 Japanese characters (one paragraph) were called "thin" by an English-sized threshold."""
    ja = "<html><head><title>株式会社テスト</title></head><body><h1>株式会社テスト</h1><p>私たちは産業用ポンプと圧縮機の設計、製造、保守を行っています。水処理、鉱業、食品加工のお客様に長年サービスを提供しています。</p></body></html>"
    zh = "<html><head><title>某某公司</title></head><body><h1>某某公司</h1><p>我们生产工业水泵和压缩机，为水处理和矿业客户提供三十年的服务。</p></body></html>"
    assert assess(ja).kind == "ok" and assess(zh).kind == "ok"
    from app.crawler.quality import info_length, page_is_useful

    assert info_length("abc") == 3 and info_length("日本語") == 7.5
    assert page_is_useful("私たちは産業用ポンプと圧縮機の設計、製造、保守を行っています。水処理、鉱業のお客様に長年サービスを提供しています。") and not page_is_useful("日本語です")


def test_a_completely_empty_page_is_an_empty_website_but_a_few_words_need_review():  # CR-B03
    assert assess("<html><head></head><body></body></html>").kind == "under_construction"
    assert assess("<html><head><title>Hi</title></head><body><p>Hi there</p></body></html>").kind == "thin"
    assert assess("<html><body><div id='root'></div><script src='/a.js'></script></body></html>").kind == "js_shell"


def test_a_short_but_real_one_page_site_is_ok():
    html = "<html><head><title>Joe's Plumbing</title></head><body><h1>Joe's Plumbing</h1><p>Emergency plumbing in Leeds, open 24 hours a day, every day of the year. Call us today.</p></body></html>"
    assert assess(html).kind == "ok"


def test_useful_text_is_ok_and_threshold_is_configurable(monkeypatch):
    from app.crawler import config

    html = "<html><head><title>Acme</title></head><body><p>" + "Acme builds warehouse robots for factories worldwide. " * 3 + "</p></body></html>"
    assert assess(html).kind == "ok"
    monkeypatch.setattr(config, "MIN_USEFUL_PAGE_CHARS", 10_000)
    assert assess(html).kind in ("thin", "js_shell")


def test_old_helpers_still_behave():
    shell = b"<html><body><script>app()</script><noscript>enable javascript</noscript></body></html>"
    assert looks_like_shell("", shell) is True
    prose = "ACME builds warehouse robots for factories across forty countries and runs support hubs."
    assert page_is_useful(prose) is True
    assert looks_like_shell(prose, b"<html><script></script><p>" + prose.encode() + b"</p></html>") is False
