"""Pass-through wrappers that WATCH the unchanged crawler. Nothing under app/ is edited: functions are wrapped in memory only.

Every wrapper returns exactly what the original returns and re-raises exactly what it raises (same inputs, same outputs, same exceptions).
Two deliberate exceptions, both listed in run_manifest.json and in the report:
  1. guard allow-list: for the scenario server's own host:port only, assert_public_url is skipped (the crawler correctly refuses loopback).
  2. safety net: a request that the crawler's guard FAILED to stop, aimed at a non-global address, is NOT sent; it is recorded as
     SAFETY_NET_BLOCKED (= guard failure evidence) and raises httpx.ConnectError. This protects other people's networks and ours.
"""
from __future__ import annotations

import asyncio
import contextvars
import ctypes
import ctypes.wintypes as wt
import ipaddress
import socket
import threading
import time
from datetime import datetime, timezone

import httpx

CURRENT_SITE: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_site", default=None)
WRAPPERS = [
    "httpx.AsyncClient.send (request log, UA, timing, safety net)",
    "app.crawler.fetcher._one_attempt (attempt/retry log)",
    "app.crawler.fetcher.assert_public_url + app.crawler.browser.assert_public_url (guard log; scenario host:port allow-list)",
    "app.crawler.pipeline.load_robots (robots decision)",
    "app.crawler.pipeline.render_page + app.crawler.browser.render_page (browser use)",
    "app.crawler.pipeline.crawl_one + app.crawler.runner.crawl_one (per-site timing and result)",
    "app.crawler.runner._save (DB write time)",
    "app.importer.extract_urls / normalize_website / is_safe_import_target (import decisions)",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class _PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def rss_mb() -> float:
    """Working set of THIS process in MB (child processes such as Chromium are not included)."""
    k32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
    k32.GetCurrentProcess.restype = wt.HANDLE  # 64-bit handle: the default int return type truncates it
    psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(_PMC), wt.DWORD]
    psapi.GetProcessMemoryInfo.restype = wt.BOOL
    pmc = _PMC()
    pmc.cb = ctypes.sizeof(_PMC)
    if not psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
        return 0.0
    return pmc.WorkingSetSize / 1048576


class _MEMSTATUS(ctypes.Structure):
    _fields_ = [("dwLength", wt.DWORD), ("dwMemoryLoad", wt.DWORD), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong), ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]


def free_phys_mb() -> float:
    """Free physical memory of the whole machine in MB."""
    st = _MEMSTATUS()
    st.dwLength = ctypes.sizeof(_MEMSTATUS)
    ctypes.WinDLL("kernel32").GlobalMemoryStatusEx(ctypes.byref(st))
    return st.ullAvailPhys / 1048576


class Watchdog:
    """Keeps the laptop safe. SOFT limit: ask the harness to cancel the run (recorded as a finding if the crawler caused it).
    HARD limit: write the evidence and kill this process at once (a blocking decompression cannot be cancelled)."""

    def __init__(self, soft_mb, hard_mb, free_soft_mb, free_hard_mb, record_path, on_soft, every=0.5):
        self.soft_mb, self.hard_mb, self.free_soft_mb, self.free_hard_mb = soft_mb, hard_mb, free_soft_mb, free_hard_mb
        self.record_path, self.on_soft, self.every = record_path, on_soft, every
        self.timeline: list[tuple[float, float, float]] = []  # (t, process_rss_mb, machine_free_mb)
        self.soft_hit = None
        self._stop = threading.Event()
        self.t0 = time.monotonic()
        self.context = {"stage": "", "row": ""}

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop.set()

    def peak_between(self, a, b):
        v = [r for t, r, _f in self.timeline if a <= t <= b]
        return max(v) if v else 0.0

    def _loop(self):
        import json
        import os
        while not self._stop.is_set():
            t, rss, free = time.monotonic() - self.t0, rss_mb(), free_phys_mb()
            self.timeline.append((round(t, 2), round(rss, 1), round(free, 1)))
            if rss > self.hard_mb or free < self.free_hard_mb:
                with open(self.record_path, "w", encoding="utf-8") as f:
                    json.dump({"event": "HARD LIMIT: process killed by watchdog", "rss_mb": rss, "machine_free_mb": free, "context": self.context,
                               "limits": {"hard_mb": self.hard_mb, "free_hard_mb": self.free_hard_mb}, "timeline_tail": self.timeline[-60:]}, f, indent=1)
                os._exit(86)
            if (rss > self.soft_mb or free < self.free_soft_mb) and self.soft_hit is None:
                self.soft_hit = {"event": "SOFT LIMIT: run cancelled by watchdog", "t": round(t, 2), "rss_mb": round(rss, 1), "machine_free_mb": round(free, 1),
                                 "context": dict(self.context), "limits": {"soft_mb": self.soft_mb, "free_soft_mb": self.free_soft_mb}}
                self.on_soft()
            self._stop.wait(self.every)


def diagnose_html(html: bytes, url: str = "") -> dict:
    """READ-ONLY diagnosis of the crawler's extraction rules on one page: which rule removed how many characters.
    Uses the crawler's own constants and its own extract_page for the final number; the attribution is done step by step in the crawler's order."""
    import re
    from bs4 import BeautifulSoup
    import app.crawler.extract as ex

    def chars(soup) -> int:
        return len(re.sub(r"\s+", " ", soup.get_text(" ", strip=True)))

    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "template", "svg", "canvas"]):
        t.decompose()
    visible = chars(soup)
    removed: dict[str, int] = {}
    for tag in ex.DROP_TAGS:
        if tag in ("script", "style", "noscript", "svg", "canvas", "template"):
            continue
        before = chars(soup)
        for node in soup.find_all(tag):
            node.decompose()
        lost = before - chars(soup)
        if lost > 0:
            removed[f"<{tag}>"] = lost
    to_drop = []
    for node in soup.find_all(True):
        if getattr(node, "attrs", None) is None:
            continue
        cls = node.get("class")
        names = " ".join(([cls] if isinstance(cls, str) else list(cls or [])) + [str(node.get("id") or "")]).lower()
        hit = next((h for h in ex.DROP_NAME_HINTS if h in names), None)
        if hit:
            to_drop.append((hit, node))
    for hit, node in to_drop:
        if getattr(node, "attrs", None) is None:
            continue
        before = chars(soup)
        node.decompose()
        lost = before - chars(soup)
        if lost > 0:
            removed[f"class/id contains '{hit}'"] = removed.get(f"class/id contains '{hit}'", 0) + lost
    after_drops = chars(soup)
    kept_lines = set()
    kept = 0
    for node in soup.select(ex.KEEP_SELECTOR):
        line = re.sub(r"\s+", " ", node.get_text(" ", strip=True))
        if len(line) >= 3 and line.lower() not in kept_lines:
            kept_lines.add(line.lower())
            kept += len(line)
    try:
        extracted = len(ex.extract_page(html, url)[1])
    except Exception:
        extracted = -1
    return {"html_bytes": len(html), "visible_text_chars": visible, "lost_by_drop_rules": removed, "text_left_after_drop_rules": after_drops,
            "kept_by_selector_h1_h2_h3_p_li_dd": kept, "lost_by_selector_rule": max(0, after_drops - kept), "extracted_chars_by_crawler": extracted}


class Telemetry:
    def __init__(self, scenario_ports: set[int]):
        self.last_body: dict[str, bytes] = {}
        self.scenario_ports = scenario_ports
        self.requests: list[dict] = []
        self.attempts: list[dict] = []
        self.guard: list[dict] = []
        self.robots: list[dict] = []
        self.browser: list[dict] = []
        self.sites: list[dict] = []
        self.saves: list[dict] = []
        self.import_log: dict = {"raws": [], "decisions": []}
        self.mem: list[tuple[float, float]] = []
        self._stop = threading.Event()
        self.t0 = time.monotonic()

    # ---- memory sampler (own thread) ----
    def start_memory(self, every: float = 2.0):
        def loop():
            while not self._stop.is_set():
                self.mem.append((time.monotonic() - self.t0, rss_mb()))
                self._stop.wait(every)
        threading.Thread(target=loop, daemon=True).start()

    def stop_memory(self):
        self._stop.set()

    def peak_between(self, a: float, b: float) -> float:
        vals = [m for t, m in self.mem if a <= t <= b]
        return max(vals) if vals else 0.0

    def allowed_scenario(self, host: str | None, port: int | None) -> bool:
        return host == "127.0.0.1" and port in self.scenario_ports


def _port(url: httpx.URL) -> int | None:
    return url.port or (443 if url.scheme == "https" else 80)


def install(tel: Telemetry) -> None:
    import app.crawler.browser as browser
    import app.crawler.fetcher as fetcher
    import app.crawler.pipeline as pipeline
    import app.crawler.runner as runner
    import app.importer as importer

    # ---------------- httpx transport-level log + safety net ----------------
    orig_send = httpx.AsyncClient.send

    async def send(self, request, *args, **kwargs):
        site = CURRENT_SITE.get()
        host, port = request.url.host, _port(request.url)
        rec = {"t": round(time.monotonic() - tel.t0, 3), "ts": now_iso(), "site": site, "method": request.method, "url": str(request.url),
               "ua": request.headers.get("user-agent", ""), "origin": "crawler" if site else "harness"}
        if site and not tel.allowed_scenario(host, port):
            blocked = None
            try:
                ips = {ipaddress.ip_address(host)} if _is_ip(host) else {ipaddress.ip_address(i[4][0].split("%")[0]) for i in
                                                                       await asyncio.get_running_loop().run_in_executor(None, socket.getaddrinfo, host, None)}
                blocked = next((str(ip) for ip in ips if not ip.is_global), None)
            except (socket.gaierror, ValueError):
                blocked = None
            if blocked:
                rec.update(safety_net_blocked=True, blocked_ip=blocked)
                tel.requests.append(rec)
                raise httpx.ConnectError(f"harness safety net: {host} resolves to non-global address {blocked}; request not sent")
        start = time.monotonic()
        try:
            resp = await orig_send(self, request, *args, **kwargs)
        except BaseException as exc:
            rec.update(error=type(exc).__name__, error_msg=str(exc)[:160], ms=int((time.monotonic() - start) * 1000))
            tel.requests.append(rec)
            raise
        try:
            size = len(resp.content)
        except Exception:
            size = None
        rec.update(status=resp.status_code, ms=int((time.monotonic() - start) * 1000), bytes=size, ctype=resp.headers.get("content-type", "")[:60],
                   retry_after=resp.headers.get("retry-after"), location=resp.headers.get("location"), t_end=round(time.monotonic() - tel.t0, 3))
        tel.requests.append(rec)
        return resp

    httpx.AsyncClient.send = send

    # ---------------- attempts (retries) ----------------
    orig_attempt = fetcher._one_attempt

    async def _one_attempt(client, url, expect_html):
        rec = {"t": round(time.monotonic() - tel.t0, 3), "site": CURRENT_SITE.get(), "url": url, "expect_html": expect_html}
        try:
            res = await orig_attempt(client, url, expect_html)
            rec.update(ok=True, status=res.status_code, final_url=res.final_url, bytes=len(res.content))
            if "html" in (res.content_type or "") and len(res.content) <= 2_000_000:  # kept in memory only, for browser-fallback diagnosis
                tel.last_body[res.final_url] = res.content
                while len(tel.last_body) > 40:
                    tel.last_body.pop(next(iter(tel.last_body)))
            return res
        except BaseException as exc:
            rec.update(ok=False, error=type(exc).__name__, kind=getattr(exc, "kind", None), detail=str(exc)[:200])
            raise
        finally:
            tel.attempts.append(rec)

    fetcher._one_attempt = _one_attempt

    # ---------------- guard (log + scenario allow-list) ----------------
    orig_assert = fetcher.assert_public_url

    def assert_public_url(url):
        p = httpx.URL(url)
        rec = {"t": round(time.monotonic() - tel.t0, 3), "site": CURRENT_SITE.get(), "url": url}
        if tel.allowed_scenario(p.host, _port(p)):
            rec.update(decision="allowed-scenario-host (guard relaxed by harness)")
            tel.guard.append(rec)
            return url
        try:
            out = orig_assert(url)
            rec.update(decision="allowed")
            return out
        except Exception as exc:
            rec.update(decision="refused", reason=str(exc)[:160])
            raise
        finally:
            tel.guard.append(rec)

    fetcher.assert_public_url = assert_public_url
    browser.assert_public_url = assert_public_url

    # ---------------- robots ----------------
    orig_robots = pipeline.load_robots

    async def load_robots(client, url, cache):
        cached = None
        try:
            from urllib.parse import urlparse, urlunparse
            u = urlparse(url)
            cached = urlunparse((u.scheme, u.netloc, "", "", "", "")) in cache
        except Exception:
            pass
        rules = await orig_robots(client, url, cache)
        tel.robots.append({"t": round(time.monotonic() - tel.t0, 3), "site": CURRENT_SITE.get(), "origin": rules.origin, "missing_or_failopen": rules.missing, "cache_hit": cached})
        return rules

    pipeline.load_robots = load_robots

    # ---------------- browser ----------------
    orig_render = browser.render_page

    async def render_page(url):
        start = time.monotonic()
        out = await orig_render(url)
        rec = {"t": round(start - tel.t0, 3), "site": CURRENT_SITE.get(), "url": url, "ms": int((time.monotonic() - start) * 1000),
               "returned_bytes": None if out is None else len(out)}
        try:  # diagnosis only (read-only): http page vs rendered page, and which crawler extraction rule removed the text
            http_html = tel.last_body.get(url)
            rec["http_page"] = diagnose_html(http_html, url) if http_html else None
            rec["rendered_page"] = diagnose_html(out, url) if out else None
            if rec["http_page"] and rec["rendered_page"]:
                rec["rendered_extracted_more_than_http"] = rec["rendered_page"]["extracted_chars_by_crawler"] > rec["http_page"]["extracted_chars_by_crawler"]
        except Exception as exc:  # a diagnosis bug must never change crawler behaviour
            rec["diag_error"] = f"{type(exc).__name__}: {exc}"[:160]
        tel.browser.append(rec)
        return out

    pipeline.render_page = render_page
    browser.render_page = render_page

    # ---------------- per-site ----------------
    orig_crawl_one = pipeline.crawl_one

    async def crawl_one(client, normalized_url, robots_cache):
        token = CURRENT_SITE.set(normalized_url)
        start = time.monotonic()
        rec = {"site": normalized_url, "start": round(start - tel.t0, 3), "start_ts": now_iso(), "rss_start_mb": round(rss_mb(), 1)}
        try:
            res = await orig_crawl_one(client, normalized_url, robots_cache)
            rec.update(status=res.status, error=res.error, pages=res.pages_crawled, final_url=res.final_url, latency_ms=res.latency_ms,
                       text_len=len(res.clean_text) if res.clean_text else 0)
            return res
        except BaseException as exc:
            rec.update(raised=type(exc).__name__, raised_msg=str(exc)[:200])
            raise
        finally:
            rec.update(end=round(time.monotonic() - tel.t0, 3), seconds=round(time.monotonic() - start, 2), rss_end_mb=round(rss_mb(), 1))
            rec["rss_peak_in_window_mb"] = round(tel.peak_between(rec["start"], rec["end"]), 1)
            tel.sites.append(rec)
            CURRENT_SITE.reset(token)

    pipeline.crawl_one = crawl_one
    runner.crawl_one = crawl_one

    orig_save = runner._save

    def _save(site_id, result):
        out = orig_save(site_id, result)
        tel.saves.append({"t": round(time.monotonic() - tel.t0, 3), "site_id": site_id, "status": result.status})
        return out

    runner._save = _save

    # ---------------- importer ----------------
    orig_extract, orig_norm, orig_safe = importer.extract_urls, importer.normalize_website, importer.is_safe_import_target

    def extract_urls(text):
        out = orig_extract(text)
        tel.import_log["raws"] = list(out)
        return out

    def normalize_website(raw):
        out = orig_norm(raw)
        tel.import_log["decisions"].append({"raw": raw, "normalized": out, "safe": None})
        return out

    def is_safe_import_target(url):
        out = orig_safe(url)
        if tel.import_log["decisions"]:
            tel.import_log["decisions"][-1]["safe"] = out
        return out

    importer.extract_urls, importer.normalize_website, importer.is_safe_import_target = extract_urls, normalize_website, is_safe_import_target


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False
