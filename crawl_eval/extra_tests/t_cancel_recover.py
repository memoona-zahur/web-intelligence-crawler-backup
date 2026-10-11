"""A13 / G02 / G09 / L-21: (a) cancel a running crawl, (b) kill the process mid-run and recover. Local scenario sites only (no real websites)."""
import asyncio
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from common import ROOT, save, setup

database, tel = setup("cancel_recover")
from app import recovery
from app.crawler import runner
from app.models import Job, Website
from sqlalchemy import select

HERE = Path(__file__).resolve().parent


def statuses(ids=None):
    with database.get_session() as s:
        return dict(Counter(w.status for w in s.scalars(select(Website)) if ids is None or w.id in ids))


def add(prefix_port, n, tag):
    ids = []
    with database.get_session() as s:
        for i in range(n):
            u = f"http://127.0.0.1:{prefix_port}/{tag}{i}"
            w = Website(original_url=u, normalized_website=u, status="pending", source_batch=tag)
            s.add(w)
        s.commit()
        ids = [w.id for w in s.scalars(select(Website).where(Website.source_batch == tag))]
    return ids


async def cancel_test():
    ids = add(8803, 30, "cancel")  # port 8803 answers only after 20 s: each site takes ~20 s
    task = asyncio.create_task(runner.run(site_ids=ids, concurrency=5, log=lambda m: None))
    await asyncio.sleep(5)
    with database.get_session() as s:
        job = s.scalar(select(Job).where(Job.kind == "crawl").order_by(Job.id.desc()))
        job.status = "cancelled"  # exactly what `python -m app.ops cancel --job N` does
        s.commit()
    t0 = time.monotonic()
    await task
    return {"cancelled_after_s": 5, "seconds_until_run_returned_after_cancel": round(time.monotonic() - t0, 1), "row_statuses_after": statuses(set(ids)),
            "note": "30 sites, 5 at a time, each site answers after 20 s; cancellation is only checked between completed sites"}


def crash_test():
    ids = add(8855, 400, "crash")
    p = subprocess.Popen([sys.executable, "-B", str(HERE / "crash_victim.py"), "cancel_recover"], cwd=str(HERE), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(4)
    p.kill()  # hard kill, like a power cut / Task Manager
    p.wait()
    after_kill = statuses(set(ids))
    # what the CLI does at start-up: init + recover_abandoned(); then crawl again
    rec = recovery.recover_abandoned()
    after_recover = statuses(set(ids))
    return ids, after_kill, rec, after_recover


async def main():
    out = {"what": "cancel and crash-recovery behaviour of the unchanged runner (local sites only)"}
    out["cancel"] = await cancel_test()
    ids, after_kill, rec, after_recover = crash_test()
    summ = await runner.run(site_ids=ids, concurrency=5, log=lambda m: None)
    out["crash_recovery"] = {"sites": len(ids), "after_kill_-9": after_kill, "recover_abandoned_result": rec, "after_recover": after_recover,
                             "second_run_counts": dict(summ.counts), "final_statuses": statuses(set(ids)),
                             "rows_lost": len(ids) - sum(statuses(set(ids)).values())}
    with database.get_session() as s:
        out["jobs"] = [(j.id, j.kind, j.status, j.note) for j in s.scalars(select(Job)) if j.kind == "crawl"]
    save("t_cancel_recover", out)

asyncio.run(main())
