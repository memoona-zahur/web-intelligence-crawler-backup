"""Pre-run check: fresh independent probe of a random sample of 40 dataset rows (30 real happy-path, 10 real error-path).
Does the fresh probe still agree with each row's expected_outcome?  Seed 20261011.  No use of app/ code.
Output: crawl_eval/dataset/oracle_agreement.csv and .md
"""
import asyncio
import csv
import random
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_dataset as B  # noqa: E402
import probe  # noqa: E402
import select_rows as SR  # noqa: E402

DS = Path(__file__).resolve().parents[1] / "dataset"
rows = list(csv.DictReader((DS / "testing_URLs.csv").open(encoding="utf-8-sig")))
rng = random.Random(20261011)
happy = [r for r in rows if r["category"] in B.HAPPY and r["source_type"] == "real"]
err = [r for r in rows if r["category"] in B.ERR and r["source_type"] == "real" and r["category"] not in ("Input handling",)]
sample = rng.sample(happy, 30) + rng.sample(err, 10)


def predict(rec: dict) -> tuple[str, str]:
    """What a person reading this fresh probe would call the site (independent of the crawler)."""
    o = rec["outcome"]
    d = rec.get("dns", {})
    if o == "dns_fail":
        return ("Unreachable", "dns") if d.get("rcode") == "NXDOMAIN" else ("?", "dns-unclear")
    if o == "robots_disallow":
        return "Blocked", "robots"
    if o.startswith("fetch_error"):
        return "Unreachable", rec["http"].get("error_kind", "")
    h, st = rec.get("html") or {}, (rec.get("http") or {}).get("status")
    ns = " ".join(d.get("ns", []))
    title = (h.get("title") or "").lower()
    if st == 200:
        if any(p in ns for p in SR.PARKING_NS) and h.get("text_len", 0) < 400 or re.search(r"for sale|is parked|buy this domain|domain.{0,20}expired", title):
            return "Parked", "parked"
        if h.get("construction_text") and h.get("text_len", 0) < 700:
            return "Under Construction", "construction"
        if h.get("has_password") and h.get("text_len", 0) < 500:
            return "Requires Review", "login"
        if h.get("bot_text") and h.get("text_len", 0) < 3000:
            return "Blocked", "challenge"
        if h.get("text_len", 0) < 60:
            return "Requires Review", "thin"
        return "Crawled", "ok"
    if st in (401, 403, 429):
        return "Blocked", f"http{st}"
    if st and st >= 400:
        return "Failed", f"http{st}"
    return "?", f"status{st}"


def agrees(expected: str, got: str, row: dict) -> bool:
    if expected == got:
        return True
    if expected in ("Redirected", "Crawled") and got in ("Redirected", "Crawled"):
        return True  # redirect rows: the fresh probe only checks the site still answers normally
    if expected == "Blocked" and row["category"] == "robots.txt":
        return got in ("Blocked", "Crawled")  # robots-5xx rows: homepage still fetchable is expected here
    return False


async def main():
    out = []
    sem = asyncio.Semaphore(5)
    no = asyncio.Semaphore(10**6)
    async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=10), limits=httpx.Limits(max_connections=20, max_keepalive_connections=0)) as client:
        async def one(r):
            rowp = {"url": r["url"], "qid": "", "label": "", "country": r["country"], "pool": "oracle_sample", "class": ""}
            async with sem:
                try:
                    return r, await asyncio.wait_for(probe.probe_one(client, no, rowp), timeout=120)
                except Exception as exc:
                    return r, {"outcome": f"probe_error:{type(exc).__name__}", "dns": {}}
        for coro in asyncio.as_completed([asyncio.create_task(one(r)) for r in sample]):
            r, rec = await coro
            got, why = predict(rec) if not rec["outcome"].startswith("probe_error") else ("?", rec["outcome"])
            ok = agrees(r["expected_outcome"], got, r)
            out.append({"id": r["id"], "group": "happy" if r["category"] in B.HAPPY else "error", "category": r["category"], "url": r["url"], "expected": r["expected_outcome"],
                        "fresh_probe_says": got, "detail": why, "agree": "Y" if ok else "N"})
    out.sort(key=lambda x: x["id"])
    with (DS / "oracle_agreement.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    for grp in ("happy", "error", "all"):
        sub = [x for x in out if grp == "all" or x["group"] == grp]
        print(grp, sum(x["agree"] == "Y" for x in sub), "/", len(sub))
    for x in out:
        if x["agree"] == "N":
            print("DISAGREE", x["id"], x["category"][:30], x["url"][:50], "expected", x["expected"], "fresh:", x["fresh_probe_says"], x["detail"])


asyncio.run(main())
