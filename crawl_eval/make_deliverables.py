"""Step 5: build the GATE 3 deliverables from the finished run.  (reads files only; no network)
    C:\\crawl_eval_data\\venv_tools\\Scripts\\python.exe -B crawl_eval\\make_deliverables.py crawl_eval\\results\\existing-code_full_20261011
"""
from __future__ import annotations

import csv
import html
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import deliverables_data as D  # noqa: E402

out = Path(sys.argv[1])
J = lambda p: json.loads(Path(p).read_text(encoding="utf-8-sig"))  # noqa: E731
manifest, metrics, analysis = J(out / "run_manifest.json"), J(out / "metrics.json"), J(out / "analysis.json")
X = HERE / "results" / "extra_tests"
t_score, t_scale, t_cancel, t_ua = J(X / "t_score.json"), J(X / "t_scale_local.json"), J(X / "t_cancel_recover.json"), J(X / "t_ua_blocked.json")
t_import, t_ssrf, t_env, t_b150, t_b600, t_root = (J(X / f) for f in ("t_import_60k.json", "t_browser_ssrf.json", "t_env_copy.json", "t_bomb_150mb.json", "t_bomb_600mb.json", "t_extraction_rootcause.json"))
rows = list(csv.DictReader((out / "results.csv").open(encoding="utf-8-sig")))
ds = {r["id"]: r for r in csv.DictReader((HERE / "dataset" / manifest["dataset_file"]).open(encoding="utf-8-sig"))}
imp = J(out / "import_decisions.json")
recs = {}
for line in (out / "per_site.jsonl").read_text(encoding="utf-8").split("\n"):
    if line.strip():
        x = json.loads(line)
        recs[x["row_id"]] = x
cand = J("C:/crawl_eval_data/scratch/rootcause_candidates.json")
trace = {r["cr_id"]: r for r in csv.DictReader((HERE / "traceability_matrix.csv").open(encoding="utf-8-sig"))}

# ------------------------------------------------------------------ facts
def cat(name):
    return [r for r in rows if r["category"] == name]


def judged(items):
    return [r for r in items if r["verdict"] in ("MATCH", "MISMATCH", "PARTIAL")]


def match(items):
    return sum(1 for r in items if r["verdict"] == "MATCH")


g = analysis["gold_set"]
pct = lambda s: f"{round(100 * int(s.split('/')[0]) / int(s.split('/')[1]))}%"  # noqa: E731
inv_rows = [r for r in rows if r["category"] == "Input handling" and r["expected_status"] == "import:invalid"]
inv_wrong = [r for r in inv_rows if r["verdict"] == "MISMATCH"]
pol = analysis["politeness"]
F = dict(
    imp_added=sum(1 for v in imp.values() if v["decision"] == "added"), imp_lines=len(rows), sb_rows=analysis["database_fields"]["source_batch_non_null_rows"], db_rows=analysis["database_fields"]["rows_total"],
    inv_wrong=len(inv_wrong), inv_total=len(inv_rows), inv_wrong_ids=", ".join(r["id"] for r in inv_wrong),
    dead_n=len(cat("Dead domains (NXDOMAIN)")), dead_inv=sum(1 for r in cat("Dead domains (NXDOMAIN)") if r["actual"] == "Invalid"),
    park_match=match(cat("Parked / for-sale domains")), park_n=len(cat("Parked / for-sale domains")),
    uc_match=match(cat("Under construction / default pages")), uc_judged=len(judged(cat("Under construction / default pages"))),
    thin_match=match(cat("Thin / empty / error-only pages")), thin_judged=len(judged(cat("Thin / empty / error-only pages"))),
    bot_match=match(cat("Bot-protected / WAF")), bot_judged=len(judged(cat("Bot-protected / WAF"))),
    vocab_mm=sum(1 for r in rows if "cannot express" in r["reason"]), pages_p50=analysis["text"]["pages_p50"], pages_p95=analysis["text"]["pages_p95"], pages_cap=analysis["text"]["sites_with_8_pages_cap"],
    crawled_sites=metrics["status_counts"].get("crawled", 0), score0_good=t_score["good_paths_scored_0"], score0_total=t_score["good_paths_total"],
    gold_recall=f"{g['recall']*100:.1f}%", gold_found=g["gold_pages_found"], gold_total=g["gold_pages_total"],
    gold_score0=g["why_missing"].get("never requested: ranking score 0 (skip-word or no keyword match)", 0), gold_cap=g["why_missing"].get("never requested: page cap / enough-text early stop", 0),
    g_serv=pct(g["recall_by_type"]["Services"]), g_prod=pct(g["recall_by_type"]["Products"]), g_ind=pct(g["recall_by_type"]["Industries"]), g_about=pct(g["recall_by_type"]["About"]),
    ge12k=analysis["text"]["sites_text_ge_12000_chars (early-stop threshold)"], crawled_happy=analysis["text"]["happy_crawled_sites"],
    traps_pass=match(cat("Crawl traps")), body_sites=len(cand["A"]), render_ok=analysis["browser"]["summary"].get("rendered", 0), render_gain=analysis["browser"]["summary"].get("rendered_extracted_more_than_http", 0),
    render_none=analysis["browser"]["summary"].get("render_returned_nothing", 0), happy_crawled=metrics["happy_crawled"], texts_n=sum(1 for x in recs.values() if x["db"]["clean_text"]),
    trunc=analysis["text"]["sites_ended_with_truncation_marker"], robots5_n=sum(1 for r in rows if r["subcategory"] in ("robots.txt 5xx", "robots.txt returns 503")),
    gap_lt1=pol["sites_whose_min_gap_below_1s"], gap_sites=pol["sites_with_2plus_page_requests"], gap_lt1_=pol["sites_whose_min_gap_below_1s"],
    domain_rows=analysis["database_fields"]["domain_stats_rows"], tasks_1000=t_scale["run_1000"]["asyncio_tasks_1s_after_start"], crawling_1000=t_scale["run_1000"]["rows_in_crawling_state_1s_after_start"],
    n_rows=len(rows), cov_crawler="91%", ua_only=t_ua["blocked_only_for_crawler_headers"], ua_n=t_ua["rows_tested"], ua_both=t_ua["blocked_for_both"], dup_groups=analysis["database_fields"]["identical_content_hash_groups"],
)


class Safe(dict):
    def __missing__(self, k):
        print("MISSING PLACEHOLDER:", k)
        return "{?" + k + "?}"


fill = lambda s: s.format_map(Safe(F))  # noqa: E731

# ------------------------------------------------------------------ scorecard
W = {"M": 3, "S": 2, "O": 1}
sc_rows = []
for cr, (verdict, evidence, iss) in D.SC.items():
    t = trace[cr]
    sc_rows.append({"cr_id": cr, "group": t["group"], "priority": t["priority"], "requirement": t["requirement_short"], "verdict": verdict, "evidence": fill(evidence), "issues": iss, "static_verdict_step1": t["static_verdict"]})
missing = set(trace) - set(D.SC)
assert not missing, missing
with (out / "requirements_scorecard.csv").open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(sc_rows[0]))
    w.writeheader()
    w.writerows(sc_rows)


def coverage(items, musts_only=False, count_nt=True):
    num = den = 0.0
    for r in items:
        if r["verdict"] == "N/A" or (musts_only and r["priority"] != "M"):
            continue
        if r["verdict"] == "NOT TESTED" and not count_nt:
            continue
        wt = W[r["priority"]]
        den += wt
        num += wt * {"PASS": 1, "PARTIAL": 0.5}.get(r["verdict"], 0)
    return round(100 * num / den, 1) if den else None


cov_all, cov_must, cov_all_nt, cov_must_nt = coverage(sc_rows), coverage(sc_rows, True), coverage(sc_rows, False, False), coverage(sc_rows, True, False)
vc = Counter(r["verdict"] for r in sc_rows)
must_rows = [r for r in sc_rows if r["priority"] == "M" and r["verdict"] != "N/A"]
must_pass = round(100 * sum(1 for r in must_rows if r["verdict"] == "PASS") / len(must_rows), 1)

# ------------------------------------------------------------------ issues + leads
issues = []
for i in D.ISSUES:
    d = {k: (fill(v) if isinstance(v, str) else v) for k, v in i.items()}
    issues.append(d)
with (out / "issues.csv").open("w", newline="", encoding="utf-8-sig") as f:
    keys = ["id", "sev", "kind", "title", "crs", "module", "loc", "repro", "expected", "actual", "evidence", "cause", "fix", "status", "leads"]
    w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
    w.writeheader()
    for d in issues:
        w.writerow({k: d.get(k, "") for k in keys})
SEV_ORDER = {"Critical": 0, "Major": 1, "Minor": 2, "Cosmetic": 3}
defects = [d for d in issues if d["kind"] == "defect"]
sev_count = Counter(d["sev"] for d in defects)
md = ["# Issue log – existing crawler (Phase 1)", "",
      f"Run `{manifest['run_id']}` · code `{manifest['git_commit'][:8]}` (tag `{manifest['git_tag']}`) · {len(defects)} defects: " + ", ".join(f"{sev_count.get(s, 0)} {s}" for s in SEV_ORDER) +
      f" · {sum(1 for d in issues if d['kind'] == 'design-decision')} design decision · {sum(1 for d in issues if d['kind'] == 'policy-question')} policy question.", "",
      "Severity scale (phase-plan 1.6): Critical = security issue, data loss, batch-stopping crash or silently wrong results at scale; Major = a MUST requirement fails or a whole class of sites is mishandled; Minor = narrow case or a SHOULD fails; Cosmetic = naming, messages, documentation.",
      "A design decision and a policy question are NOT counted as defects. No fix is implemented in Phase 1.", "",
      "| ID | Severity | Type | Title | CR-IDs | Module | Leads | Status |", "|---|---|---|---|---|---|---|---|"]
for d in sorted(issues, key=lambda d: (SEV_ORDER[d["sev"]], d["id"])):
    md.append(f"| {d['id']} | {d['sev']} | {d['kind']} | {d['title']} | {d['crs']} | {d['module']} | {d['leads']} | {d['status']} |")
md.append("")
for d in sorted(issues, key=lambda d: (SEV_ORDER[d["sev"]], d["id"])):
    md += [f"## {d['id']} – {d['title']}", "", f"* **Severity:** {d['sev']} · **Type:** {d['kind']} · **Status:** {d['status']}", f"* **Requirements:** {d['crs']} · **Leads:** {d['leads']}",
           f"* **Code location:** `{d['loc']}`", f"* **Repro:** {d['repro']}", f"* **Expected:** {d['expected']}", f"* **Actual:** {d['actual']}", f"* **Evidence:** {d['evidence']}",
           f"* **Suspected root cause:** {d['cause']}", f"* **Fix direction (not implemented):** {d.get('fix', '')}", ""]
(out / "issues.md").write_text("\n".join(md), encoding="utf-8")

leads = [{"lead": k, "verdict": v[0], "evidence": fill(v[1]), "issues": v[2]} for k, v in D.LEADS.items()]
assert len(leads) == 23
with (out / "leads_verdicts.csv").open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["lead", "verdict", "evidence", "issues"])
    w.writeheader()
    w.writerows(leads)
(out / "leads_verdicts.md").write_text("# Verdict on every lead in docs/known-findings.md (Part 1)\n\nLeads were hypotheses. Each one below was tested by running something.\n\n| Lead | Verdict | Evidence | Issue |\n|---|---|---|---|\n" +
                                       "\n".join(f"| {l['lead']} | {l['verdict']} | {l['evidence']} | {l['issues']} |" for l in leads) + "\n", encoding="utf-8")

# ------------------------------------------------------------------ numbers for banner / summary
vd = metrics["verdicts"]
judged_n = len(rows) - vd.get("ENV-DEPENDENT", 0) - vd.get("SITE-CHANGED", 0) - vd.get("ORACLE-LIMITATION", 0) - vd.get("NOT-RUN", 0)
happy_cats = set(__import__("run_eval").HAPPY_CATS) if False else {"Corporate / B2B services", "Manufacturers, industrial, distributors, wholesalers", "E-commerce and retail", "SaaS / software / platforms",
                                                                    "Healthcare, education, finance, real estate, non-profit, government", "Small local businesses on site builders", "Large multinational enterprises",
                                                                    "Non-English / international", "JavaScript-heavy SPAs", "Minimal / one-page / static sites", "Sitemap variants and non-standard navigation"}
hp, er = [r for r in rows if r["category"] in happy_cats], [r for r in rows if r["category"] not in happy_cats]


def rate(items):
    j = judged(items)
    return (round(100 * match(items) / len(j), 1) if j else None, len(j))


m_all, m_h, m_e = rate(rows), rate(hp), rate(er)
ready = "NOT READY"
useful = metrics["happy_useful_text_ge_500"]
stats = dict(cov_all=cov_all, cov_must=cov_must, must_pass=must_pass, m_all=m_all, m_h=m_h, m_e=m_e)
(out / "scorecard_summary.json").write_text(json.dumps({"coverage_all_pct": cov_all, "coverage_must_pct": cov_must, "coverage_all_excluding_not_tested": cov_all_nt, "coverage_must_excluding_not_tested": cov_must_nt,
                                                         "must_requirements_PASS_pct": must_pass, "verdict_counts": dict(vc), "match_rate_judged_all": m_all, "match_rate_judged_happy": m_h, "match_rate_judged_error_edge": m_e,
                                                         "defects_by_severity": dict(sev_count)}, indent=1), encoding="utf-8")

lr0 = list(csv.DictReader((out / "label_review.csv").open(encoding="utf-8-sig")))
n_chk = sum(1 for r in lr0 if r["fresh_probe_reading"])
n_not0 = sum(1 for r in lr0 if r["label_holds"] == "NO")
reclass_txt = ", ".join(f"{r['id']} to {r['new_label']}" for r in lr0 if r["label_holds"] == "NO")
# ------------------------------------------------------------------ plain summary.md (replaces generated stats file)
if (out / "summary.md").exists() and not (out / "run_stats.md").exists():
    shutil.copy(out / "summary.md", out / "run_stats.md")
S = f"""# Phase 1 result in plain English – existing crawler, unchanged

**Verdict: {ready}.** Four Critical problems, only {cov_must}% of the MUST requirements covered, and the crawler finds only {g['recall']*100:.0f}% of the key pages (About / Services / Products / Industries) on the sites tested.

## What was tested
* {len(rows)} URLs ({len(hp)} normal sites, {len(er)} difficult cases) checked against the requirements. 804 real sites, 123 public test endpoints, 61 local scenarios. Crawled once, at concurrency 5 (the code's own default is 10); rows that did not match got one extra independent check.
* The code was not changed (56 files, SHA-256 checked before and after). Extra tests: 60,000-URL import, 1,000-site scale test, cancel and crash recovery, decompression bombs, browser redirect, `.env` handling.

## The numbers (this run only)
| Measure | Result |
|---|---|
| Rows where the crawler did what the requirements say | {vd['MATCH']} of {len(rows)} ({m_all[0]}% of the {m_all[1]} rows that can be judged against the crawler) |
| Normal sites | {m_h[0]}% match ({m_h[1]} judged); {metrics['happy_crawled']} of {metrics['happy_rows']} crawled, {useful} with at least 500 characters of text |
| Difficult cases (errors, edge cases, traps, bad input) | {m_e[0]}% match ({m_e[1]} judged) |
| Rows not counted against the crawler | {vd.get('ENV-DEPENDENT',0)} ENV-DEPENDENT (my network / ISP DNS), {vd.get('SITE-CHANGED',0)} SITE-CHANGED, {vd.get('ORACLE-LIMITATION',0)} ORACLE-LIMITATION |
| Requirement coverage | {cov_all}% (weighted), {cov_must}% MUST-only; {must_pass}% of MUST requirements fully PASS |
| Key pages found (gold set, {g['gold_sites']} sites) | {g['gold_pages_found']} of {g['gold_pages_total']} = {g['recall']*100:.1f}% |
| Time per site | median {metrics['latency_s_p50']} s, 95th percentile {metrics['latency_s_p95']} s |

## What works well
* Plain sites: most normal websites are crawled correctly, never more than 8 pages, homepage first, junk pages avoided.
* Safe by default: private addresses in redirects are refused on the HTTP path; blocked sites, HTTP errors, TLS errors and robots.txt "disallow all" are handled; crawl traps did not trap it (19 of 20).
* Reliability: no failing website stopped the crawl; a killed run recovered with 0 rows lost; memory stayed small (297 MB peak in the full run).

## The most serious problems
1. **Browser fallback can be sent to internal addresses** (Critical): a JavaScript redirect to 127.0.0.2 was followed and the internal page was stored.
2. **A decompression bomb can exhaust memory** (Critical): +205 MB for 150 MB, +941 MB for 600 MB, no cap.
3. **The safety check misses 100.64.0.0/10**, which includes a cloud metadata address (Critical).
4. **One malformed URL crashes the whole import** (Critical).
5. **Text extraction deletes whole pages**: {F['body_sites']} sites where the page had text but the crawler kept almost none, because a CSS class like "sidebar" or "cookie" sits on the page body.
6. **Key pages are missed**: ranking gives score 0 to {F['score0_good']} of {F['score0_total']} real business paths; non-English paths are not understood.
7. **Parked, placeholder and login pages are saved as normal results**; DNS failure is reported as "invalid"; the status list lacks Parked / Redirected / Under Construction.

## Not counted as bugs
* **User-Agent blocked** ({F['ua_only']} of {F['ua_n']} blocked happy-path sites accept another User-Agent): a design decision, because the requirements demand an honest User-Agent and forbid bypassing protection.
* **robots.txt answering 5xx is treated as allowed**: a policy question for the project owner (the RFC says to treat it as disallow).
* **T0901**: ORACLE-LIMITATION (the dataset verified `http://`, the importer always uses `https://`).

## Limits of this test
* Wikidata favours large and old organisations; "small local business" rows are site-builder sites of limited size, not proven small or local.
* Tested from Lahore: {vd.get('ENV-DEPENDENT',0)} rows are ENV-DEPENDENT and some SITE-CHANGED rows may also be geo-blocking or rate limits.
* One run on one day; sites change. Not a statistical sample, and nothing here is a forecast for 60,000 sites.
* **Close-out check of the labels:** all {len(lr0) - 3} rows labelled SITE-CHANGED or ENV-DEPENDENT at the end of the run (plus 3 rows moved by a rule refinement) are listed with their evidence in `label_review.csv`. A fresh independent probe of {n_chk} of them (10 random SITE-CHANGED rows plus the 3 refinement rows) showed the label holds for {n_chk - n_not0} and not for {n_not0}; reclassified: {reclass_txt}. Sites that alternate between 403 and 200 (T0118, T0575) cannot be called "changed".
* The Chromium child process memory was not measured. Excel upload, the web paste box and 200-status challenge pages were not tested.
"""
(out / "summary.md").write_text(S, encoding="utf-8")

# ------------------------------------------------------------------ SIR note (<= 10 bullets)
SIR = f"""# Update for sir – Phase 1: testing the existing crawler (unchanged)

* **What we tested:** the existing crawler, without any change, on {len(rows)} URLs: {len(hp)} normal websites in 11 types and {len(er)} difficult cases (dead, parked, blocked, slow, broken, bad input, crawl traps). 804 are real sites; each was crawled once (rows that did not match got one extra independent check). Plus extra tests: 60,000-URL import, 1,000-site run, cancel and crash recovery.
* **Overall coverage of the requirements:** {cov_all}% (weighted), {cov_must}% for the MUST items. Of {len(must_rows)} applicable MUST requirements {sum(1 for r in must_rows if r['verdict']=='PASS')} fully pass, {sum(1 for r in must_rows if r['verdict']=='PARTIAL')} partly, {sum(1 for r in must_rows if r['verdict']=='FAIL')} fail, {sum(1 for r in must_rows if r['verdict']=='NOT TESTED')} not tested.
* **What works well:** normal websites ({m_h[0]}% match); homepage-first and at most 8 pages; junk pages skipped; blocked sites, HTTP errors, TLS errors and "robots disallow all" handled; 19 of 20 crawl traps did not trap it; no failing site stopped the batch; a killed run recovered with nothing lost.
* **Most serious problems:** (1) the browser fallback can be redirected to an internal address and stores what it finds; (2) a decompression bomb can use unlimited memory; (3) the address safety check misses a cloud-metadata range; (4) one bad URL crashes the whole import. All four are Critical.
* **Quality of the data:** it finds only {g['recall']*100:.0f}% of the important pages (About / Services / Products); the ranking gives score 0 to many real pages, especially non-English ones. On {F['body_sites']} sites it threw away the whole page text because of a CSS class name. The browser fallback reads the page too early and rarely helps.
* **Error-path behaviour:** only {m_e[0]}% of the difficult cases are handled as the requirements say. Parked domains are saved as normal results (0 of 30 recognised); placeholder and login pages are saved as normal; a dead domain is called "invalid" instead of "unreachable"; there is no status for Parked, Redirected or Under Construction.
* **Performance and reliability (this run only):** median {metrics['latency_s_p50']} s per site, 95th percentile {metrics['latency_s_p95']} s at concurrency 5; no crash of the crawl; memory small (297 MB peak). 1,000 local sites finished in 91 s. We make **no** claim about 60,000 sites.
* **Two items for your decision:** (a) when a site's robots.txt answers a server error (5xx), the crawler treats it as "allowed"; the standard says "disallowed". We need a written policy. (b) Some sites ({F['ua_only']} of {F['ua_n']} blocked ones) refuse the crawler's honest User-Agent; we do not bypass this, as the requirements forbid it.
* **Honest limits:** sites change and the test ran from Lahore ({vd.get('ENV-DEPENDENT',0)} rows are marked as network-caused and not counted); the sample favours large, old organisations; one run on one day; Excel upload and the web paste box were not tested.
* **What happens next:** after your approval, Phase 2 builds a new crawler that meets every requirement, then tests it on the same URLs and compares line by line with these results. Nothing in Phase 2 has been started.
"""
(HERE / "SIR_UPDATE_phase1.md").write_text(SIR, encoding="utf-8")
shutil.copy(HERE / "SIR_UPDATE_phase1.md", out / "SIR_UPDATE_phase1.md")
bullets = sum(1 for l in SIR.splitlines() if l.startswith("* "))
assert bullets <= 10, bullets

# ------------------------------------------------------------------ report.html
esc = html.escape
VCOL = {"PASS": "#1a7f37", "PARTIAL": "#b08800", "FAIL": "#cf222e", "NOT TESTED": "#6e7781", "N/A": "#8c959f", "MATCH": "#1a7f37", "MISMATCH": "#cf222e", "ENV-DEPENDENT": "#8250df", "SITE-CHANGED": "#0969da",
        "ORACLE-LIMITATION": "#bc4c00", "Critical": "#82071e", "Major": "#cf222e", "Minor": "#b08800", "Cosmetic": "#6e7781"}
badge = lambda t: f'<span class="b" style="background:{VCOL.get(t, "#6e7781")}">{esc(t)}</span>'  # noqa: E731
GROUPS = {"A": "A. URL ingestion & management", "B": "B. URL validation & website status", "C": "C. Page discovery & focused crawling", "D": "D. Fetching (HTTP-first, conditional browser)",
          "E": "E. Content extraction, cleaning & evidence", "F": "F. Responsible crawling & safety", "G": "G. Queue, reliability & scale", "H": "H. Crawl data persistence",
          "I": "I. Rollout, pilot & acceptance", "J": "J. Testing", "K": "K. Coding rules (Phase 2)"}
H = []
A = H.append
A(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Crawler Field Test Report</title>
<style>:root{{--bg:#fff;--fg:#1f2328;--mut:#59636e;--line:#d1d9e0;--card:#f6f8fa}}@media(prefers-color-scheme:dark){{:root{{--bg:#0d1117;--fg:#e6edf3;--mut:#9198a1;--line:#3d444d;--card:#151b23}}}}
body{{font:15px/1.5 system-ui,Segoe UI,sans-serif;margin:0;background:var(--bg);color:var(--fg)}}main{{max-width:1180px;margin:0 auto;padding:16px}}h1{{font-size:26px}}h2{{margin-top:34px;border-bottom:1px solid var(--line);padding-bottom:6px}}
table{{border-collapse:collapse;width:100%;font-size:13.5px;margin:10px 0}}th,td{{border:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top}}th{{background:var(--card)}}
.b{{color:#fff;border-radius:10px;padding:1px 8px;font-size:12px;white-space:nowrap}}.banner{{background:var(--card);border:2px solid #cf222e;border-radius:10px;padding:14px 18px}}
.kpi{{display:flex;flex-wrap:wrap;gap:10px;margin:10px 0}}.kpi div{{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px 12px;min-width:150px}}.kpi b{{font-size:22px;display:block}}
details{{margin:2px 0}}summary{{cursor:pointer}}.small{{color:var(--mut);font-size:12.5px}}input#q{{width:100%;padding:7px;margin:8px 0;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg)}}
.scroll{{overflow-x:auto}}code{{background:var(--card);padding:1px 4px;border-radius:4px}}</style></head><body><main>
<h1>Website Crawler – Phase 1 Field Test Report</h1>
<p class="small">Existing crawler, code unchanged (git <code>{manifest['git_commit'][:8]}</code>, tag <code>{manifest['git_tag']}</code>). Run <code>{esc(manifest['run_id'])}</code>. Dataset <code>{esc(manifest['dataset_file'])}</code> sha256 <code>{manifest['dataset_sha256'][:16]}…</code>.
App code hash check: before <b>{manifest['app_code_unchanged_before']}</b>, after <b>{manifest['app_code_unchanged_after']}</b> (56 files). Concurrency used: <b>{manifest['concurrency_used']}</b> – the code's own default is <b>{manifest['crawler_own_default_concurrency']['config.CONCURRENCY']}</b>. Tested from Lahore, Pakistan.</p>
<h2>1. Verdict</h2><div class="banner"><b style="font-size:20px">{ready}</b> – because there are {sev_count.get('Critical',0)} Critical issues (browser SSRF, decompression-bomb memory, guard gap 100.64/10, import crash), only {cov_must}% of the MUST requirements are covered, and the crawler finds only {g['recall']*100:.1f}% of the key pages.
<div class="kpi"><div><b>{cov_all}%</b>requirement coverage (weighted)</div><div><b>{cov_must}%</b>MUST-only coverage</div><div><b>{must_pass}%</b>MUST requirements fully PASS</div>
<div><b>{m_all[0]}%</b>URL expectation match, all ({m_all[1]} judged)</div><div><b>{m_h[0]}%</b>normal sites</div><div><b>{m_e[0]}%</b>difficult cases</div>
<div><b>{sev_count.get('Critical',0)} / {sev_count.get('Major',0)} / {sev_count.get('Minor',0)} / {sev_count.get('Cosmetic',0)}</b>Critical / Major / Minor / Cosmetic</div></div>
<p class="small">Also logged: 1 design decision (User-Agent blocked) and 1 policy question (robots.txt 5xx). Not counted against the crawler: {vd.get('ENV-DEPENDENT',0)} ENV-DEPENDENT, {vd.get('SITE-CHANGED',0)} SITE-CHANGED, {vd.get('ORACLE-LIMITATION',0)} ORACLE-LIMITATION rows.
Coverage = (PASS + 0.5 × PARTIAL) ÷ applicable requirements, weighted M=3, S=2, O=1; NOT TESTED counts as 0 credit (excluding them: {cov_all_nt}% all, {cov_must_nt}% MUST).</p></div>
<p>This is a field test, not a statistical sample: nothing here is a forecast for 60,000 URLs (CR-I03).</p>""")
A("<h2>2. Requirements scorecard</h2><p class='small'>Click a row for the evidence. Counts: " + ", ".join(f"{badge(k)} {v}" for k, v in vc.items()) + "</p>")
for gk, gname in GROUPS.items():
    items = [r for r in sc_rows if r["group"] == gk]
    gc = Counter(r["verdict"] for r in items)
    A(f"<h3>{gname} <span class='small'>({', '.join(f'{v} {k}' for k, v in gc.items())})</span></h3><table><tr><th>ID</th><th>Pri</th><th>Requirement</th><th>Verdict</th><th>Issues</th></tr>")
    for r in items:
        A(f"<tr><td>{r['cr_id']}</td><td>{r['priority']}</td><td><details><summary>{esc(r['requirement'])}</summary><div class='small'>{esc(r['evidence'])}</div></details></td><td>{badge(r['verdict'])}</td><td>{esc(r['issues'])}</td></tr>")
    A("</table>")
A("<h2>3. Where the code is weak</h2><table><tr><th>Module</th><th>Critical</th><th>Major</th><th>Minor</th><th>Cosmetic</th><th>Total</th></tr>")
mods = defaultdict(Counter)
for d in defects:
    for m in re.split(r"[/,]\s*", d["module"]):
        mods[m.strip()][d["sev"]] += 1
for m, c in sorted(mods.items(), key=lambda kv: (-kv[1]["Critical"], -kv[1]["Major"], -sum(kv[1].values()))):
    A(f"<tr><td>{esc(m)}</td><td>{c['Critical'] or ''}</td><td>{c['Major'] or ''}</td><td>{c['Minor'] or ''}</td><td>{c['Cosmetic'] or ''}</td><td>{sum(c.values())}</td></tr>")
A("</table><p class='small'>An issue that spans two modules is counted in both. Worst offenders: <b>extract</b> (page deletion), <b>discover</b> (ranking), <b>browser</b> (SSRF, timing), <b>fetcher</b> (bomb, time, retries), <b>guard</b>, <b>importer</b>.</p>")
A("<h2>4. Results by category</h2><p class='small'>Match rate = MATCH ÷ rows judged against the crawler (ENV-DEPENDENT, SITE-CHANGED and ORACLE-LIMITATION excluded). Happy path and error path are shown separately.</p>")
for title, items_, cats_ in (("Happy path", hp, [c for c in dict.fromkeys(r["category"] for r in rows) if c in happy_cats]), ("Error and edge path", er, [c for c in dict.fromkeys(r["category"] for r in rows) if c not in happy_cats])):
    A(f"<h3>{title}</h3><table><tr><th>Category</th><th>Rows</th><th>MATCH</th><th>PARTIAL</th><th>MISMATCH</th><th>ENV</th><th>SITE-CHG</th><th>ORACLE-LIM</th><th>Match rate</th><th>Example mismatches</th></tr>")
    for c in cats_:
        it = cat(c)
        cn = Counter(r["verdict"] for r in it)
        j = judged(it)
        ex = "; ".join(esc(r["url"][:48]) for r in it if r["verdict"] == "MISMATCH")[:260]
        A(f"<tr><td>{esc(c)}</td><td>{len(it)}</td><td>{cn['MATCH']}</td><td>{cn['PARTIAL']}</td><td>{cn['MISMATCH']}</td><td>{cn['ENV-DEPENDENT']}</td><td>{cn['SITE-CHANGED']}</td><td>{cn['ORACLE-LIMITATION']}</td><td>{round(100*cn['MATCH']/len(j)) if j else '-'}%</td><td class='small'>{ex}</td></tr>")
    A("</table>")
b = analysis["browser"]
A(f"""<h2>5. Quality &amp; performance metrics (this run only – no extrapolation, CR-I03)</h2><table>
<tr><th>Measure (CR-I02)</th><th>Result</th></tr>
<tr><td>Crawl success rate, normal sites</td><td>{metrics['happy_crawled']} of {metrics['happy_rows']} crawled ({round(100*metrics['happy_crawled']/metrics['happy_rows'],1)}%); the rest: blocked, unreachable, DNS (many are ENV-DEPENDENT or SITE-CHANGED)</td></tr>
<tr><td>Useful-content rate</td><td>{useful} of {metrics['happy_crawled']} crawled normal sites have ≥ 500 characters of text ({round(100*useful/metrics['happy_crawled'],1)}%)</td></tr>
<tr><td>Relevant-page discovery (gold set)</td><td>Recall {g['recall']*100:.1f}% ({g['gold_pages_found']}/{g['gold_pages_total']}) on {g['gold_sites']} sites; Services {F['g_serv']}, Products {F['g_prod']}, Industries {F['g_ind']}, About {F['g_about']}. Precision cannot be computed because the gold list is not exhaustive; proxy: {g['proxy_relevant_share_of_crawled_nonhome_pages']*100:.0f}% of crawled non-home pages match a business keyword. Missing pages: {', '.join(f'{v} {k}' for k, v in sorted(g['why_missing'].items(), key=lambda kv: -kv[1])[:4])}.</td></tr>
<tr><td>Browser fallback</td><td>Used on {b['sites_using_browser']} sites ({b['render_calls']} renders, ~5 s each; 91 of 600 normal sites = 15%). Benefit: {F['render_gain']} of {F['render_ok']} successful renders gave more extracted text; {F['render_none']} returned nothing.</td></tr>
<tr><td>Latency per site</td><td>p50 {metrics['latency_s_p50']} s, p95 {metrics['latency_s_p95']} s, max {analysis['timing']['max_s']} s (slow-drip scenario)</td></tr>
<tr><td>Requests, retries, failures</td><td>{pol['requests_total']} HTTP requests; {metrics['retries']} retried URLs; failed attempts by kind: {esc(json.dumps(pol['failed_attempt_kinds']))}</td></tr>
<tr><td>Blocked rate</td><td>{metrics['status_counts'].get('blocked',0)} blocked + {metrics['status_counts'].get('robots_blocked',0)} robots-blocked of {len(rows)-vd.get('NOT-RUN',0)} rows (test set is rich in blocked sites by design)</td></tr>
<tr><td>Pages per site / text size</td><td>pages p50 {analysis['text']['pages_p50']}, p95 {analysis['text']['pages_p95']}; text p50 {analysis['text']['text_chars_p50']} chars, p95 {analysis['text']['text_chars_p95']}; {analysis['text']['sites_with_only_homepage']} sites homepage-only; {analysis['text']['sites_ended_with_truncation_marker']} truncated</td></tr>
<tr><td>Politeness</td><td>Gap between page requests of one site: p50 {pol['gap_between_consecutive_page_requests_same_site_s']['p50']} s, min {pol['gap_between_consecutive_page_requests_same_site_s']['min']} s; {pol['sites_whose_min_gap_below_1s']} of {pol['sites_with_2plus_page_requests']} multi-page sites had two requests less than 1 s apart. User-Agent sent: {esc(list(pol['user_agents_sent'])[0])}.</td></tr>
<tr><td>Throughput (full run)</td><td>{metrics['throughput_sites_per_hour_THIS_RUN_ONLY']} sites/hour at concurrency {metrics['concurrency_used']} – mixed real sites, slow test rows, 1 laptop; <b>not a forecast</b>. Local-only test: 1,000 trivial sites in {t_scale['run_1000']['seconds']} s.</td></tr>
<tr><td>Memory</td><td>Full run peak {manifest['peak_rss_mb']} MB (Python process only; Chromium not included). 150 MB bomb +{t_b150['peak_increase_mb']} MB; 600 MB bomb +{t_b600['peak_increase_mb']} MB. Watchdog (soft 2 GB / hard 3 GB) never triggered. 1,000 local sites: {t_scale['run_1000']['rss_peak_mb']} MB.</td></tr>
<tr><td>Import of 60,000 URLs</td><td>Importer function {t_import['importer_function']['seconds']} s, {t_import['importer_function']['added']} added, +{round(t_import['importer_function']['rss_peak_mb']-t_import['importer_function']['rss_before_mb'])} MB; web upload refused at default limit (2,000,000 characters).</td></tr></table>
<h3>Why the browser fallback and extraction fail (evidence)</h3><p class='small'>Of {b['summary'].get('rendered_has_visible_text_but_crawler_extracted<80',0)} renders where the page had ≥ 500 visible characters but the crawler kept &lt; 80, characters removed by rule: {esc(', '.join(f'{k}: {v:,}' for k,v in list(b['characters_removed_by_rule_in_failed_cases'].items())[:6]))}. Root cause check on 14 sites: 11 had one <code>&lt;body&gt;</code>/<code>&lt;html&gt;</code> element matching a hint that holds 94–100% of the text. Render timing on 7 testable sites: 4 give 80–61,543 characters after network idle versus 0–14 at the moment the crawler reads.</p>""")
A("<h2>6. Top issues</h2><table><tr><th>ID</th><th>Severity</th><th>Title</th><th>CR-IDs</th><th>Repro</th><th>Code location</th><th>Root cause</th><th>Fix direction (not implemented)</th></tr>")
for d in sorted(issues, key=lambda d: (SEV_ORDER[d["sev"]], d["id"])):
    kind = "" if d["kind"] == "defect" else f" <span class='b' style='background:#8250df'>{esc(d['kind'])}</span>"
    A(f"<tr><td>{d['id']}</td><td>{badge(d['sev'])}{kind}</td><td>{esc(d['title'])}</td><td>{esc(d['crs'])}</td><td class='small'>{esc(d['repro'][:160])}</td><td class='small'><code>{esc(d['loc'][:90])}</code></td><td class='small'>{esc(d['cause'][:200])}</td><td class='small'>{esc(d.get('fix','')[:160])}</td></tr>")
A("</table><p class='small'>Full detail for every issue: <code>issues.md</code> / <code>issues.csv</code>. Verdict on every lead from <code>known-findings.md</code>: <code>leads_verdicts.md</code> (23 of 23 confirmed or partly confirmed).</p>")
A("<h3>Leads from the manual code review – all 23 tested</h3><table><tr><th>Lead</th><th>Verdict</th><th>Evidence</th><th>Issue</th></tr>" + "".join(f"<tr><td>{l['lead']}</td><td>{esc(l['verdict'])}</td><td class='small'>{esc(l['evidence'])}</td><td>{esc(l['issues'])}</td></tr>" for l in leads) + "</table>")
ol = J(HERE / "dataset" / "oracle_limitations.json")["rows"]
A("<h2>7. Appendix</h2><h3>Rows not counted as crawler bugs</h3>")
A("<p><b>ORACLE-LIMITATION</b> (separate list; same rule in Phase 2): " + "; ".join(f"{k}: {esc(v)}" for k, v in ol.items()) + "</p>")
lr = list(csv.DictReader((out / "label_review.csv").open(encoding="utf-8-sig")))
fp = J(out / "fresh_probe_review.json")
n_hold = sum(1 for r in lr if r["label_holds"] == "YES")
n_not = sum(1 for r in lr if r["label_holds"] == "NO")
A(f"<p class='small'>Close-out review: every row below was labelled {sum(1 for r in lr if r['label']=='SITE-CHANGED')} SITE-CHANGED or {sum(1 for r in lr if r['label']=='ENV-DEPENDENT')} ENV-DEPENDENT at the end of the run. "
  f"A fresh independent probe of 10 randomly chosen SITE-CHANGED rows (seed 20261012) showed the label holds for {n_hold} and not for {n_not}; those {n_not} were reclassified ({', '.join(r['id'] + ' → ' + r['new_label'] for r in lr if r['label_holds']=='NO')}). "
  "Two of them (T0118, T0575) answered 403 to the original probe and a normal page to the fresh one: such sites alternate and cannot be called 'changed'. Full table: <code>label_review.csv</code>; probe data: <code>fresh_probe_review.json</code>.</p>")
for lab in ("SITE-CHANGED", "ENV-DEPENDENT"):
    lst = [r for r in lr if r["label"] == lab]
    A(f"<details><summary><b>{lab}</b> (label at end of run) – {len(lst)} rows</summary><div class='small scroll'><table><tr><th>Id</th><th>URL</th><th>Expected</th><th>Crawler said</th><th>Probe reading</th><th>Why labelled</th><th>Fresh check</th><th>Final label</th></tr>" +
      "".join(f"<tr><td>{r['id']}</td><td>{esc(r['url'][:56])}</td><td>{esc(r['expected'])}</td><td>{esc(r['crawler_result'][:26])}</td><td>{esc(r['probe_reading'])} {esc(r['probe_detail'][:24])}</td><td>{esc(r['why_labelled'][:150])}</td>"
              f"<td>{esc((r['fresh_probe_reading'] + ' – label ' + ('holds' if r['label_holds']=='YES' else 'does NOT hold')) if r['fresh_probe_reading'] else 'not sampled')}</td><td>{badge(r['final_label_after_review'])}</td></tr>" for r in lst) + "</table></div></details>")
A("<h3>Limitations of this test</h3><ul><li><b>Dataset bias:</b> Wikidata favours large and old organisations. The 'small local business' rows are sites built with Wix / Squarespace / Shopify / Webflow / WordPress and size-filtered (≤ 80 links, ≤ 12,000 characters); they are not proven small or local.</li>"
  "<li><b>Network:</b> tested from Lahore, Pakistan. The ISP resolver fails for some names that public DNS resolves; some sites geo-block or rate-limit. Such rows are ENV-DEPENDENT, and some SITE-CHANGED rows may have the same cause.</li>"
  "<li><b>One run on one day.</b> Sites change; every row has a verification date. 100 smoke-run results were reused (same code, same dataset) so every real site was visited once; only rows that did not match were visited a second time by the probe.</li>"
  "<li><b>Oracle:</b> 19 ambiguous rows use frozen <code>oracle_rule</code> text; a 40-row re-probe agreed on 37/40 (40/40 with a browser for the JavaScript rows).</li>"
  "<li><b>Direct-insert rows:</b> the importer keeps only <code>https://host</code>, so scenario and test-endpoint rows ({manifest['direct_insert_rows']}) were inserted directly; the guard was relaxed only for 127.0.0.1 ports 8800–8862 and 8899.</li>"
  "<li><b>Not tested:</b> Excel upload, web paste box, 200-status challenge pages, Chromium memory, independent scaling of crawl vs AI workers, spreadsheet-formula escaping (export layer).</li>"
  "<li><b>Environment note:</b> the existing test suite created an empty <code>data/</code> folder in the repo root during Step 0; the harness never opened <code>data/websites.db</code>.</li></ul>".replace("{manifest['direct_insert_rows']}", str(manifest["direct_insert_rows"])))
A("<h3>Wrappers (pass-through) and environment</h3><ul>" + "".join(f"<li>{esc(w)}</li>" for w in manifest["wrappers"]) + f"</ul><p class='small'>Python {manifest['python']} · {esc(manifest['os'])} · guard relaxed for {esc(manifest['guard_relaxed_for'])} · safety net: {esc(manifest['safety_net'])} · watchdog soft/hard {manifest['watchdog']['soft_mb']}/{manifest['watchdog']['hard_mb']} MB, hit: {manifest['watchdog']['soft_limit_event']}.</p>")
A("<h3>All rows (filter)</h3><input id='q' placeholder='filter: id, category, url, verdict…'><div class='scroll'><table id='t'><tr><th>Id</th><th>Category</th><th>URL</th><th>Expected</th><th>Actual</th><th>Verdict</th><th>Reason / checks</th></tr>")
for r in rows:
    A(f"<tr><td>{r['id']}</td><td>{esc(r['category'][:32])}</td><td>{esc(r['url'][:70])}</td><td>{esc(r['expected_outcome'])}</td><td>{esc(r['actual'][:34])}</td><td>{badge(r['verdict'])}</td><td class='small'>{esc((r['reason'] or r['checks'])[:200])}</td></tr>")
A("</table></div><script>const q=document.getElementById('q'),t=document.getElementById('t');q.oninput=()=>{const v=q.value.toLowerCase();for(const r of t.rows){if(r.rowIndex===0)continue;r.style.display=r.innerText.toLowerCase().includes(v)?'':'none'}}</script></main></body></html>")
(out / "report.html").write_text("\n".join(H), encoding="utf-8")
print("scorecard:", dict(vc), "| coverage", cov_all, cov_must, "| must pass", must_pass, "| defects", dict(sev_count))
print("match rates (judged): all", m_all, "happy", m_h, "error", m_e, "| report bytes", (out / "report.html").stat().st_size)
