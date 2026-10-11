"""Gold set: find and verify the key business pages (About / Services / Products / Industries) of selected happy-path sites.

Independent of the crawler's ranking code. Candidates come from the homepage links the probe saved; each chosen page is
fetched once to confirm HTTP 200 + HTML + real text. A site enters the gold set with >= 2 verified key pages.
Output: C:/crawl_eval_data/scratch/gold.json  {host: {"About": url, ...}}
"""
import asyncio
import json
import random
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe  # noqa: E402

S = Path("C:/crawl_eval_data/scratch")
TARGET = 150
TYPES = {
    "About": r"about|company|who[-_ ]?we[-_ ]?are|our[-_ ]?story|ueber[-_ ]?uns|ÃƒÂ¼ber|a[-_ ]?propos|qui[-_ ]?sommes|quienes|nosotros|chi[-_ ]?siamo|sobre|hakk|Ã¤Â¼Å¡Ã§Â¤Â¾|Ã¤Â¼ÂÃ¦Â¥Â­|Ã¥â€¦Â³Ã¤ÂºÅ½|Ã©â€”Å“Ã¦â€“Â¼|Ã­Å¡Å’Ã¬â€šÂ¬|Ã¬â€ Å’ÃªÂ°Å“|about-us|Ã˜Â§Ã™â€žÃ˜Â´Ã˜Â±Ã™Æ’Ã˜Â©|Ã™â€¦Ã™â€  Ã™â€ Ã˜Â­Ã™â€ |Ã˜Â­Ã™Ë†Ã™â€ž",
    "Services": r"services?|solutions?|what[-_ ]?we[-_ ]?do|capabilit|expertise|leistung|dienstleist|servicios|servizi|prestations|offering|Ã£â€šÂµÃ£Æ’Â¼Ã£Æ’â€œÃ£â€šÂ¹|Ã¦Å“ÂÃ¥Å Â¡|Ã¦Å“ÂÃ¥â€¹â„¢|Ã¬â€žÅ“Ã«Â¹â€žÃ¬Å Â¤|Ã˜Â®Ã˜Â¯Ã™â€¦Ã˜Â§Ã˜Âª",
    "Products": r"products?|platform|software|features|produkte?|produits?|productos|prodotti|catalog|shop|Ã¨Â£Â½Ã¥â€œÂ|Ã¤ÂºÂ§Ã¥â€œÂ|Ã§â€Â¢Ã¥â€œÂ|Ã¬Â Å“Ã­â€™Ë†|Ã™â€¦Ã™â€ Ã˜ÂªÃ˜Â¬Ã˜Â§Ã˜Âª",
    "Industries": r"industr|markets?|sectors?|who[-_ ]?we[-_ ]?serve|branchen|secteurs|industrias|settori|Ã¦Â¥Â­Ã§â€¢Å’|Ã¨Â¡Å’Ã¤Â¸Å¡|Ã¬â€šÂ°Ã¬â€”â€¦|Ã™â€šÃ˜Â·Ã˜Â§Ã˜Â¹Ã˜Â§Ã˜Âª",
}
SKIP = re.compile(r"blog|news|career|job|privacy|terms|cookie|login|signin|cart|checkout|search|\.pdf|\.jpg|\.png|/tag/|/author/|press|event|investor|legal", re.I)


def pick(links, base_host):
    best = {}
    for url, text in links:
        p = urlparse(url)
        if SKIP.search(url) or SKIP.search(text or ""):
            continue
        depth = len([x for x in p.path.split("/") if x])
        if depth == 0 or depth > 3:
            continue
        hay = f"{p.path} {text}".lower()
        for t, pat in TYPES.items():
            if re.search(pat, hay, re.I):
                score = (depth, len(p.path))
                if t not in best or score < best[t][0]:
                    best[t] = (score, url)
    return {t: v[1] for t, v in best.items()}


async def check(client, host, rec):
    found = pick((rec.get("html") or {}).get("links", []), host)
    verified = {}
    for t, url in found.items():
        res = await probe.fetch(client, url, max_hops=5)
        ct = (res.get("headers") or {}).get("content-type", "").lower()
        if res.get("status") == 200 and "html" in ct:
            text, _ = probe.decode(res.get("body", b""), res.get("headers", {}))
            info = probe.analyse_html(text, res.get("final_url", url), urlparse(url).hostname or host)
            if info["text_len"] >= 150 and not info["bot_text"]:
                verified[t] = res.get("final_url", url)
        await asyncio.sleep(1.0)  # one request at a time per site, 1 s apart
    return host, verified


async def main():
    hosts = json.loads((S / "gold_hosts.json").read_text(encoding="utf-8"))
    probes = {}
    for f in (S / "probe").glob("*.jsonl"):
        for line in f.read_text(encoding="utf-8").split("\n"):
            try:
                r = json.loads(line)
                probes[r["host"]] = r
            except Exception:
                pass
    current = set(hosts)
    random.Random(20261010).shuffle(hosts)
    out_file = S / "gold.json"
    gold = json.loads(out_file.read_text(encoding="utf-8")) if out_file.exists() else {}
    tried = set(gold) | set(json.loads((S / "gold_tried.json").read_text(encoding="utf-8")) if (S / "gold_tried.json").exists() else [])
    todo = [h for h in hosts if h not in tried and h in probes and len((probes[h].get("html") or {}).get("links", [])) >= 3]
    print(len(todo), "to try; have", len(gold), flush=True)
    sem = asyncio.Semaphore(6)
    async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=10), limits=httpx.Limits(max_connections=20, max_keepalive_connections=0)) as client:
        async def one(h):
            async with sem:
                if len([h2 for h2, g in gold.items() if h2 in current and len(g) >= 2]) >= TARGET:
                    return h, None
                return await check(client, h, probes[h])
        for n, coro in enumerate(asyncio.as_completed([asyncio.create_task(one(h)) for h in todo]), 1):
            h, ver = await coro
            if ver is None:
                continue
            tried.add(h)
            if len(ver) >= 2:
                gold[h] = ver
            if n % 25 == 0:
                out_file.write_text(json.dumps(gold, ensure_ascii=False), encoding="utf-8")
                (S / "gold_tried.json").write_text(json.dumps(sorted(tried)), encoding="utf-8")
                print(f"  tried {n}, gold {len(gold)}", flush=True)
    out_file.write_text(json.dumps(gold, ensure_ascii=False), encoding="utf-8")
    (S / "gold_tried.json").write_text(json.dumps(sorted(tried)), encoding="utf-8")
    print("gold sites:", len(gold))


asyncio.run(main())
