"""Assemble crawl_eval/dataset/testing_URLs.csv from probe evidence + hand-designed rows.

    python build_dataset.py select    -> picks candidates (over-selects volatile categories), writes selection_final.json
    python build_dataset.py write     -> applies re-verification + gold-set results, writes CSV + dataset_summary.md
Seeded (20261010) so the same inputs give the same file.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import select_rows as SR  # noqa: E402
import static_rows as ST  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DS = ROOT / "dataset"
SCRATCH = Path("C:/crawl_eval_data/scratch")
rng = random.Random(20261010)

COLUMNS = ["id", "url", "category", "subcategory", "source_type", "expected_outcome", "expected_status", "expected_pages_note", "tags", "smoke",
           "country", "language", "tech_stack_hint", "why_included", "source_of_url", "verified_at", "verification_method", "notes", "oracle_rule"]

# Fixed judging rules for rows tagged ambiguous-oracle (frozen BEFORE any crawler run; same rules in Phase 1 and Phase 2; never re-judged after results).
# MATCH / PARTIAL / MISMATCH are applied mechanically from the stored status, stored text and harness telemetry.
ORACLE_RULES = {
    "slow headers 20s": "MATCH if status is Unreachable or Failed with a timeout reason, OR status is Crawled with page text present. MISMATCH if the row takes longer than 90 s in total or ends in any other status.",
    "meta-refresh redirect": "MATCH if status is Crawled AND stored text contains >=300 characters taken from the refresh target (final URL differs from the first URL), or status is Redirected. MISMATCH if Crawled with only the stub page (<300 chars, no target content) or any failure status.",
    "JavaScript redirect": "MATCH if status is Crawled AND stored text contains >=300 characters of target-page content. PARTIAL if status is empty/Under Construction/Requires Review (thin result reported as thin). MISMATCH if Crawled with only the stub text, or Failed/Unreachable/Blocked.",
    "cross-domain": "MATCH if status is Redirected. PARTIAL if status is Crawled and telemetry shows the final URL is the target domain (example.com/.org/.net) and stored text comes from it. MISMATCH if the final URL is not recorded anywhere or the status is a failure.",
    "307 (httpbin": "MATCH if status is Redirected. PARTIAL if status is Crawled and telemetry shows the final URL is the target domain (example.com/.org/.net) and stored text comes from it. MISMATCH if the final URL is not recorded anywhere or the status is a failure.",
    "chain of 7": "MATCH if the 7 redirects are followed to example.com (status Redirected or Crawled with target text). MISMATCH if it fails with 'too many redirects' (up to 10 hops must be followed).",
    "9-hop redirect chain": "MATCH if all 9 redirects are followed and the final good page is crawled (status Crawled). MISMATCH if it fails with 'too many redirects' (up to 10 hops must be followed).",
    "malformed robots.txt": "MATCH if status is Crawled (garbage lines ignored, site crawled normally). MISMATCH if Blocked/robots_blocked or Failed.",
    "robots.txt returns 503": "MATCH if status is Blocked (robots) or Unreachable with a robots-related reason and NO page except robots.txt is fetched after a short retry (RFC 9309 s2.3.1.4). MISMATCH if the homepage is fetched.",
    "robots.txt 5xx": "MATCH if status is Blocked/robots-related and the homepage is NOT fetched (RFC 9309 s2.3.1.4). MISMATCH if the homepage is crawled while robots.txt is answering 5xx. ENV-DEPENDENT if the site's robots.txt answers differently at run time (then judged by the run-time probe).",
    "Shift_JIS body": "MATCH if the stored text contains the exact string '株式会社テスト' (or >=50% of its characters readable Japanese). MISMATCH if the text is garbled (mojibake) or empty.",
    "scheme-relative": "MATCH if the import reports it as a duplicate of https://example.com (import:duplicate). MISMATCH if it is added as a new site or rejected as invalid.",
    "full-width characters": "MATCH if the import reports it as a duplicate of https://example.com (import:duplicate). MISMATCH if it is added as a new site or rejected as invalid.",
}


def oracle_rule(row: dict) -> str:
    if "ambiguous-oracle" not in row.get("tags", "").split(";"):
        return ""
    for key, rule in ORACLE_RULES.items():
        if key in row.get("subcategory", ""):
            return rule
    raise SystemExit(f"no oracle_rule for ambiguous row: {row.get('subcategory')} {row.get('url')}")

# ---- quota table (docs/phase-plan.md section 1.3) ----
HAPPY = {
    "Corporate / B2B services": 70, "Manufacturers, industrial, distributors, wholesalers": 60, "E-commerce and retail": 60,
    "SaaS / software / platforms": 60, "Healthcare, education, finance, real estate, non-profit, government": 80,
    "Small local businesses on site builders": 60, "Large multinational enterprises": 30, "Non-English / international": 80,
    "JavaScript-heavy SPAs": 50, "Minimal / one-page / static sites": 30, "Sitemap variants and non-standard navigation": 20,
}
ERR = {
    "Dead domains (NXDOMAIN)": 30, "Parked / for-sale domains": 30, "Under construction / default pages": 25, "Timeouts / refused / slow": 25,
    "SSL/TLS problems": 20, "HTTP errors": 30, "Redirect behaviour": 40, "Bot-protected / WAF": 25, "robots.txt": 20,
    "Non-HTML and heavy content": 15, "Login-walled": 10, "Encoding oddities": 15, "Input handling": 80,
    "Thin / empty / error-only pages": 15, "Crawl traps": 20,
}
QUOTA = {**HAPPY, **ERR}
INST_SUB = {"healthcare": ("hospital", "clinic"), "education": ("university", "school"), "finance": ("bank", "insurance company"),
            "real estate": ("real estate company",), "non-profit": ("non-governmental organization", "non-profit organization", "charitable organization"),
            "government": ("government agency",), "culture": ("museum", "public library")}
INST_TARGET = {"healthcare": 16, "education": 16, "finance": 14, "real estate": 8, "non-profit": 12, "government": 8, "culture": 6}
REGION = {"Germany": "europe", "France": "europe", "Spain": "europe", "Italy": "europe", "Poland": "europe", "Czech Republic": "europe", "Greece": "europe",
          "Turkey": "europe", "Russia": "europe", "Saudi Arabia": "rtl", "United Arab Emirates": "rtl", "Egypt": "rtl", "Morocco": "rtl", "Israel": "rtl", "Iran": "rtl",
          "Japan": "cjk", "People's Republic of China": "cjk", "South Korea": "cjk", "Taiwan": "cjk", "Pakistan": "southasia", "India": "southasia", "Bangladesh": "southasia",
          "Brazil": "latam", "Mexico": "latam", "Argentina": "latam", "Colombia": "latam", "Chile": "latam", "Peru": "latam", "Thailand": "other", "Indonesia": "other"}
REGION_TARGET = {"europe": 18, "rtl": 14, "cjk": 16, "southasia": 18, "latam": 12, "other": 2}
PK_MIN = 8


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def take(items, n, key=None, cap=0.4, exclude=lambda it: False):
    """Deterministic diverse pick: shuffle, then respect a per-key cap (share of n)."""
    items = [i for i in items if not exclude(i)]
    rng.shuffle(items)
    out, per = [], Counter()
    limit = max(1, int(n * cap)) if key else n
    for it in items:
        if len(out) >= n:
            break
        k = key(it) if key else None
        if key and per[k] >= limit:
            continue
        per[k] += 1
        out.append(it)
    if len(out) < n:  # relax the cap before reporting a shortfall
        for it in items:
            if len(out) >= n:
                break
            if it not in out:
                out.append(it)
    return out


def probe_method(r) -> str:
    h = r.get("http") or {}
    rb = r.get("robots") or {}
    sm = r.get("sitemap") or {}
    bits = ["dns(system+1.1.1.1/8.8.8.8)", f"robots:{rb.get('status')}", f"GET:{h.get('status', h.get('error_kind', '-'))}"]
    if (r.get("html") or {}).get("text_len") is not None:
        bits.append(f"text:{r['html']['text_len']}ch")
    if sm:
        bits.append(f"sitemap:{sm.get('kind')}")
    return "+".join(bits)


def base_row(r, cat, sub, outcome, status, why, tags="", notes="", note_pages="") -> dict:
    h = r.get("html") or {}
    return dict(url=r.get("input_url", ""), category=cat, subcategory=sub, source_type="real", expected_outcome=outcome, expected_status=status,
                expected_pages_note=note_pages, tags=tags, country=r.get("country", ""), language=SR.lang_of(r), tech_stack_hint=SR.tech_hint(r),
                why_included=why, source_of_url=f"Wikidata {r.get('qid', '')} P856 (pool {r.get('pool', '')}); label: {r.get('label', '')[:40]}",
                verified_at=(r.get("probed_at") or "")[:10], verification_method=probe_method(r), notes=notes, host=r["host"])


def select() -> None:
    P = SR.load()
    ov = json.loads((SCRATCH / "manual_overrides.json").read_text(encoding="utf-8-sig"))
    # re-run category detection (so overrides apply)
    SR.main_quiet = True
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        SR.main()
    cats = json.loads((SCRATCH / "selection_stage1.json").read_text(encoding="utf-8"))
    for host in ov.get("to_construction", []):
        for k in ("login", "thin", "parked"):
            cats[k] = [i for i in cats.get(k, []) if i["host"] != host]
        cats.setdefault("construction", []).append({"host": host})
    for host in ov.get("to_parked", []):
        cats["construction"] = [i for i in cats.get("construction", []) if i["host"] != host]
        cats.setdefault("parked", []).append({"host": host})
    spa = {}
    spa_file = SCRATCH / "spa_check.jsonl"
    if spa_file.exists():
        for line in spa_file.read_text(encoding="utf-8").split("\n"):
            try:
                x = json.loads(line)
                spa[x["host"]] = x
            except Exception:
                pass
    used: set[str] = set()
    sel: dict[str, list[dict]] = {}
    reserve_factor = 2  # volatile categories: pick extra, re-verify, keep what is stable

    def claim(cat_key, n, label, key=None, cap=0.4, exclude=lambda it: False, pool_filter=None):
        items = [i for i in cats.get(cat_key, []) if i["host"] not in used and (pool_filter is None or pool_filter(i))]
        picked = take(items, n, key=key, cap=cap, exclude=exclude)
        for it in picked:
            used.add(it["host"])
        sel.setdefault(label, []).extend({**it, "_src": cat_key} for it in picked)
        return picked

    # ---------------- error / edge ----------------
    claim("dead", 20 * reserve_factor, "Dead domains (NXDOMAIN)")
    # parked: vendor diversity by NS
    vendor = lambda it: (it.get("ns", "") or it.get("title", "")).split(".")[1] if "." in (it.get("ns", "") or "") else (it.get("title") or "x")[-12:]  # noqa: E731
    claim("parked", 45, "Parked / for-sale domains", key=vendor, cap=0.3)
    claim("construction", 23, "Under construction / default pages")
    claim("login", 8, "Login-walled")
    claim("timeout", 14 * reserve_factor, "Timeouts / refused / slow")
    claim("refused", 6 * reserve_factor, "Timeouts / refused / slow")
    claim("tls", 8 * reserve_factor, "SSL/TLS problems")
    claim("bot", 24 * 2, "Bot-protected / WAF", key=lambda it: it.get("vendor", ""), cap=0.7)
    claim("http_error", 18 * reserve_factor, "HTTP errors", key=lambda it: it.get("st"), cap=0.5)
    for k, n in [("robots_disallow_all", 5), ("robots_crawl_delay", 2), ("robots_html", 2), ("robots_5xx", 2), ("robots_403", 1), ("robots_partial", 1)]:
        claim(k, n * reserve_factor if k in ("robots_5xx", "robots_403") else n, "robots.txt")
    for k, n in [("redirect_http-to-https", 6), ("redirect_www-apex-toggle", 5), ("redirect_cross-domain", 8), ("redirect_long", 3), ("redirect_meta", 2), ("redirect_js", 2)]:
        claim(k, n, "Redirect behaviour")
    claim("encoding", 7, "Encoding oddities")
    claim("encoding_bom", 3, "Encoding oddities")
    # thin: only pages that are still (nearly) empty after real browser rendering
    thin_ok = lambda it: spa.get(it["host"], {}).get("rendered_text_len", 10**6) < 100 and "error" not in spa.get(it["host"], {})  # noqa: E731
    claim("thin", 14, "Thin / empty / error-only pages", pool_filter=thin_ok)
    # ---------------- happy: scarce first ----------------
    spa_ok = lambda it: (spa.get(it["host"], {}).get("rendered_text_len", 0) >= 500 and "error" not in spa.get(it["host"], {}))  # noqa: E731
    claim("spa_candidate", 50, "JavaScript-heavy SPAs", pool_filter=spa_ok, key=lambda it: P[it["host"]].get("country", ""), cap=0.35)
    # thin-looking sites that render fine in a browser are also JS-heavy sites
    thin_js = [i for i in cats.get("thin", []) if i["host"] not in used and spa.get(i["host"], {}).get("rendered_text_len", 0) >= 500]
    short = 50 - len(sel.get("JavaScript-heavy SPAs", []))
    if short > 0:
        for it in take(thin_js, short):
            used.add(it["host"])
            sel["JavaScript-heavy SPAs"].append({**it, "_src": "thin->spa"})
    sm_plan = [("sm_index", 5), ("sm_gz", 4), ("sm_none", 5), ("sm_invalid", 3), ("sm_huge", 3)]
    for k, n in sm_plan:
        claim(k, n, "Sitemap variants and non-standard navigation", key=lambda it: P[it["host"]].get("country", ""), cap=0.5)
    claim("builder", 60, "Small local businesses on site builders", key=lambda it: tuple(it.get("builders", []))[:1], cap=0.4)
    claim("minimal", 30, "Minimal / one-page / static sites")
    # international by region
    intl = [i for i in cats.get("ok_international_s", []) if i["host"] not in used]
    for reg, n in REGION_TARGET.items():
        pool = [i for i in intl if REGION.get(i.get("country", "")) == reg and i["host"] not in used]
        if reg in ("europe", "rtl", "cjk", "latam"):
            pool = [i for i in pool if not str(i.get("lang", "")).startswith("en")]
        picked = take(pool, n, key=lambda it: it.get("country", ""), cap=0.4)
        if reg == "southasia":
            pk = [i for i in pool if i.get("country") == "Pakistan"]
            fixed = take(pk, PK_MIN)
            rest = take([i for i in pool if i not in fixed], n - len(fixed), key=lambda it: it.get("country", ""), cap=0.5)
            picked = fixed + rest
        for it in picked:
            used.add(it["host"])
        sel.setdefault("Non-English / international", []).extend({**it, "_src": f"intl:{reg}"} for it in picked)
    claim("ok_multinational", 30, "Large multinational enterprises", key=lambda it: it.get("country", ""), cap=0.4)
    # institutions by sub-sector
    inst = [i for i in cats.get("ok_institutions_s", []) if i["host"] not in used]
    for sector, n in INST_TARGET.items():
        pool = [i for i in inst if i.get("cls") in INST_SUB[sector] and i["host"] not in used]
        picked = take(pool, n, key=lambda it: it.get("country", ""), cap=0.4)
        for it in picked:
            used.add(it["host"])
        sel.setdefault("Healthcare, education, finance, real estate, non-profit, government", []).extend({**it, "_src": f"inst:{sector}"} for it in picked)
    inst_label = "Healthcare, education, finance, real estate, non-profit, government"
    missing = QUOTA[inst_label] - len(sel.get(inst_label, []))
    if missing > 0:  # some sectors have too few verified sites: fill from the other sectors (any institution site)
        extra_pool = [i for i in cats.get("ok_institutions_s", []) if i["host"] not in used and i.get("cls")]
        for it in take(extra_pool, missing, key=lambda it: it.get("country", ""), cap=0.4):
            used.add(it["host"])
            sel[inst_label].append({**it, "_src": "inst:" + next((s for s, cl in INST_SUB.items() if it.get("cls") in cl), "other")})
    cap_c = lambda it: it.get("country", "")  # noqa: E731
    claim("ok_corporate", 70, "Corporate / B2B services", key=cap_c, cap=0.4)
    claim("ok_manufacturing", 60, "Manufacturers, industrial, distributors, wholesalers", key=cap_c, cap=0.4)
    claim("ok_retail", 60, "E-commerce and retail", key=cap_c, cap=0.4)
    claim("ok_software", 60, "SaaS / software / platforms", key=cap_c, cap=0.4)
    (SCRATCH / "selection_final.json").write_text(json.dumps(sel, ensure_ascii=False), encoding="utf-8")
    print("\n== selected (incl. reserves for volatile categories) vs quota ==")
    for cat in QUOTA:
        print(f"{cat[:62]:62s} real/probe {len(sel.get(cat, [])):4d}   quota {QUOTA[cat]}")
    # reverify + gold lists
    volatile = [i["host"] for c in ("Dead domains (NXDOMAIN)", "Timeouts / refused / slow", "SSL/TLS problems", "HTTP errors", "Bot-protected / WAF", "robots.txt", "Login-walled",
                                     "Thin / empty / error-only pages", "Under construction / default pages", "Parked / for-sale domains") for i in sel.get(c, [])]
    (SCRATCH / "reverify_hosts.json").write_text(json.dumps(sorted(set(volatile))), encoding="utf-8")
    gold_pool = [i["host"] for c in HAPPY for i in sel.get(c, []) if c not in ("Sitemap variants and non-standard navigation",)] + \
                [i["host"] for i in sel.get("Sitemap variants and non-standard navigation", [])]
    (SCRATCH / "gold_hosts.json").write_text(json.dumps(sorted(set(gold_pool))), encoding="utf-8")
    print(len(set(volatile)), "hosts to re-verify;", len(set(gold_pool)), "happy hosts for gold-page lookup")


def klass(r: dict) -> str:
    """Coarse outcome class of a probe record, used to compare probe #1 with the re-verification probe #2."""
    o = r.get("outcome", "")
    if o == "dns_fail":
        return "dead" if (r["dns"].get("rcode") == "NXDOMAIN" and not r["dns"].get("system_ok")) else "dns-other"
    if o in ("robots_disallow", "fetch_error:timeout", "fetch_error:tls"):
        return o
    if o.startswith("fetch_error"):
        return "refused" if (r.get("http") or {}).get("error_kind") in ("refused", "connect") else o
    if o == "fetched":
        st = (r.get("http") or {}).get("status")
        rb = (r.get("robots") or {}).get("status")
        h = r.get("html") or {}
        return f"http:{st}|robots:{rb}|login:{bool(h.get('has_password'))}|bot:{bool(h.get('bot_text'))}|park:{bool(h.get('parked_text'))}"
    return o


def write() -> None:
    P = SR.load()
    sel = json.loads((SCRATCH / "selection_final.json").read_text(encoding="utf-8"))
    rev = {}
    rf = SCRATCH / "reverify.jsonl"
    if rf.exists():
        for line in rf.read_text(encoding="utf-8").split("\n"):
            try:
                x = json.loads(line)
                rev[x["host"]] = x
            except Exception:
                pass
    gold = json.loads((SCRATCH / "gold.json").read_text(encoding="utf-8")) if (SCRATCH / "gold.json").exists() else {}
    spa = {}
    for line in (SCRATCH / "spa_check.jsonl").read_text(encoding="utf-8").split("\n"):
        try:
            x = json.loads(line)
            spa[x["host"]] = x
        except Exception:
            pass
    sv = json.loads((SCRATCH / "statics_verified.json").read_text(encoding="utf-8"))
    dropped = Counter()

    def stable(host: str, cat: str) -> bool:
        if cat in ("Parked / for-sale domains", "Under construction / default pages", "Thin / empty / error-only pages", "Login-walled", "Dead domains (NXDOMAIN)",
                   "Timeouts / refused / slow", "SSL/TLS problems", "HTTP errors", "Bot-protected / WAF", "robots.txt"):
            if host not in rev:
                dropped[(cat, "not re-verified")] += 1
                return False
            same = klass(P[host]) == klass(rev[host])
            if not same:
                dropped[(cat, "re-verification disagreed")] += 1
            return same
        return True

    rows: list[dict] = []

    def real(cat, items, n, maker):
        kept = []
        for it in items:
            if len(kept) >= n:
                break
            if stable(it["host"], cat):
                kept.append(it)
        for it in kept:
            r = P[it["host"]]
            row = maker(it, r)
            if it["host"] in rev and rev[it["host"]].get("probed_at"):
                row["verification_method"] += f"; re-verified {rev[it['host']]['probed_at'][:10]} (same result)"
            rows.append(row)

    def of(cat, *srcs):
        return [i for i in sel.get(cat, []) if i["_src"] in srcs]

    NET = "network-dependent"
    # ---------- happy ----------
    def happy(cat, sub, why, tags=""):
        def m(it, r):
            h = r.get("html") or {}
            row = base_row(r, cat, sub(it) if callable(sub) else sub, "Crawled", "http:200", why, tags=tags)
            row["notes"] = f"home text {h.get('text_len')} chars; title: {h.get('title', '')[:60]}"
            return row
        return m

    for cat, why in [("Corporate / B2B services", "B2B services firm with a normal marketing site"),
                     ("Manufacturers, industrial, distributors, wholesalers", "manufacturer / distributor site with product pages"),
                     ("E-commerce and retail", "retailer / online shop"), ("SaaS / software / platforms", "software or platform company"),
                     ("Large multinational enterprises", "large multinational: heavy site, mega-menu, cookie wall")]:
        real(cat, sel.get(cat, []), QUOTA[cat], happy(cat, lambda it: it.get("cls", "") or "company", why))
    cat = "Healthcare, education, finance, real estate, non-profit, government"
    real(cat, sel.get(cat, []), QUOTA[cat], happy(cat, lambda it: it["_src"].split(":")[1], "institution site (healthcare/education/finance/real estate/non-profit/government/culture)"))
    cat = "Small local businesses on site builders"
    real(cat, sel.get(cat, []), QUOTA[cat], happy(cat, lambda it: "+".join(it.get("builders", [])) or "builder", "small business site built with a site builder"))
    cat = "Non-English / international"
    real(cat, sel.get(cat, []), QUOTA[cat], happy(cat, lambda it: it["_src"].split(":")[1], "non-English or international site (region in subcategory)", tags="geo-risk"))
    cat = "JavaScript-heavy SPAs"

    def spa_maker(it, r):
        s = spa[it["host"]]
        row = base_row(r, cat, "client-side rendered", "Crawled", "http:200", "text is empty over plain HTTP but appears after browser rendering (browser-fallback test)",
                       notes=f"static text {r['html']['text_len']} chars -> rendered {s['rendered_text_len']} chars (independent Playwright check)")
        row["verification_method"] += f"+playwright-render:{s['rendered_text_len']}ch"
        return row
    real(cat, sel.get(cat, []), QUOTA[cat], spa_maker)
    cat = "Minimal / one-page / static sites"
    real(cat, sel.get(cat, []), QUOTA[cat], happy(cat, "one-page / static", "small static site with few links"))
    cat = "Sitemap variants and non-standard navigation"

    def sm_maker(it, r):
        sm = r.get("sitemap") or {}
        sub = {"sm_index": "sitemap index", "sm_gz": "gzip sitemap", "sm_none": "no sitemap", "sm_invalid": "invalid sitemap", "sm_huge": "huge sitemap"}[it["_src"]]
        row = base_row(r, cat, sub, "Crawled", "http:200", "sitemap variant: crawler must still find business pages without crawling the whole sitemap",
                       notes=f"sitemap url {sm.get('url', '')[:80]}; kind {sm.get('kind')}; entries {sm.get('count')}")
        return row
    real(cat, sel.get(cat, []), QUOTA[cat], sm_maker)
    # ---------- errors: real ----------
    real("Dead domains (NXDOMAIN)", sel.get("Dead domains (NXDOMAIN)", []), 20, lambda it, r: base_row(
        r, "Dead domains (NXDOMAIN)", "verified-dead real domain", "Unreachable", "dns:NXDOMAIN", "domain no longer exists (public resolvers say NXDOMAIN)",
        tags=NET, notes="1.1.1.1/8.8.8.8 NXDOMAIN and the local resolver fails; checked twice"))
    park_sub = lambda r: "HugeDomains" if "hugedomains" in json.dumps(r.get("dns", {})).lower() or "HugeDomains" in (r.get("html") or {}).get("title", "") else "parking/for-sale page"  # noqa: E731
    real("Parked / for-sale domains", sel.get("Parked / for-sale domains", []), 30, lambda it, r: base_row(
        r, "Parked / for-sale domains", park_sub(r), "Parked", "http:200", "domain is parked or for sale: not a company site", tags="",
        notes=f"title: {(r.get('html') or {}).get('title', '')[:60]}; NS: {' '.join(r['dns'].get('ns', []))[:70]}"))
    real("Under construction / default pages", sel.get("Under construction / default pages", []), 23, lambda it, r: base_row(
        r, "Under construction / default pages", "placeholder / default server page", "Under Construction", "http:200", "placeholder or default server page, no business content",
        notes=f"title: {(r.get('html') or {}).get('title', '')[:60]}; text {(r.get('html') or {}).get('text_len')} chars"))
    real("Login-walled", sel.get("Login-walled", []), 7, lambda it, r: base_row(
        r, "Login-walled", "password / sign-in wall", "Requires Review", "login-wall", "landing page that only asks for a password or sign-in; crawler must not try to log in",
        notes=f"title: {(r.get('html') or {}).get('title', '')[:60]}"))
    real("Timeouts / refused / slow", of("Timeouts / refused / slow", "timeout"), 14, lambda it, r: base_row(
        r, "Timeouts / refused / slow", "real site: connection/response timeout", "Unreachable", "timeout", "site did not answer within 15 s twice", tags=NET,
        notes="probe timeout 15 s (connect 10 s); may be geo/ISP related"))
    real("Timeouts / refused / slow", of("Timeouts / refused / slow", "refused"), 6, lambda it, r: base_row(
        r, "Timeouts / refused / slow", "real site: connection refused / failed", "Unreachable", "refused", "TCP connection failed twice", tags=NET,
        notes=(r.get("http") or {}).get("error", "")[:100]))
    real("SSL/TLS problems", sel.get("SSL/TLS problems", []), 6, lambda it, r: base_row(
        r, "SSL/TLS problems", "real site: certificate/TLS error", "Unreachable", "tls-error", "HTTPS fails certificate or handshake checks (same result twice)",
        notes=(r.get("http") or {}).get("error", "")[:110] + f"; works without verification: {(r.get('http') or {}).get('works_without_verify')}"))
    code_out = lambda st: "Blocked" if st in (401, 403, 429) else "Failed"  # noqa: E731
    real("HTTP errors", sel.get("HTTP errors", []), 18, lambda it, r: base_row(
        r, "HTTP errors", f"real site: HTTP {it.get('st')}", code_out(it.get("st")), f"http:{it.get('st')}", f"homepage returns HTTP {it.get('st')} (same twice)", tags=NET,
        notes=f"title: {(r.get('html') or {}).get('title', '')[:50]}"))
    real("Bot-protected / WAF", sel.get("Bot-protected / WAF", []), 24, lambda it, r: base_row(
        r, "Bot-protected / WAF", f"challenge page ({it.get('vendor')})", "Blocked", f"http:{it.get('st')}", "bot-challenge page: must be recorded as blocked, never bypassed", tags=NET,
        notes=f"title: {(r.get('html') or {}).get('title', '')[:50]}; markers: {(r.get('html') or {}).get('bot_text')}"))
    rb_maps = {"robots_disallow_all": ("disallow all", "Blocked", "robots", "robots.txt forbids all crawling for everyone; homepage deliberately NOT fetched by us"),
               "robots_crawl_delay": ("crawl-delay", "Crawled", "http:200", "robots.txt has Crawl-delay"),
               "robots_html": ("robots.txt is an HTML page", "Crawled", "http:200", "robots.txt URL returns an HTML page (invalid file)"),
               "robots_5xx": ("robots.txt 5xx", "Blocked", "robots-5xx", "robots.txt answers a server error; RFC 9309 s2.3.1.4 says assume complete disallow"),
               "robots_403": ("robots.txt 401/403", "Crawled", "http:200", "robots.txt denied (4xx): RFC 9309 says treat as no rules"),
               "robots_partial": ("partial disallow", "Crawled", "http:200", "robots.txt disallows some paths only")}
    for key, (sub, out, st, why) in rb_maps.items():
        real("robots.txt", of("robots.txt", key), 13, lambda it, r, sub=sub, out=out, st=st, why=why, key=key: base_row(
            r, "robots.txt", sub, out, st, why, tags="ambiguous-oracle" if key in ("robots_5xx",) else "",
            notes=f"robots status {(r.get('robots') or {}).get('status')}; crawl-delay {(r.get('robots') or {}).get('crawl_delay')}"))
    n_rb = sum(1 for r in rows if r["category"] == "robots.txt")
    # trim robots real to fit quota later
    rd_map = {"redirect_http-to-https": ("http to https", "Crawled"), "redirect_www-apex-toggle": ("www/apex change", "Crawled"),
              "redirect_cross-domain": ("cross-domain redirect", "Redirected"), "redirect_long": ("chain of 3+ hops", "Redirected"),
              "redirect_meta": ("meta-refresh redirect", "Crawled"), "redirect_js": ("JavaScript redirect", "Crawled")}
    for key, (sub, out) in rd_map.items():
        real("Redirect behaviour", of("Redirect behaviour", key), 8, lambda it, r, sub=sub, out=out, key=key: base_row(
            r, "Redirect behaviour", sub, out if key != "redirect_long" or (it.get("final") and SR.reg(urlparse(it["final"]).hostname or "") != SR.reg(r["host"])) else "Crawled",
            (f"final:{(urlparse(it.get('final', '')).hostname or '')[:40]}" if key not in ("redirect_meta", "redirect_js") else key.replace("_", "-")), f"redirect behaviour: {sub}", tags="ambiguous-oracle" if key in ("redirect_meta", "redirect_js") else "",
            notes=f"hops {it.get('hops')}; start {r['input_url'][:50]}; final {it.get('final', r['http'].get('final_url', ''))[:70]}"))
    enc_out = lambda it, r: base_row(r, "Encoding oddities", it.get("enc", "BOM")[:40], "Crawled", "http:200", "legacy or unusual encoding: text must still be readable",
                                     tags="manual-text-review", notes=f"declared encoding: {it.get('enc', '')[:60]}")  # noqa: E731
    real("Encoding oddities", of("Encoding oddities", "encoding"), 7, enc_out)
    real("Encoding oddities", of("Encoding oddities", "encoding_bom"), 3, enc_out)

    def thin_maker(it, r):
        s = spa[it["host"]]
        row = base_row(r, "Thin / empty / error-only pages", "200 OK but (almost) no content", "Requires Review", "http:200",
                       "HTTP 200 homepage with no business content, also after browser rendering", notes=f"static {it['tl']} chars; rendered {s['rendered_text_len']} chars; title: {it.get('title', '')[:40]}")
        row["verification_method"] += f"+playwright-render:{s['rendered_text_len']}ch"
        return row
    real("Thin / empty / error-only pages", sel.get("Thin / empty / error-only pages", []), 12, thin_maker)

    # ---------- static / scenario / test-endpoint rows ----------
    TRIM_HB = {"json", "xml", "image/png", "gzip", "stream-bytes/300000", "robots.txt"}
    badssl_ok = ["expired", "wrong.host", "self-signed", "untrusted-root", "incomplete-chain", "no-common-name", "no-subject", "edellroot", "sha1-intermediate",
                 "mitm-software", "null", "rc4", "dh480", "dh512"]
    statics = []
    for s in ST.rows:
        if s["category"] == "Non-HTML and heavy content" and s["source_type"] == "public-test-endpoint":
            if s["url"].replace("https://httpbin.org/", "") not in TRIM_HB:
                continue
        statics.append(s)
    for h in badssl_ok:
        v = sv.get(f"https://{h}.badssl.com/", {})
        if v.get("error_kind") == "tls":
            statics.append(ST.R("SSL/TLS problems", h.replace(".", " "), f"https://{h}.badssl.com/", "public-test-endpoint", "Unreachable", "tls-error",
                                f"TLS problem: {dict(ST.BADSSL).get(h, h)}", ST.SRC_BS, f"TLS error confirmed {v.get('verified_at', '')[:10]}: {v.get('error', '')[:60]}"))
    for s in statics:
        v = sv.get(s["url"], {})
        row = dict(s)
        row.setdefault("expected_pages_note", "")
        try:
            static_host = urlparse(s["url"]).hostname or ""
        except ValueError:  # deliberately malformed input rows (e.g. 'http://[invalid')
            static_host = ""
        row.update(country="", language="", tech_stack_hint="", host=static_host)
        if v:
            row["verified_at"] = v.get("verified_at", "")[:10]
            if s["verification_method"].startswith(("GET", "redirect chain", "robots.txt")):
                row["verification_method"] += f"; observed status {v.get('status', v.get('error_kind'))}, {v.get('elapsed_ms')} ms"
        else:
            row["verified_at"] = now()
        if "scenario" in s["tags"] or s["source_type"] == "local-scenario":
            row["verified_at"] = "2026-10-10"
        if s["category"] == "Input handling":
            row["verified_at"] = now()
        row["tags"] = ";".join(x for x in [s["tags"], "network-dependent" if s["source_type"] == "public-test-endpoint" and s["category"] != "Input handling" else ""] if x)
        rows.append(row)

    # ---------- attach gold pages / flags ----------
    gold_count = 0
    for r in rows:
        g = gold.get(r.get("host", ""))
        if g and r["source_type"] == "real" and r["category"] in HAPPY:
            r["expected_pages_note"] = "Gold key pages (verified 200): " + "; ".join(f"{k}: {v}" for k, v in g.items())
            r["tags"] = ";".join(x for x in [r.get("tags", ""), "gold"] if x)
            gold_count += 1
    scenario_gold = {SC_URL: "gold: /what-we-do, /who-we-serve" for SC_URL in []}
    # ---------- order, trim to quota, ids ----------
    cat_order = list(QUOTA)
    by = defaultdict(list)
    for r in rows:
        by[r["category"]].append(r)
    final: list[dict] = []
    shortfall = {}
    over = {}
    for cat in cat_order:
        items = by.get(cat, [])
        # keep static rows first (designed), then real, trimming the real ones if over quota
        if len(items) > QUOTA[cat]:
            statics_ = [i for i in items if i["source_type"] != "real"]
            reals = [i for i in items if i["source_type"] == "real"]
            items = statics_ + reals[: max(0, QUOTA[cat] - len(statics_))]
            if len(items) > QUOTA[cat]:
                items = items[: QUOTA[cat]]
        shortfall[cat] = QUOTA[cat] - len(items)
        final.extend(items)
    # smoke subset: ~10% of each category, every category >=1, avoid heavy/slow scenario rows
    heavy = ("8804", "8805", "8807", "8808", "8817", "8801", "8802", "8803")
    smoke_pick = {}
    for cat in cat_order:
        items = [r for r in final if r["category"] == cat]
        pool = [r for r in items if not any(f":{p}/" in r["url"] for p in heavy)] or items
        n = max(1, round(len(items) / 10)) if items else 0
        smoke_pick[cat] = rng.sample(pool, min(n, len(pool))) if pool else []
    total_smoke = sum(len(v) for v in smoke_pick.values())
    cats_by_size = sorted(cat_order, key=lambda c: -len([r for r in final if r["category"] == c]))
    i = 0
    while total_smoke > 100:
        c = cats_by_size[i % len(cats_by_size)]
        if len(smoke_pick[c]) > 1:
            smoke_pick[c].pop()
            total_smoke -= 1
        i += 1
    while total_smoke < 100:
        c = cats_by_size[i % len(cats_by_size)]
        items = [r for r in final if r["category"] == c and r not in smoke_pick[c] and not any(f":{p}/" in r["url"] for p in heavy)]
        if items:
            smoke_pick[c].append(rng.choice(items))
            total_smoke += 1
        i += 1
    smoke_ids = {id(r) for v in smoke_pick.values() for r in v}
    # manual text review flag on 40 more happy rows without gold
    cand = [r for r in final if r["category"] in HAPPY and r["source_type"] == "real" and "gold" not in r.get("tags", "") and "manual-text-review" not in r.get("tags", "")]
    for r in rng.sample(cand, min(40, len(cand))):
        r["tags"] = ";".join(x for x in [r.get("tags", ""), "manual-text-review"] if x)
    out_rows = []
    for n, r in enumerate(final, 1):
        r["id"] = f"T{n:04d}"
        r["smoke"] = "Y" if id(r) in smoke_ids else "N"
        r["oracle_rule"] = oracle_rule(r)
        out_rows.append({c: r.get(c, "") for c in COLUMNS})
    DS.mkdir(exist_ok=True)
    with (DS / "testing_URLs.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(out_rows)
    sha = hashlib.sha256((DS / "testing_URLs.csv").read_bytes()).hexdigest()
    print(f"wrote {len(out_rows)} rows; smoke {sum(1 for r in out_rows if r['smoke'] == 'Y')}; gold {gold_count}; sha256 {sha[:16]}")
    for cat in cat_order:
        have = len([r for r in out_rows if r['category'] == cat])
        print(f"{cat[:60]:60s} {have:4d} / {QUOTA[cat]:3d}  {'SHORT ' + str(QUOTA[cat] - have) if have < QUOTA[cat] else ''}")
    print("dropped by re-verification:", dict(dropped))
    (SCRATCH / "build_stats.json").write_text(json.dumps({"shortfall": {c: QUOTA[c] - len([r for r in out_rows if r['category'] == c]) for c in cat_order},
                                                          "dropped": {f"{a}|{b}": n for (a, b), n in dropped.items()}, "sha256": sha, "gold": gold_count}), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "select":
        select()
    elif len(sys.argv) > 1 and sys.argv[1] == "write":
        write()
    else:
        sys.exit("usage: build_dataset.py select|write")

