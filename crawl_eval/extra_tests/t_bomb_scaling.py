"""D09 / L-17 / 'does memory grow without bound?': crawl ONE decompression-bomb page in a fresh process and record peak memory with a 0.1 s sampler.
usage: t_bomb_scaling.py <port> <label>     (8805 = 150 MB expanded, 8862 = 600 MB expanded). A watchdog protects the laptop (soft 1.8 GB / hard 2.8 GB)."""
import asyncio
import sys

port, label = int(sys.argv[1]), sys.argv[2]
from common import save, setup

database, tel = setup(f"bomb_{label}")
import telemetry
from app.crawler import runner
from app.models import Website
from sqlalchemy import select

URL = f"http://127.0.0.1:{port}/"
stop = asyncio.Event() if False else None
wd = telemetry.Watchdog(soft_mb=1800, hard_mb=2800, free_soft_mb=1500, free_hard_mb=1000, record_path=f"C:/crawl_eval_data/scratch/bomb_{label}_watchdog_hard.json", on_soft=lambda: None, every=0.1)
wd.start()


async def main():
    with database.get_session() as s:
        s.add(Website(original_url=URL, normalized_website=URL, status="pending", source_batch="bomb"))
        s.commit()
        wid = s.scalar(select(Website.id))
    base = telemetry.rss_mb()
    t0 = wd.timeline[-1][0] if wd.timeline else 0
    import time
    t = time.monotonic()
    await runner.run(site_ids=[wid], concurrency=1, log=lambda m: None)
    secs = time.monotonic() - t
    await asyncio.sleep(1.0)
    peak = max([r for _t, r, _f in wd.timeline] or [0])
    with database.get_session() as s:
        w = s.get(Website, wid)
        res = {"label": label, "scenario_port": port, "expanded_size_mb": {"8805": 150, "8862": 600}.get(str(port)), "status": w.status, "crawl_error": w.crawl_error,
               "seconds": round(secs, 1), "rss_before_mb": round(base, 1), "rss_peak_mb": round(peak, 1), "peak_increase_mb": round(peak - base, 1),
               "rss_after_run_mb": round(telemetry.rss_mb(), 1), "sampler_samples": len(wd.timeline),
               "watchdog_soft_limit_hit": wd.soft_hit}
    wd.stop()
    save(f"t_bomb_{label}", res)

asyncio.run(main())
