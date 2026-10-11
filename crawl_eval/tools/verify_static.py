"""Verify public-test-endpoint rows (httpbin, badssl, public IP literals) with one real request each.

Writes C:/crawl_eval_data/scratch/statics_verified.json  {url: {...facts...}}
"""
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe  # noqa: E402
import static_rows  # noqa: E402

OUT = Path("C:/crawl_eval_data/scratch/statics_verified.json")


async def one(client, url):
    res = await probe.fetch(client, url, max_hops=15)
    rec = {k: v for k, v in res.items() if k not in ("body",)}
    body = res.get("body", b"")
    rec["body_len"] = len(body)
    rec["body_sample"] = body[:80].decode("utf-8", errors="replace")
    rec["verified_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return url, rec


async def main():
    urls = [r["url"] for r in static_rows.rows if r["source_type"] in ("public-test-endpoint", "real") and r["url"].startswith("http")
            and ("httpbin.org" in r["url"] or r["url"].startswith(("http://1.1.1.1", "http://[2606")))]
    urls += [f"https://{h}.badssl.com/" for h, _ in static_rows.BADSSL]
    urls += ["https://example.com/", "https://example.org/", "http://example.net/", "https://httpbin.org/robots.txt"]
    urls = list(dict.fromkeys(urls))
    print(len(urls), "urls", flush=True)
    results = {}
    sem = asyncio.Semaphore(4)
    async with httpx.AsyncClient(timeout=httpx.Timeout(45, connect=10)) as client:
        async def run(u):
            async with sem:
                return await one(client, u)
        for coro in asyncio.as_completed([asyncio.create_task(run(u)) for u in urls]):
            u, rec = await coro
            results[u] = rec
    OUT.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    for u in urls:
        r = results[u]
        print(str(r.get("status", r.get("error_kind"))).ljust(10), str(r.get("elapsed_ms")).rjust(6), u[:90], "|", (r.get("error") or "")[:70])


asyncio.run(main())
