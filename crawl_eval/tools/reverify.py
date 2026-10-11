"""Second independent probe of volatile rows (dead, timeout, TLS, HTTP error, bot, robots...). A row is kept only if the
second probe agrees with the first (same outcome class). Output: C:/crawl_eval_data/scratch/reverify.jsonl
    python reverify.py            (reads reverify_hosts.json)
"""
import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe  # noqa: E402

S = Path("C:/crawl_eval_data/scratch")


async def main():
    hosts = json.loads((S / "reverify_hosts.json").read_text(encoding="utf-8"))
    first = {}
    for f in (S / "probe").glob("*.jsonl"):
        for line in f.read_text(encoding="utf-8").split("\n"):
            try:
                r = json.loads(line)
                first[r["host"]] = r
            except Exception:
                pass
    out = S / "reverify.jsonl"
    done = set()
    if out.exists():
        done = {json.loads(l)["host"] for l in out.read_text(encoding="utf-8").split("\n") if l.strip()}
    todo = [first[h] for h in hosts if h in first and h not in done]
    print(len(todo), "to re-verify", flush=True)
    sem = asyncio.Semaphore(6)
    no_limit = asyncio.Semaphore(10**6)
    async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=10), limits=httpx.Limits(max_connections=30, max_keepalive_connections=0)) as client:
        async def one(r):
            row = {"url": r["input_url"], "qid": r.get("qid", ""), "label": r.get("label", ""), "country": r.get("country", ""), "pool": r.get("pool", ""), "class": r.get("class", "")}
            async with sem:
                try:
                    return await asyncio.wait_for(probe.probe_one(client, no_limit, row), timeout=120)
                except Exception as exc:
                    return {"host": r["host"], "outcome": f"probe_error:{type(exc).__name__}"}
        with out.open("a", encoding="utf-8") as fh:
            for n, coro in enumerate(asyncio.as_completed([asyncio.create_task(one(r)) for r in todo]), 1):
                rec = await coro
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                if n % 50 == 0:
                    print(f"  {n}/{len(todo)}", flush=True)


asyncio.run(main())
