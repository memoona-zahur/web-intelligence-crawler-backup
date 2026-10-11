"""One crawl-worker PROCESS for the local scale test (plan GATE 4 / user addition 2). Started by scale_test.py; not meant to be run by hand.

It is the real worker (app.crawler.runner.run_worker): real queue, real database, real pipeline, real persistence. Only the NETWORK is replaced by an
in-memory fake of 1,000 company sites (httpx.MockTransport), and the DNS check is switched off, because the test measures queue / database / CPU
behaviour, not the internet. Politeness spacing is shortened for the same reason (DOMAIN_DELAY); the spacing logic itself is unit-tested.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "crawl_eval"))
sys.dont_write_bytecode = True
os.environ.setdefault("CRAWLER_MODE", "test")
os.environ["OBSERVE_ECHO"] = "0"

import httpx  # noqa: E402

from app.crawler import client as client_module  # noqa: E402
from app.crawler import config, fetcher, runner  # noqa: E402
from tests.sitekit import prose  # noqa: E402


def site_number(host: str) -> int:
    return int(hashlib.sha256(host.encode()).hexdigest()[:8], 16)


def page_html(host: str, title: str, nav: bool = False, sentences: int = 10) -> bytes:
    links = '<nav><a href="/about">About us</a><a href="/services">Our services</a><a href="/products">Products</a><a href="/industries">Industries</a></nav>' if nav else ""
    return f"<html><head><title>{host} {title}</title></head><body>{links}<h1>{title}</h1>{prose(host + title, sentences)}</body></html>".encode()


async def handler(request: httpx.Request) -> httpx.Response:
    host, path = request.url.host, request.url.path
    n = site_number(host) % 100
    await asyncio.sleep(0.02 + (site_number(host + path) % 120) / 1000)        # 20-140 ms "network" latency
    if n == 3:
        raise httpx.ConnectError("connection refused", request=request)         # unreachable site
    if path == "/robots.txt":
        return httpx.Response(503 if n == 5 else 404, request=request)
    if n in (0, 1, 2) and path == "/":
        return httpx.Response(503, request=request)                              # failing site
    if n == 4 and path == "/":
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html><head><title>x</title></head><body><h1>This domain is for sale</h1><p>Make an offer on this domain.</p></body></html>", request=request)
    if n == 6 and path == "/":
        return httpx.Response(302, headers={"location": f"https://moved-{host}.example.net/"}, request=request)
    if n in (7, 8) and path == "/services":
        return httpx.Response(500, request=request)                              # one page fails: partial crawl
    if path in ("/", "/about", "/services", "/products", "/industries"):
        return httpx.Response(200, headers={"content-type": "text/html"}, content=page_html(host, path.strip("/") or "home", nav=(path == "/")), request=request)
    return httpx.Response(404, request=request)


def main() -> None:
    concurrency = int(sys.argv[1])
    out = Path(sys.argv[2])
    config.DOMAIN_DELAY = float(os.environ.get("SCALE_DOMAIN_DELAY", "0.05"))
    config.RETRY_BACKOFF = 0.05
    fetcher.assert_public_url = lambda url: url                                  # no DNS in the scale test
    runner.new_client = lambda **kw: client_module.new_client(transport=httpx.MockTransport(handler))

    from telemetry import rss_mb  # frozen harness helper, read-only use

    peak = {"mb": 0.0}
    stop = threading.Event()

    def sample():
        while not stop.is_set():
            peak["mb"] = max(peak["mb"], rss_mb())
            time.sleep(0.25)

    threading.Thread(target=sample, daemon=True).start()
    started = time.monotonic()
    summary = asyncio.run(runner.run_worker(concurrency=concurrency, enqueue_pending=False, log=lambda *_a: None))
    stop.set()
    out.write_text(json.dumps({"pid": os.getpid(), "concurrency": concurrency, "seconds": round(time.monotonic() - started, 2), "counts": summary.counts,
                               "peak_rss_mb": round(peak["mb"], 1)}), encoding="utf-8")


if __name__ == "__main__":
    main()
