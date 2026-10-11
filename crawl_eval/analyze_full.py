"""Step 5 analysis of a finished run: measures things the verdict table cannot show. Reads only the run's own files (no network).

    C:\\crawl_eval_data\\venv\\Scripts\\python.exe -B crawl_eval\\analyze_full.py <results dir>
Writes <results dir>/analysis.json
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True
import csv
import glob
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import judge  # noqa: E402
from app.crawler.discover import _score  # noqa: E402  (the crawler's own ranking function, read-only use)

TYPES = {
    "About": r"about|company|who[-_ ]?we[-_ ]?are|our[-_ ]?story|ueber|über|propos|quienes|nosotros|chi[-_ ]?siamo|sobre|hakk|会社|企業|关于|關於|회사|소개",
    "Services": r"services?|solutions?|what[-_ ]?we[-_ ]?do|capabilit|expertise|leistung|dienstleist|servicios|servizi|prestations|offering|サービス|服务|服務|서비스",
    "Products": r"products?|platform|software|features|produkte?|produits?|productos|prodotti|catalog|製品|产品|產品|제품",
    "Industries": r"industr|markets?|sectors?|who[-_ ]?we[-_ ]?serve|branchen|secteurs|industrias|settori|業界|行业|산업",
}


def norm(u: str) -> str:
    p = urlparse(u)
    host = (p.hostname or "").lower().removeprefix("www.")
    return f"{host}{(p.path or '/').rstrip('/') or '/'}"


def pctl(v, p):
    v = sorted(v)
    return round(v[min(len(v) - 1, int(len(v) * p))], 2) if v else None


def main(out: Path):
    manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    rows = {r["id"]: r for r in csv.DictReader((HERE / "dataset" / manifest["dataset_file"]).open(encoding="utf-8-sig"))}
    recs = {}
    for line in (out / "per_site.jsonl").read_text(encoding="utf-8").split("\n"):
        if line.strip():
            x = json.loads(line)
            recs[x["row_id"]] = x
    # anchor text lookup from the dataset-building probe (homepage links)
    links = {}
    for f in glob.glob("C:/crawl_eval_data/scratch/probe/*.jsonl"):
        for line in Path(f).read_text(encoding="utf-8").split("\n"):
            if line.strip():
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if (r.get("html") or {}).get("links"):
                    links[r["host"].removeprefix("www.")] = {norm(u): t for u, t in r["html"]["links"]}
    res: dict = {"run_id": manifest["run_id"]}

    # ---------------- 1. gold set: relevant-page discovery (CR-I02, L-01, L-02, L-03) ----------------
    gold_rows = [(rid, r) for rid, r in rows.items() if "gold" in r["tags"].split(";") and r["source_type"] == "real" and rid in recs]
    tot = found = 0
    miss_reasons = Counter()
    per_site = []
    by_type = defaultdict(lambda: [0, 0])
    examples = defaultdict(list)
    crawled_nonhome = relevant_nonhome = 0
    for rid, r in gold_rows:
        x = recs[rid]
        st = x["db"]["status"]
        m = re.search(r"verified 200\): (.*)$", r["expected_pages_note"])
        if not m:
            continue
        gold = {}
        for part in m.group(1).split("; "):
            if ": " in part:
                k, v = part.split(": ", 1)
                gold[k] = v
        text = x["db"]["clean_text"] or ""
        got = {norm(u) for _l, u, _b in judge.sections(text)}
        reqs = [q for q in x["requests"] if q.get("origin") == "crawler" and judge.purpose(q["url"]) == "page"]
        requested = {norm(q["url"]): q for q in reqs}
        host = (urlparse(x["site_url"]).hostname or "").removeprefix("www.")
        home_links = links.get(host, {})
        site_found = 0
        for typ, url in gold.items():
            tot += 1
            by_type[typ][1] += 1
            n = norm(url)
            if n in got:
                found += 1
                site_found += 1
                by_type[typ][0] += 1
                continue
            path = urlparse(url).path
            anchor = home_links.get(n, "")
            if st != "crawled":
                reason = f"site not crawled (status {st})"
            elif n in requested and requested[n].get("status") != 200:
                reason = "requested but fetch failed"
            elif n in requested:
                reason = "fetched but its text was empty or removed as duplicate/boilerplate"
            elif _score(path, anchor) == 0:
                reason = "never requested: ranking score 0 (skip-word or no keyword match)"
            elif len(text) >= 12000 or (x["db"]["pages_crawled"] or 0) >= 8:
                reason = "never requested: page cap / enough-text early stop"
            else:
                reason = "never requested: not in the top candidates (lower score than others)"
            miss_reasons[reason] += 1
            if len(examples[reason]) < 4:
                examples[reason].append({"row": rid, "site": host, "gold_page": url, "anchor": anchor, "score": _score(path, anchor)})
        per_site.append({"row": rid, "gold_pages": len(gold), "found": site_found, "status": st})
        for _l, u, _b in judge.sections(text):
            if norm(u).split("/", 1)[-1] not in ("", "/") and urlparse(u).path.strip("/"):
                crawled_nonhome += 1
                if any(re.search(p, urlparse(u).path, re.I) for p in TYPES.values()):
                    relevant_nonhome += 1
    sites_with_gold = len(per_site)
    full = sum(1 for s in per_site if s["found"] == s["gold_pages"])
    res["gold_set"] = {"gold_sites": sites_with_gold, "gold_pages_total": tot, "gold_pages_found": found, "recall": round(found / tot, 3) if tot else None,
                       "sites_with_all_gold_pages": full, "sites_with_none": sum(1 for s in per_site if s["found"] == 0), "recall_by_type": {k: f"{a}/{b}" for k, (a, b) in by_type.items()},
                       "why_missing": dict(miss_reasons), "examples": dict(examples),
                       "precision_note": ("Gold is not an exhaustive list of relevant pages, so true precision cannot be computed. "
                                          "Lower-bound proxy: share of crawled non-home pages whose path matches an About/Services/Products/Industries word:"),
                       "proxy_relevant_share_of_crawled_nonhome_pages": round(relevant_nonhome / crawled_nonhome, 3) if crawled_nonhome else None, "crawled_nonhome_pages": crawled_nonhome}

    # ---------------- 2. text, early stop, truncation (L-03, CR-E10) ----------------
    happy = [(rid, recs[rid]) for rid, r in rows.items() if r["category"] in judge_happy() and rid in recs and recs[rid]["db"]["status"] == "crawled"]
    lens = [len(x["db"]["clean_text"] or "") for _rid, x in happy]
    pages = [x["db"]["pages_crawled"] or 0 for _rid, x in happy]
    res["text"] = {"happy_crawled_sites": len(happy), "text_chars_p50": pctl(lens, 0.5), "text_chars_p95": pctl(lens, 0.95), "pages_p50": pctl(pages, 0.5), "pages_p95": pctl(pages, 0.95),
                   "sites_ended_with_truncation_marker": sum(1 for _rid, x in happy if (x["db"]["clean_text"] or "").endswith("...[truncated]")),
                   "sites_text_ge_12000_chars (early-stop threshold)": sum(1 for v in lens if v >= 12000),
                   "sites_with_only_homepage": sum(1 for v in pages if v <= 1), "sites_with_8_pages_cap": sum(1 for v in pages if v >= 8)}

    # ---------------- 3. browser fallback (D05/D06/D07, L-04, L-05, finding #4) ----------------
    bcalls = []
    for rid, x in recs.items():
        for b in x.get("browser", []):
            bcalls.append((rid, x, b))
    agg = Counter()
    rules = Counter()
    sel_loss = 0
    cases = []
    for rid, x, b in bcalls:
        h, rp = b.get("http_page"), b.get("rendered_page")
        if not rp:
            agg["render_returned_nothing"] += 1
            continue
        agg["rendered"] += 1
        agg["rendered_extracted_more_than_http" if b.get("rendered_extracted_more_than_http") else "rendered_extracted_NOT_more_than_http"] += 1
        if rp["visible_text_chars"] >= 500 and rp["extracted_chars_by_crawler"] < 80:
            agg["rendered_has_visible_text_but_crawler_extracted<80"] += 1
            for k, v in rp["lost_by_drop_rules"].items():
                rules[k] += v
            sel_loss += rp["lost_by_selector_rule"]
        if x["db"]["status"] in ("empty", "failed") or rp["extracted_chars_by_crawler"] < 80:
            cases.append({"row": rid, "url": b["url"], "final_status": x["db"]["status"], "http_html_bytes": h and h["html_bytes"], "http_visible_chars": h and h["visible_text_chars"],
                          "http_extracted_chars": h and h["extracted_chars_by_crawler"], "rendered_html_bytes": rp["html_bytes"], "rendered_visible_chars": rp["visible_text_chars"],
                          "rendered_extracted_chars": rp["extracted_chars_by_crawler"], "lost_by_drop_rules": rp["lost_by_drop_rules"],
                          "text_left_after_drop_rules": rp["text_left_after_drop_rules"], "lost_by_selector_rule": rp["lost_by_selector_rule"], "browser_ms": b["ms"]})
    res["browser"] = {"sites_using_browser": len({rid for rid, _x, _b in bcalls}), "render_calls": len(bcalls), "summary": dict(agg),
                      "characters_removed_by_rule_in_failed_cases": dict(rules.most_common()), "characters_removed_by_selector_rule_in_failed_cases": sel_loss,
                      "failed_cases": cases[:40]}

    # ---------------- 4. politeness, retries, User-Agent, robots (F-group, L-13..L-16) ----------------
    gaps_all, per_site_min_gap = [], []
    uas, retry_kinds, status_codes = Counter(), Counter(), Counter()
    retry_after = []
    per_domain = Counter()
    robots_5xx_rows, robots_missing_flag = [], Counter()
    for rid, x in recs.items():
        reqs = [q for q in x["requests"] if q.get("origin") == "crawler"]
        for q in reqs:
            uas[q.get("ua")] += 1
            status_codes[q.get("status") or q.get("error")] += 1
            per_domain[urlparse(q["url"]).netloc] += 1
        pg = [q for q in reqs if judge.purpose(q["url"]) == "page"]
        ts = sorted(q["t"] for q in pg)
        g = [b - a for a, b in zip(ts, ts[1:])]
        gaps_all += g
        if g:
            per_site_min_gap.append(min(g))
        att = Counter(a["url"] for a in x.get("attempts", []))
        for a in x.get("attempts", []):
            if not a.get("ok"):
                retry_kinds[a.get("kind") or a.get("error")] += 1
        for q in reqs:
            if q.get("retry_after"):
                nxt = [y for y in reqs if y["t"] > q["t"]]
                retry_after.append({"row": rid, "url": q["url"][:70], "status": q.get("status"), "retry_after": q["retry_after"], "next_request_gap_s": round(nxt[0]["t"] - q.get("t_end", q["t"]), 2) if nxt else None})
        for rb in x.get("robots", []):
            robots_missing_flag[rb.get("missing_or_failopen")] += 1
    res["politeness"] = {"user_agents_sent": dict(uas), "http_status_or_error_counts": dict(status_codes.most_common(20)), "requests_total": sum(uas.values()),
                         "gap_between_consecutive_page_requests_same_site_s": {"p05": pctl(gaps_all, 0.05), "p50": pctl(gaps_all, 0.5), "p95": pctl(gaps_all, 0.95), "min": round(min(gaps_all), 3) if gaps_all else None},
                         "sites_whose_min_gap_below_1s": sum(1 for g in per_site_min_gap if g < 1.0), "sites_with_2plus_page_requests": len(per_site_min_gap),
                         "failed_attempt_kinds": dict(retry_kinds), "responses_with_Retry-After_header": retry_after[:20],
                         "most_requested_hosts": per_domain.most_common(5)}

    # ---------------- 5. timing and per-site cost ----------------
    secs = [x["tel_site"]["seconds"] for x in recs.values() if x.get("tel_site") and not x.get("reused_from")]
    slow = sorted(((x["tel_site"]["seconds"], rid, x["site_url"][:50]) for rid, x in recs.items() if x.get("tel_site")), reverse=True)[:10]
    res["timing"] = {"sites_timed_this_run": len(secs), "p50_s": pctl(secs, 0.5), "p95_s": pctl(secs, 0.95), "max_s": max(secs) if secs else None, "slowest": slow}

    # ---------------- 6. what the DB can answer (CR-D10, H-group, L-06, L-09) ----------------
    from app.models import Website  # noqa: E402
    cols = [c.name for c in Website.__table__.columns]
    res["database_fields"] = {"website_columns": cols, "has_final_url_column": any("final" in c or "redirect" in c for c in cols), "has_http_status_column": any("http" in c for c in cols),
                              "has_pages_attempted_column": any("attempt" in c for c in cols), "has_retry_count_column": any("retry" in c for c in cols),
                              "per_page_table_in_models": False, "tables_in_models": [t for t in __import__("app.models", fromlist=["Base"]).Base.metadata.tables]}
    import sqlite3
    db = sqlite3.connect(manifest["db"])
    cur = db.cursor()
    res["database_fields"]["source_batch_non_null_rows"] = cur.execute("select count(*) from websites where source_batch is not null and source_batch != 'harness-direct'").fetchone()[0]
    res["database_fields"]["rows_total"] = cur.execute("select count(*) from websites").fetchone()[0]
    res["database_fields"]["domain_stats_rows"] = cur.execute("select count(*) from domain_stats").fetchone()[0]
    res["database_fields"]["crawl_status_vs_status_differs_rows"] = cur.execute("select count(*) from websites where crawl_status is not null and status != crawl_status").fetchone()[0]
    res["database_fields"]["jobs_by_kind_status"] = cur.execute("select kind,status,count(*) from jobs group by 1,2").fetchall()
    # duplicate content across different sites (CR-E05, L-19)
    dup = cur.execute("select content_hash,count(*) c from websites where content_hash is not null group by 1 having c>1").fetchall()
    res["database_fields"]["identical_content_hash_groups"] = len(dup)
    db.close()

    # ---------------- 7. outcome tables by verdict/category from results.csv ----------------
    rs = list(csv.DictReader((out / "results.csv").open(encoding="utf-8-sig")))
    res["verdicts_by_group"] = {"happy": dict(Counter(r["verdict"] for r in rs if r["category"] in judge_happy())),
                                "error_edge": dict(Counter(r["verdict"] for r in rs if r["category"] not in judge_happy()))}
    (out / "analysis.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("gold_set", "text", "timing")}, indent=1, ensure_ascii=False, default=str)[:3500])


def judge_happy():
    return {"Corporate / B2B services", "Manufacturers, industrial, distributors, wholesalers", "E-commerce and retail", "SaaS / software / platforms",
            "Healthcare, education, finance, real estate, non-profit, government", "Small local businesses on site builders", "Large multinational enterprises",
            "Non-English / international", "JavaScript-heavy SPAs", "Minimal / one-page / static sites", "Sitemap variants and non-standard navigation"}


if __name__ == "__main__":
    main(Path(sys.argv[1]))
