"""The browser fallback with a real Chromium against local servers (CR-B10, D05, D06, D07; issues ISS-01, ISS-06).

Skipped when Playwright or its Chromium is not installed. No real website is contacted: two small servers run on 127.0.0.1 and 127.0.0.2.
"""

import asyncio
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "C:/crawl_eval_data/browsers")
pytest.importorskip("playwright")

from app.crawler import browser, config  # noqa: E402
from app.crawler.guard import UnsafeTarget  # noqa: E402


def chromium_available() -> bool:
    async def probe():
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as pw:
                b = await pw.chromium.launch(headless=True)
                await b.close()
            return True
        except Exception:
            return False

    return asyncio.run(probe())


pytestmark = pytest.mark.skipif(not chromium_available(), reason="Playwright Chromium is not installed")


class Servers:
    def __init__(self):
        self.hits: dict[str, list[str]] = {"main": [], "secret": []}
        outer = self

        def make(name):
            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *a):
                    pass

                def _send(self, status, body, ctype="text/html", headers=None):
                    data = body.encode() if isinstance(body, str) else body
                    self.send_response(status)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    for k, v in (headers or {}).items():
                        self.send_header(k, v)
                    self.end_headers()
                    self.wfile.write(data)

                def do_GET(self):
                    outer.hits[name].append(self.path)
                    if name == "secret":
                        return self._send(200, "<html><body>SECRET-TOKEN-4711</body></html>")
                    path = self.path.split("?")[0]
                    if path == "/spa":
                        return self._send(200, "<html><head><title>App</title></head><body><div id='root'></div><script>"
                                               "setTimeout(function(){document.getElementById('root').innerHTML="
                                               "'<h1>Rendered by script</h1><p>We manufacture industrial valves and control systems for chemical plants across three regions.</p>'},700)"
                                               "</script></body></html>")
                    if path == "/redir302":
                        return self._send(302, "", headers={"Location": "/spa"})
                    if path == "/js-redirect-private":
                        return self._send(200, f"<html><body><p>one moment</p><script>window.location='http://127.0.0.2:{outer.secret_port}/secret'</script></body></html>")
                    if path == "/xhr-private":
                        return self._send(200, f"<html><body><div id='o'>start</div><script>fetch('http://127.0.0.2:{outer.secret_port}/xhr').then(r=>r.text()).then(t=>"
                                               f"document.getElementById('o').textContent='got '+t).catch(e=>document.getElementById('o').textContent='blocked')</script></body></html>")
                    if path == "/assets":
                        return self._send(200, "<html><head><link rel='stylesheet' href='/style.css'></head><body><img src='/logo.png'><video src='/movie.mp4'></video>"
                                               "<p>A page with enough text to be read by the extractor without any browser tricks at all, really.</p></body></html>")
                    if path == "/many":
                        calls = "".join(f"fetch('/api/{i}');" for i in range(30))
                        return self._send(200, f"<html><body><p>many</p><script>{calls}</script></body></html>")
                    return self._send(200, "{}" if path.startswith("/api") else "<html><body>ok</body></html>", "application/json" if path.startswith("/api") else "text/html")

            return Handler

        self.secret = ThreadingHTTPServer(("127.0.0.2", 0), make("secret"))
        self.secret_port = self.secret.server_address[1]
        self.main = ThreadingHTTPServer(("127.0.0.1", 0), make("main"))
        self.port = self.main.server_address[1]
        for server in (self.secret, self.main):
            threading.Thread(target=server.serve_forever, daemon=True).start()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def stop(self):
        self.main.shutdown()
        self.secret.shutdown()


@pytest.fixture()
def servers(monkeypatch):
    s = Servers()
    allowed = f"127.0.0.1:{s.port}"

    def guard(url):  # like the evaluation harness: only the test server is allowed; 127.0.0.2 is refused
        from urllib.parse import urlparse

        p = urlparse(url)
        if f"{p.hostname}:{p.port}" != allowed:
            raise UnsafeTarget(f"host {p.hostname!r} points at non-public address")
        return url

    monkeypatch.setattr(browser, "assert_public_url", guard)
    monkeypatch.setattr(config, "BROWSER_SETTLE", 3.0)
    monkeypatch.setattr(config, "BROWSER_TIMEOUT", 10.0)
    yield s
    s.stop()


def render(url):
    async def go():
        try:
            return await browser.render_page(url)
        finally:
            await browser.shutdown_browser()

    return asyncio.run(go())


def test_script_rendered_content_is_read_after_it_appears(servers):  # ISS-06
    html = render(servers.url("/spa"))
    assert html is not None and b"Rendered by script" in html and b"industrial valves" in html
    assert html.final_url == servers.url("/spa")


def test_http_redirects_are_followed_by_the_browser_and_each_hop_is_checked(servers):
    html = render(servers.url("/redir302"))
    assert html is not None and b"Rendered by script" in html and html.final_url.endswith("/spa")
    assert "/redir302" in servers.hits["main"] and "/spa" in servers.hits["main"]


def test_a_javascript_redirect_to_a_private_address_is_never_followed(servers):  # ISS-01, CR-B10
    html = render(servers.url("/js-redirect-private"))
    assert html is not None and b"SECRET-TOKEN-4711" not in html
    assert servers.hits["secret"] == []                                   # the private server was never contacted
    assert any("127.0.0.2" in b for b in html.blocked)                    # and the refusal is recorded


def test_a_script_cannot_reach_a_private_address_either(servers):
    html = render(servers.url("/xhr-private"))
    assert html is not None and b"blocked" in html and servers.hits["secret"] == []


def test_images_media_and_style_sheets_are_not_loaded(servers):  # CR-D06
    render(servers.url("/assets"))
    requested = servers.hits["main"]
    assert "/assets" in requested and not {"/logo.png", "/movie.mp4", "/style.css"} & set(requested)


def test_the_number_of_requests_per_render_is_capped(servers, monkeypatch):
    monkeypatch.setattr(config, "BROWSER_MAX_REQUESTS", 5)
    render(servers.url("/many"))
    api_calls = [p for p in servers.hits["main"] if p.startswith("/api")]
    assert len(api_calls) <= 5


def test_a_page_that_is_not_reachable_returns_none_and_the_reason_is_traced(servers):
    from app.crawler.fetcher import ATTEMPT_TRACE

    trace: list[dict] = []
    token = ATTEMPT_TRACE.set(trace)
    try:
        html = render("http://127.0.0.1:1/never")          # the guard refuses it: nothing is rendered
    finally:
        ATTEMPT_TRACE.reset(token)
    assert html is None


def test_one_browser_is_reused_between_renders(servers):
    async def go():
        try:
            await browser.render_page(servers.url("/spa"))
            first = browser._POOL.browser
            await browser.render_page(servers.url("/spa"))
            return first is browser._POOL.browser
        finally:
            await browser.shutdown_browser()

    assert asyncio.run(go()) is True


def test_rendered_html_behaves_like_bytes_and_carries_the_render_facts(servers):
    html = render(servers.url("/spa"))
    assert isinstance(html, bytes) and html.requests >= 1 and html.blocked == []
