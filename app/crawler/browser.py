"""Render a page only when HTTP returned a JavaScript shell (CR-D05, D06, D07, B10).

Playwright is imported lazily. If it is not installed, or the browser fails, the caller keeps the HTTP result and continues.

How the browser is kept inside the rules (ISS-01, ISS-06):
- Chromium has NO network of its own. It is started with a dead proxy, and every request it makes (page, redirect hop, script, XHR) is
  intercepted: the URL goes through the SSRF guard, is fetched by our guarded httpx client, and the answer is handed back with route.fulfill.
  A JavaScript redirect to 127.0.0.2 therefore ends in a refused request, never in a stored page.
- documents obey the same per-domain gate and politeness as plain HTTP; sub-resources of the page being rendered use a small shared limit
- images, media, fonts, style sheets and ad/analytics hosts are not loaded; the number of requests and bytes per render is capped
- the page is read when its text stops changing (up to BROWSER_SETTLE seconds), not right after DOMContentLoaded
- one Chromium per event loop is reused; each page gets a fresh context (no cookies, no service workers)
"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse

import httpx

from app.crawler import config, politeness
from app.crawler.client import new_client
from app.crawler.fetcher import record_attempt
from app.crawler.guard import GuardError, assert_public_url

_SKIPPED_TYPES = {"image", "media", "font", "stylesheet", "texttrack", "manifest", "other", "ping", "eventsource", "websocket"}
_BLOCKED_HOST_HINTS = (
    "googletagmanager.", "google-analytics.", "doubleclick.", "googlesyndication.", "googleadservices.", "facebook.net", "connect.facebook",
    "hotjar.", "clarity.ms", "segment.io", "segment.com", "mixpanel.", "adservice.", "adsystem.", "criteo.", "taboola.", "outbrain.",
    "snap.licdn.com", "px.ads.linkedin", "tiktok.com/i18n", "intercom.io", "drift.com", "hubspot.com/__", "newrelic.", "sentry.io",
)
_DROP_RESPONSE_HEADERS = {"content-encoding", "content-length", "transfer-encoding", "connection", "keep-alive", "set-cookie", "set-cookie2",
                          "strict-transport-security", "content-security-policy", "content-security-policy-report-only"}
_PASS_REQUEST_HEADERS = {"accept", "accept-language", "content-type", "origin", "referer", "x-requested-with"}
_LAUNCH_ARGS = [
    "--proxy-server=http://127.0.0.1:9",            # dead proxy: anything not intercepted fails (fail-closed)
    "--disable-background-networking", "--disable-component-update", "--disable-sync", "--no-first-run", "--disable-default-apps",
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp", "--disable-dev-shm-usage", "--mute-audio",
]


class RenderedHtml(bytes):
    """Rendered HTML plus facts about the render. Behaves like bytes everywhere."""

    final_url: str = ""
    blocked: list
    requests: int = 0

    def __new__(cls, data: bytes, final_url: str = "", blocked: list | None = None, requests: int = 0):
        obj = super().__new__(cls, data)
        obj.final_url = final_url
        obj.blocked = blocked or []
        obj.requests = requests
        return obj


class _Pool:
    def __init__(self) -> None:
        self.playwright = None
        self.browser = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.semaphore: asyncio.Semaphore | None = None
        self.sub_limit: asyncio.Semaphore | None = None


_POOL = _Pool()


async def shutdown_browser() -> None:
    """Close the shared Chromium (called at the end of a crawl run). Safe to call when nothing is open."""
    pool = _POOL
    browser, playwright, loop = pool.browser, pool.playwright, pool.loop
    pool.browser = pool.playwright = pool.loop = pool.semaphore = pool.sub_limit = None
    if loop is not asyncio.get_running_loop():
        return  # belongs to a loop that is gone: nothing we can close from here
    try:
        if browser is not None:
            await browser.close()
    except Exception:  # noqa: BLE001 - shutting down
        pass
    try:
        if playwright is not None:
            await playwright.stop()
    except Exception:  # noqa: BLE001
        pass


async def _get_browser():
    loop = asyncio.get_running_loop()
    if _POOL.browser is not None and _POOL.loop is loop:
        try:
            if _POOL.browser.is_connected():
                return _POOL.browser
        except Exception:  # noqa: BLE001
            pass
    _POOL.browser = _POOL.playwright = None
    from playwright.async_api import async_playwright

    _POOL.playwright = await async_playwright().start()
    _POOL.browser = await _POOL.playwright.chromium.launch(headless=True, args=_LAUNCH_ARGS)
    _POOL.loop = loop
    _POOL.semaphore = asyncio.Semaphore(2)
    _POOL.sub_limit = asyncio.Semaphore(6)
    return _POOL.browser


async def _upstream(client: httpx.AsyncClient, request, state: dict, document: bool):
    """Fetch what the page asked for through our guarded client. Redirects are NOT followed: Chromium follows them and we check each hop."""
    headers = {k: v for k, v in request.headers.items() if k.lower() in _PASS_REQUEST_HEADERS}
    headers["User-Agent"] = config.user_agent()
    body = request.post_data_buffer if request.method not in ("GET", "HEAD") else None
    url = request.url
    gate = politeness.get_gate()

    async def go():
        async with asyncio.timeout(config.PAGE_TIMEOUT + 8):
            async with client.stream(request.method, url, headers=headers, content=body, follow_redirects=False, timeout=config.PAGE_TIMEOUT) as response:
                chunks, total = [], 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > config.MAX_BYTES_PER_PAGE or state["bytes"] + total > config.BROWSER_MAX_BYTES:
                        raise FetchTooLarge()
                    chunks.append(chunk)
                return response.status_code, response.headers, b"".join(chunks)

    if document:
        async with gate.slot(url):
            return await go()
    async with _POOL.sub_limit:
        return await go()


class FetchTooLarge(Exception):
    pass


async def _settle(page) -> None:
    """Wait until the visible text stops changing (single-page apps fill the page after DOMContentLoaded)."""
    deadline = time.monotonic() + config.BROWSER_SETTLE
    last, stable = -1, 0
    while time.monotonic() < deadline:
        try:
            size = await page.evaluate("() => (document.body ? document.body.innerText.length : 0)")
        except Exception:  # noqa: BLE001 - navigation in progress
            size = -2
        if size == last and size > 0:
            stable += 1
            if stable >= 2:
                return
        else:
            stable = 0
        last = size
        await asyncio.sleep(0.5)


async def _render(url: str) -> RenderedHtml:
    browser = await _get_browser()
    context = await browser.new_context(service_workers="block", accept_downloads=False, user_agent=config.user_agent(), ignore_https_errors=False)
    state = {"requests": 0, "bytes": 0, "blocked": []}
    try:
        page = await context.new_page()
        async with new_client() as client:

            async def handler(route):
                request = route.request
                target = request.url
                parsed = urlparse(target)
                if parsed.scheme not in ("http", "https"):
                    await route.abort()
                    return
                if request.resource_type in _SKIPPED_TYPES or any(h in target for h in _BLOCKED_HOST_HINTS):
                    await route.abort()
                    return
                state["requests"] += 1
                if state["requests"] > config.BROWSER_MAX_REQUESTS or state["bytes"] > config.BROWSER_MAX_BYTES:
                    await route.abort()
                    return
                try:
                    await asyncio.to_thread(assert_public_url, target)  # module-level name: replaceable by tests and the harness
                except GuardError as exc:
                    state["blocked"].append(f"{target} ({exc})")
                    record_attempt(url=target, method="browser", error_kind="guard", note=f"browser request refused: {exc}"[:300])
                    await route.abort()
                    return
                try:
                    status, response_headers, body = await _upstream(client, request, state, request.resource_type == "document")
                except Exception as exc:  # noqa: BLE001 - one failed sub-request must not fail the render
                    record_attempt(url=target, method="browser", error_kind=type(exc).__name__, note=str(exc)[:200])
                    await route.abort()
                    return
                state["bytes"] += len(body)
                headers = {k: v for k, v in response_headers.items() if k.lower() not in _DROP_RESPONSE_HEADERS}
                await route.fulfill(status=status, headers=headers, body=body)

            await page.route("**/*", handler)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=int(config.BROWSER_TIMEOUT * 1000))
            except Exception as exc:  # noqa: BLE001 - a slow page may still have rendered text we can use
                record_attempt(url=url, method="browser", error_kind=type(exc).__name__, note=f"goto: {str(exc)[:160]}")
            await _settle(page)
            html = await page.content()
            final_url = page.url
        return RenderedHtml(html.encode("utf-8"), final_url, state["blocked"], state["requests"])
    finally:
        try:
            await context.close()
        except Exception:  # noqa: BLE001
            pass


async def render_page(url: str) -> bytes | None:
    """Return rendered HTML (a RenderedHtml, which is bytes), or None when the browser cannot be used."""
    try:
        import playwright.async_api  # noqa: F401
    except ImportError:
        return None
    try:
        await asyncio.to_thread(assert_public_url, url)
    except GuardError:
        return None

    started = time.perf_counter()
    try:
        browser = await _get_browser()  # noqa: F841 - creates the pool and its semaphore
        async with _POOL.semaphore:
            result = await asyncio.wait_for(_render(url), timeout=config.BROWSER_TIMEOUT + config.BROWSER_SETTLE + 30)
        record_attempt(url=url, method="browser", ms=int((time.perf_counter() - started) * 1000), bytes=len(result),
                       note=f"rendered; {result.requests} requests, {len(result.blocked)} refused")
        return result
    except Exception as exc:  # noqa: BLE001 - the caller keeps the HTTP result
        record_attempt(url=url, method="browser", ms=int((time.perf_counter() - started) * 1000), error_kind=type(exc).__name__, note=str(exc)[:200])
        return None
