"""G01/G02/G08 / L-20: how does the unchanged runner behave with 100 and then 1,000 sites in ONE run() call?
All sites are local (scenario 8855 answers 200 for any path), so no real website is touched. Measures only this crawler on this laptop."""
import asyncio
import time
from collections import Counter

from common import save, setup

database, tel = setup("scale")
import telemetry
from app.crawler import runner
from app.models import Website
from sqlalchemy import select

CONC = 5


def add_sites(start, n):
    with database.get_session() as s:
        for i in range(start, start + n):
            u = f"http://127.0.0.1:8855/s{i}"
            s.add(Website(original_url=u, normalized_website=u, status="pending", source_batch="scale-test"))
        s.commit()
        return [w.id for w in s.scalars(select(Website).where(Website.source_batch == "scale-test").where(Website.normalized_website.like(f"http://127.0.0.1:8855/s%")))]


async def one_run(n, start):
    with database.get_session() as s:
        before = {w.id for w in s.scalars(select(Website))}
    add_sites(start, n)
    with database.get_session() as s:
        ids = [w.id for w in s.scalars(select(Website)) if w.id not in before]
    snap = {}

    async def watch():
        await asyncio.sleep(1.0)
        snap["asyncio_tasks_1s_after_start"] = len(asyncio.all_tasks())
        snap["rows_in_crawling_state_1s_after_start"] = None
        with database.get_session() as s:
            snap["rows_in_crawling_state_1s_after_start"] = sum(1 for w in s.scalars(select(Website).where(Website.id.in_(ids))) if w.status == "crawling")

    r0 = telemetry.rss_mb()
    t = time.monotonic()
    t_rel = t - tel.t0
    w = asyncio.create_task(watch())
    summary = await runner.run(site_ids=ids, concurrency=CONC, log=lambda m: None)
    secs = time.monotonic() - t
    await w
    peak = tel.peak_between(t_rel, t_rel + secs + 1)
    reqs = [q for q in tel.requests if q.get("site", "") and f"/s" in (q.get("site") or "") and q["t"] >= t_rel]
    return {"sites": n, "concurrency": CONC, "seconds": round(secs, 1), "sites_per_hour_this_test_only": round(n / secs * 3600), "statuses": dict(summary.counts),
            "http_requests": len(reqs), "rss_before_mb": round(r0, 1), "rss_peak_mb": round(peak, 1), **snap}


async def main():
    res = {"what": "single runner.run() call per size; local scenario server; concurrency 5 (the harness value; the code's own default is 10)"}
    res["run_100"] = await one_run(100, 1)
    res["run_1000"] = await one_run(1000, 101)
    save("t_scale_local", res)

asyncio.run(main())
