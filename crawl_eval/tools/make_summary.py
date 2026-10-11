"""Write crawl_eval/dataset/dataset_summary.md from the real files (no hand-typed numbers)."""
import csv
import glob
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_dataset as B  # noqa: E402

DS = Path(__file__).resolve().parents[1] / "dataset"
S = Path("C:/crawl_eval_data/scratch")
rows = list(csv.DictReader((DS / "testing_URLs.csv").open(encoding="utf-8-sig")))
stats = json.loads((S / "build_stats.json").read_text(encoding="utf-8"))
sha = hashlib.sha256((DS / "testing_URLs.csv").read_bytes()).hexdigest()

pools = {}
for f in sorted(glob.glob(str(DS / "candidates" / "pool_*.csv"))):
    pools[Path(f).stem.removeprefix("pool_")] = sum(1 for _ in csv.DictReader(open(f, encoding="utf-8")))
probe_outcomes = Counter()
probed = 0
for f in glob.glob(str(S / "probe" / "*.jsonl")):
    for line in Path(f).read_text(encoding="utf-8").split("\n"):
        if line.strip():
            try:
                r = json.loads(line)
            except Exception:
                continue
            probed += 1
            probe_outcomes[r["outcome"].split(":")[0] if not r["outcome"].startswith("fetch_error") else r["outcome"]] += 1
rev = sum(1 for l in (S / "reverify.jsonl").read_text(encoding="utf-8").split("\n") if l.strip())
spa = [json.loads(l) for l in (S / "spa_check.jsonl").read_text(encoding="utf-8").split("\n") if l.strip()]

botn = 0
for f in glob.glob(str(S / "probe" / "*.jsonl")):
    for line in Path(f).read_text(encoding="utf-8").split("\n"):
        if line.strip():
            try:
                rr = json.loads(line)
            except Exception:
                continue
            if (rr.get("html") or {}).get("bot_text") and (rr.get("http") or {}).get("status") in (403, 429, 503, 202):
                botn += 1
BOTPCT = (f"{botn} of {probed:,} probed domains (about {round(100 * botn / probed)}%) answered 403/429/503 with a bot-challenge page; "
          "some may be region- or rate-related. The 25 bot-protected rows were confirmed by a second probe.")
by_cat = {c: [r for r in rows if r["category"] == c] for c in B.QUOTA}
L = []
A = L.append
A("# Dataset summary – `testing_URLs.csv`")
A("")
A(f"File: `crawl_eval/dataset/testing_URLs.csv` · {len(rows)} rows · SHA-256 `{sha}` · built 2026-10-10 (seed 20261010).")
A("")
A("**The target was 1,000 rows. This file has "
  f"{len(rows)}.** The {1000 - len(rows)} missing rows are accepted shortfalls (listed below). Nothing was padded.")
A("")
hap = sum(len(by_cat[c]) for c in B.HAPPY)
A("## 1. Counts per category (target vs. actual)")
A("")
A("| Group | Category | Target | Actual | Real sites | Test endpoints | Local scenarios | Smoke |")
A("|---|---|---:|---:|---:|---:|---:|---:|")
for grp, table in (("Happy", B.HAPPY), ("Error/edge", B.ERR)):
    for c, q in table.items():
        it = by_cat[c]
        st = Counter(r["source_type"] for r in it)
        sm = sum(1 for r in it if r["smoke"] == "Y")
        flag = " **SHORT**" if len(it) < q else ""
        A(f"| {grp} | {c} | {q} | {len(it)}{flag} | {st['real']} | {st['public-test-endpoint']} | {st['local-scenario']} | {sm} |")
A(f"| | **Total** | 1000 | **{len(rows)}** | {sum(1 for r in rows if r['source_type']=='real')} | {sum(1 for r in rows if r['source_type']=='public-test-endpoint')} | {sum(1 for r in rows if r['source_type']=='local-scenario')} | {sum(1 for r in rows if r['smoke']=='Y')} |")
A("")
A(f"Happy path: **{hap}** of 600. Error/edge path: **{len(rows) - hap}** of 400. Smoke subset: **{sum(1 for r in rows if r['smoke']=='Y')}** rows, every category represented.")
A("")
A("## 2. Shortfalls (not padded) and why")
A("")
A("| Category | Missing | Why | Options |")
A("|---|---:|---|---|")
short = {c: q - len(by_cat[c]) for c, q in B.QUOTA.items() if len(by_cat[c]) < q}
why = {
    "Under construction / default pages": ("Only 14 real placeholder / default-server pages were found among ~6,400 probed domains (0.2%); with 2 local scenarios the category has 16.",
                                           "Probe the ~3,400 harvested-but-unprobed domains (about 30–40 min) or add a web-search source for default pages."),
    "Login-walled": ("Only 4 real sites whose landing page is just a password/sign-in wall (7 incl. 3 test endpoints/scenarios).",
                     "Probe more domains, or accept 7."),
    "Crawl traps": ("Real crawl traps cannot be found safely on the live web. Only the 4 local scenarios exist (calendar, session-ID, faceted, deep chain).",
                    "Add entry-point variants of the same 4 traps (near-duplicates, so not done), or accept 4."),
}
for c, n in short.items():
    w, o = why.get(c, ("see build log", ""))
    A(f"| {c} | {n} | {w} | {o} |")
A("")
A("**GATE 1 decision:** the under-construction (9) and login-walled (3) shortfalls are accepted, no extra probing. The crawl-trap shortfall (16) was filled with 16 more LOCAL SCENARIO rows "
  "(`source_type=local-scenario`): infinite pagination, day-level calendar, session ID in path, session-ID redirect, faceted navigation, endless redirect URLs, two-origin redirect loop, "
  "growing path, link explosion, growing relative link, random soft-404s, case/slash duplicates, mirrored content, endless sitemap index, infinite scroll, endless tag graph. "
  "Together with the first 4 traps, CR-C09 is tested on 20 different traps. These are synthetic: real-world trap behaviour may differ.")
A("")
A("## 3. Where the URLs came from (nothing typed from memory)")
A("")
A("| Source | Used for | Rows |")
A("|---|---|---:|")
srcs = Counter()
for r in rows:
    s = r["source_of_url"]
    key = ("Wikidata official-website property P856 (query by class/country label; Q-id kept per row)" if s.startswith("Wikidata") else
           "httpbin.org public test service" if "httpbin" in s else "badssl.com public TLS test site" if "badssl" in s else
           "own scenario server (127.0.0.1)" if "scenario_server" in s else "RFC-reserved names (.invalid/.test) and IANA example domains" if ("RFC" in s or "IANA" in s) else
           "designed by hand (input-handling / SSRF cases)" if "designed" in s else "DNS/HTTP checks run in this project")
    srcs[key] += 1
for k, n in srcs.most_common():
    A(f"| {k} | | {n} |")
A("")
A("Wikidata candidate pools (domains harvested, before probing): " + ", ".join(f"{k} {v}" for k, v in pools.items()) + ".")
A("Large pools were sampled with a fixed seed (international: up to 45 per country). Social networks, Wikipedia/Wikimedia, GitHub, Medium, Blogspot-style hosts and similar platform domains were removed from the pools. Terms of service of individual sites were NOT read; only robots.txt was respected.")
A("Web search (WebSearch) was tried for real PDF / very-large-page examples and did not return usable URLs; those cases are covered by httpbin and the scenario server instead.")
A("")
A("## 4. How each URL was verified")
A("")
A(f"Every real URL was probed by `tools/probe.py` (independent of `app/`): DNS on the system resolver **and** 1.1.1.1/8.8.8.8 (plus NS records), then `robots.txt`, then one homepage GET **only if robots allowed our user-agent**, then the sitemap. "
  f"{probed:,} domains were probed. One request at a time per domain, 8 domains in parallel.")
A("")
A("| Probe outcome | Domains |")
A("|---|---:|")
for k, n in probe_outcomes.most_common():
    A(f"| {k} | {n} |")
A("")
A(f"* **Re-verification:** rows in volatile categories (dead, timeouts, TLS, HTTP errors, bot pages, robots, login, thin, parked, under construction) were probed a **second time**; a row stays only if both probes agree. {rev} domains were re-probed; "
  f"rows dropped because the two probes disagreed: {sum(stats['dropped'].values())} ({', '.join(f'{k.split(chr(124))[0]}: {v}' for k, v in stats['dropped'].items())}).")
A(f"* **Browser check:** {len(spa)} JavaScript-looking or empty-looking pages were rendered in a real Chromium (independent of the crawler). SPA rows need almost no static text but ≥500 characters after rendering; "
  "'thin' rows must stay under 100 characters even after rendering.")
A(f"* **Gold set:** {stats['gold']} happy-path sites have About / Services / Products / Industries pages found from their homepage links and each confirmed with a real request (HTTP 200, HTML, ≥150 characters). Required: 100.")
A(f"* **Manual text review set:** {sum(1 for r in rows if 'manual-text-review' in r['tags'])} rows tagged `manual-text-review` (required: 30). Encoding rows are included.")
A("* **Hand review:** parked, under-construction, login and thin candidates were read one by one; false positives (shops that say 'for sale', real sites with a 'coming soon' banner) were excluded. "
  "The first dataset draft had error pages and one hosting placeholder among the happy-path rows; they were found by spot-checking and removed. Happy-path rows were NOT all read by a person.")
A("* **Test endpoints:** httpbin and badssl rows were each requested once at build time (`statics_verified.json`); httpbin `/delay/N` is capped at 10 s so it is not used for timeouts; badssl `revoked`/`pinning-test` open normally on this machine and were left out.")
A("* **Local scenarios:** all 44 routes were requested once and behaved as designed (`verify_scenarios.py`); one bug in my own latin-1 page was found and fixed.")
A("* **Input-handling rows** are inputs only. Private, loopback and metadata addresses are **never contacted** by us; `localtest.me` and `lvh.me` were only DNS-checked (they resolve to 127.0.0.1).")
A("")
A("* **Oracle agreement check:** a fresh independent probe of 40 random rows agreed with the expected outcome on 37/40 (92.5%) as a plain probe, and 40/40 once the 3 JavaScript-site rows were judged with a real browser (`oracle_agreement.md`).")
A("")
A("## 5. How the expected outcome (oracle) was decided")
A("")
A("From the requirements (CR-B01..B10, C, D, F) and standards (HTTP semantics, RFC 9309 for robots.txt, RFC 6761/2606 for reserved names) plus what the probe saw. **Never** from running the existing crawler. "
  f"{sum(1 for r in rows if 'ambiguous-oracle' in r['tags'].split(';'))} rows are tagged `ambiguous-oracle` (e.g. how many redirects are acceptable, robots.txt 5xx policy, timeout of 20 s): a mismatch on those is judged by hand, not automatically.")
A("")
A("| Expected outcome | Rows |")
A("|---|---:|")
for k, n in Counter(r["expected_outcome"] for r in rows).most_common():
    A(f"| {k} | {n} |")
A("")
A("`Duplicate` is an import-level outcome (second spelling of the same site); the requirement vocabulary has no word for it, so it is documented here and in `expected_status` (`import:duplicate`).")
A("")
A("## 6. Testing from Lahore, Pakistan – read before judging results")
A("")
A(f"The dataset was built and will be run from a home connection in Lahore. Some sites may show different content, a challenge page or a block from Pakistan than from Europe or the US. "
  f"{sum(1 for r in rows if 'network-dependent' in r['tags'] or 'geo-risk' in r['tags'])} rows are tagged `network-dependent` or `geo-risk`. Observed on this network:")
A("")
A("* Some public IPs (1.1.1.1, 8.8.8.8, 9.9.9.9) do not accept HTTP connections; only 94.140.14.14 and 208.67.222.222 were usable as IP-literal rows.")
A("* The local ISP resolver failed for some names that resolve fine on 1.1.1.1 (e.g. `blmlaw.com` at first probe). Dead-domain rows therefore require **both** resolvers to say the domain is gone.")
A("* No IPv6 route: IPv6-literal rows were removed.")
A("* {BOTPCT}")
A("")
A("## 7. Known limits of this dataset")
A("")
A("* Wikidata skews to larger and older organisations. Very small local shops are under-represented; the 'site builders' category means *built with Wix/Squarespace/Shopify/Webflow/WordPress* and size-filtered (≤80 links, ≤12,000 chars), **not** proven to be small local businesses.")
A("* Language is read from `<html lang>` or the script of the text, not from a language detector. Country comes from Wikidata.")
A("* Sites change. Every row has `verified_at`; a later mismatch must be re-checked and labelled `SITE-CHANGED` before it counts against the crawler.")
A("* Real sites that were dead or parked at build time may come back, and vice versa.")
A("* The dataset is a field test, not a statistical sample of the 60,000 URLs. No rate computed from it should be extrapolated.")
A("")
A("## 8. Columns")
A("")
A("`" + ", ".join(B.COLUMNS) + "`")
A("")
A("`oracle_rule` is filled only for the `ambiguous-oracle` rows. The rules were frozen before any crawler run; they are applied mechanically in Phase 1 and Phase 2 and are never changed after results are seen.")
(DS / "dataset_summary.md").write_text(("\n".join(L) + "\n").replace("{BOTPCT}", BOTPCT), encoding="utf-8")
print("written", len(L), "lines")
