"""Finding #5 (User-Agent): for every row where the crawler was 'blocked' (403/429) although the dataset expected a normal page, ask the site twice:
once with the crawler's exact headers, once with the harness headers. One GET per header set per site. Reading: 200 only for the harness UA = the site reacts to the crawler's UA/headers;
403 for both = the site (or this network) refuses any bot."""
import csv
import json
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from common import ROOT, save

from app.crawler import config

run = ROOT / "crawl_eval" / "results" / "existing-code_full_20261011"
rows = list(csv.DictReader((run / "results.csv").open(encoding="utf-8-sig")))
recs = {}
for line in (run / "per_site.jsonl").read_text(encoding="utf-8").split("\n"):
    if line.strip():
        x = json.loads(line)
        recs[x["row_id"]] = x
crawler = {"User-Agent": config.user_agent(), "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5", "Accept-Language": "en, *;q=0.5"}
harness = {"User-Agent": "WebsiteIntelligenceEval/1.0 (academic crawler field test; Lahore)", "Accept": "text/html,*/*;q=0.5"}
targets = [r for r in rows if r["expected_outcome"] == "Crawled" and r["crawler_status"] == "blocked" and r["source_type"] == "real"]
out = []
for r in targets:
    # the URL the crawler was finally blocked on
    err = r["crawler_error"] or ""
    url = err.split(" from ", 1)[1] if " from " in err else recs[r["id"]]["site_url"]
    rec = {"row": r["id"], "url": url, "crawler_error": err[:60], "verdict_in_report": r["verdict"]}
    for name, h in (("crawler_headers", crawler), ("harness_headers", harness)):
        try:
            rec[name] = httpx.get(url, headers=h, timeout=15, follow_redirects=True).status_code
        except Exception as exc:
            rec[name] = type(exc).__name__
        time.sleep(1.0)
    out.append(rec)
only_harness_ok = [o for o in out if o["crawler_headers"] in (403, 429) and o["harness_headers"] == 200]
both_blocked = [o for o in out if o["crawler_headers"] in (403, 429) and o["harness_headers"] in (403, 429)]
save("t_ua_blocked", {"crawler_user_agent": config.user_agent(), "rows_tested": len(out), "blocked_only_for_crawler_headers": len(only_harness_ok), "blocked_for_both": len(both_blocked),
                      "other": len(out) - len(only_harness_ok) - len(both_blocked), "rows": out,
                      "reading": "The crawler's User-Agent is descriptive and honest (requirement CR-F02) and the requirements forbid bypassing anti-bot protection (CR-F05): this is reported as a design decision, not as a defect."})
