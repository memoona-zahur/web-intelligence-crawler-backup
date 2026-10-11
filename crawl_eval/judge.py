"""Mechanical judging of one dataset row: expected vs actual. Same code is used in Phase 1 and Phase 2 (never edited after results are seen).

Verdicts: MATCH, PARTIAL, MISMATCH, ENV-DEPENDENT, SITE-CHANGED, HARNESS-ERROR, NOT-RUN.
Judge rules come from docs/crawler-requirements.md (via the dataset's oracle), `oracle_rule` (ambiguous rows) and the 'pass:' text in `notes`.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

STATUS_WORD = {"crawled": "Crawled", "empty": "Under Construction", "unreachable": "Unreachable", "blocked": "Blocked", "robots_blocked": "Blocked",
               "invalid": "Invalid", "failed": "Failed"}
# Words the crawler's status vocabulary cannot express at all (CR-B06): a row expecting one of these can only be MATCHed if the crawler says something equivalent.
NO_SUCH_STATUS = {"Parked", "Redirected", "Requires Review"}


def purpose(url: str) -> str:
    p = urlparse(url).path.lower()
    if p.endswith("robots.txt"):
        return "robots"
    if p.endswith((".xml", ".gz")) or "sitemap" in p:
        return "sitemap"
    return "page"


def port_of(url: str):
    m = re.search(r"127\.0\.0\.1:(88\d\d)", url)
    return int(m.group(1)) - 8800 if m else None


def sections(text: str):
    """[(label, url, body)] from the crawler's clean_text format."""
    out = []
    for m in re.finditer(r"^=== PAGE: (.*?) \| (\S+)\n(.*?)(?=^=== PAGE: |\Z)", text or "", re.M | re.S):
        out.append((m.group(1), m.group(2), m.group(3)))
    return out


def body_chars(text: str) -> int:
    n = 0
    for _l, _u, b in sections(text):
        n += sum(len(line) for line in b.splitlines() if not line.startswith("Retrieved via"))
    return n


def classify_probe(p: dict | None) -> str:
    """The post-crawl probe's own reading of the site (same words as the oracle), or 'unknown'."""
    if not p:
        return "unknown"
    if p.get("dns_dead"):
        return "Unreachable"
    return p.get("predicted") or "unknown"


# Which probe readings are compatible with each expected outcome (thin / placeholder / parked pages look alike to a short probe).
COMPAT = {"Crawled": {"Crawled"}, "Redirected": {"Crawled"}, "Parked": {"Parked", "Requires Review", "Under Construction"},
          "Under Construction": {"Under Construction", "Requires Review", "Parked"}, "Requires Review": {"Requires Review", "Under Construction", "Parked"},
          "Blocked": {"Blocked"}, "Failed": {"Failed"}, "Unreachable": {"Unreachable"}}


def probe_agrees(expected: str, cls: str, category: str = "", subcategory: str = "") -> bool | None:
    if cls == "unknown" or expected not in COMPAT:
        return None
    if (category == "JavaScript-heavy SPAs" or "JavaScript redirect" in subcategory) and cls in ("Crawled", "Parked", "Under Construction", "Requires Review"):
        return None  # a plain GET cannot execute JavaScript, so it cannot judge the CONTENT of these rows (unreachable / blocked / failed readings still count; JS-redirect rows added at Phase 1 close-out)
    return cls in COMPAT[expected]


def checks(row: dict, c: dict) -> list[tuple[str, bool, str]]:
    """Pass criteria from the dataset's 'pass:' notes. Returns [(name, passed, detail)]."""
    out = []
    reqs = [r for r in c.get("requests", []) if r.get("origin") == "crawler"]
    pages = [r for r in reqs if purpose(r["url"]) == "page"]
    ok_pages = {r["url"] for r in pages if r.get("status") == 200}
    text = c.get("clean_text") or ""
    n = port_of(row["url"])
    url = row["url"]
    cat = row["category"]

    def count(sub):
        return sum(1 for u in ok_pages if sub in u)

    if cat == "Crawl traps" and n not in (49, 50):
        out.append(("pages<=10", len(ok_pages) <= 10, f"{len(ok_pages)} distinct pages fetched"))
        spec = {44: ("/list?page=", 1), 45: ("/day/", 1), 48: ("sort=", 1), 55: ("/x-", 1), 57: ("/mirror/", 3), 59: ("/feed?", 1), 60: ("/t/", 1)}
        if n in spec:
            sub, lim = spec[n]
            out.append((f"{sub} fetched<={lim}", count(sub) <= lim, f"{count(sub)} fetched"))
        if n == 46:
            paths = [re.sub(r"^/s/\d+", "", urlparse(u).path) for u in ok_pages]
            dup = [p for p in set(paths) if paths.count(p) > 1]
            out.append(("each page once", not dup, f"repeated: {dup[:3]}"))
        if n == 52:
            out.append(("no /a/a/a", not any("/a/a/a" in u for u in ok_pages), ""))
        if n == 54:
            out.append(("no /docs/docs/docs", not any("/docs/docs/docs" in u for u in ok_pages), ""))
        if n == 56:
            for base in ("/about", "/services"):
                k = sum(1 for u in ok_pages if re.sub(r"(/index\.html)?/?$", "", urlparse(u).path.lower()) == base)
                out.append((f"{base} variants fetched<=1", k <= 1, f"{k} variants fetched"))
        if n == 58:
            sm = [r for r in reqs if purpose(r["url"]) == "sitemap" and r.get("status") == 200]
            out.append(("sitemap files<=5", len(sm) <= 5, f"{len(sm)} sitemap files"))
    if cat == "Crawl traps" and n in (49, 50):
        out.append(("stops quickly", len([r for r in reqs]) <= 15, f"{len(reqs)} requests"))
    if n == 10 or "127.0.0.2" in url:
        out.append(("secret absent", "SECRET-TOKEN-4711" not in text, ""))
        sent = [r for r in reqs if (urlparse(r["url"]).hostname == "127.0.0.2") and not r.get("safety_net_blocked")]
        out.append(("no request SENT to host 127.0.0.2", not sent, f"{len(sent)} sent" if sent else ""))
    if n == 18:
        out.append(("no page fetched", len(pages) == 0, f"{len(pages)} page requests"))
    if n == 19:
        out.append(("/about never fetched", not any(urlparse(r["url"]).path.rstrip("/") == "/about" for r in pages), ""))
    if n == 20:
        ts = sorted((r["t"] for r in pages))
        gaps = [b - a for a, b in zip(ts, ts[1:])]
        out.append(("gap>=9.5 s", (not gaps) or min(gaps) >= 9.5, f"min gap {min(gaps):.1f}s" if gaps else "single page"))
    if n in (24, 25):
        late = [r for r in reqs if purpose(r["url"]) == "page"]
        gaps = [b["t"] - a.get("t_end", a["t"]) for a, b in zip(late, late[1:])]
        out.append(("honours Retry-After 5s", (not gaps) or min(gaps) >= 4.5, f"{len(late)} requests, min gap {min(gaps):.1f}s" if gaps else f"{len(late)} request"))
    if n == 33:
        out.append(("umlauts readable", "Café Müller" in text and "Größere" in text, ""))
    if n == 34:
        out.append(("Japanese readable", "株式会社テスト" in text, ""))
    if n == 35:
        out.append(("no BOM char, text present", "﻿" not in text and "BOM page" in text, ""))
    if n == 36:
        out.append(("UTF-16 decoded", "UTF16" in text, ""))
    if n == 16:
        got = {urlparse(r["url"]).path for r in pages}
        out.append(("found /what-we-do and /who-we-serve", {"/what-we-do", "/who-we-serve"} <= got, str(sorted(got))))
    if n in (7, 8, 15, 17):
        out.append(("finished within 60 s", (c.get("seconds") or 0) <= 60, f"{c.get('seconds')} s"))
    if any(r.get("safety_net_blocked") for r in reqs):
        out.append(("guard stopped private target", False, "SAFETY_NET_BLOCKED: " + ", ".join(sorted({r['url'][:60] + ' -> ' + r['blocked_ip'] for r in reqs if r.get('safety_net_blocked')}))))
    return out


def judge(row: dict, c: dict) -> dict:
    """c: imp (import decision), site (db row or None), clean_text, status, error, pages, seconds, requests, final_url, probe, via, secret_stored"""
    exp, exps, cat, sub = row["expected_outcome"], row["expected_status"], row["category"], row["subcategory"]
    res = {"actual": "NOT-RUN", "status_verdict": "", "checks": [], "verdict": "NOT-RUN", "reason": "", "env_flags": []}
    imp = c.get("imp") or {}
    st = c.get("status")
    actual = STATUS_WORD.get(st, "NOT-RUN") if st else "NOT-RUN"
    res["actual"] = actual
    text = c.get("clean_text") or ""
    # ---------------- import-level rows ----------------
    if cat == "Input handling":
        dec = imp.get("decision", "none")
        want = exps.split(":", 1)[1] if exps.startswith("import:") else None
        if exps == "dns:loopback":
            ok = actual == "Invalid" or (not st and dec == "invalid")
            res.update(actual=f"import:{dec}/crawl:{actual}", status_verdict="MATCH" if ok else "MISMATCH", reason="public name resolving to loopback must end as Invalid at fetch time" if not ok else "")
            res["checks"] = checks(row, c)
        else:
            ok = dec == {"invalid": "invalid", "duplicate": "duplicate", "added": "added"}.get(want, "?")
            res.update(actual=f"import:{dec}" + (f"/crawl:{actual}" if st else ""), status_verdict="MATCH" if ok else "MISMATCH")
            if not ok:
                res["reason"] = (f"importer RAISED {imp.get('error')} and the whole import batch was lost" if dec == "crash"
                                 else f"importer said '{dec}', expected '{want}'")
            if ok and want == "added" and exp in ("Crawled", "Redirected", "Failed"):
                ok2 = actual == exp or (exp == "Redirected" and actual == "Crawled")
                res["status_verdict"] = "MATCH" if ok2 else "MISMATCH"
                if not ok2:
                    res["reason"] = f"import ok but crawl status {actual}, expected {exp}"
            if "credentials" in sub:
                res["checks"].append(("credentials not stored", not c.get("secret_stored"), "password text found in stored original_url" if c.get("secret_stored") else ""))
            if "oracle_rule" in row and row["oracle_rule"] and ("scheme-relative" in sub or "full-width" in sub):
                pass
        res["checks"] += checks(row, c) if st else []
        return finish(row, c, res)
    # ---------------- crawl rows ----------------
    if not st:
        res.update(verdict="NOT-RUN", reason="no crawl result (site not created or not run)")
        return res
    # oracle_rule rows
    if row.get("oracle_rule"):
        v, why = apply_oracle(row, c, actual, text)
        res["status_verdict"] = v
        res["reason"] = why
    else:
        if actual == exp:
            res["status_verdict"] = "MATCH"
        elif exp in NO_SUCH_STATUS:
            res["status_verdict"] = "MISMATCH"
            res["reason"] = f"expected '{exp}', which the crawler's status vocabulary cannot express (CR-B06); crawler said '{actual}' ({c.get('error')})"
        else:
            res["status_verdict"] = "MISMATCH"
            res["reason"] = f"expected {exp}, crawler said {actual}: {c.get('error') or ''}"
    res["checks"] = checks(row, c)
    return finish(row, c, res)


def apply_oracle(row, c, actual, text):
    sub = row["subcategory"]
    err = (c.get("error") or "").lower()
    fu = c.get("final_url") or ""
    home_only = [r for r in c.get("requests", []) if r.get("origin") == "crawler" and purpose(r["url"]) == "page"]
    if "slow headers" in sub:
        if (c.get("seconds") or 0) > 90:
            return "MISMATCH", f"took {c.get('seconds')} s (>90 s)"
        ok = (actual in ("Unreachable", "Failed") and "timeout" in err) or (actual == "Crawled" and text)
        return ("MATCH", "") if ok else ("MISMATCH", f"status {actual}: {c.get('error')}")
    if "meta-refresh" in sub or "JavaScript redirect" in sub:
        if actual == "Crawled" and body_chars(text) >= 300:
            return "MATCH", ""
        if "JavaScript" in sub and actual in ("Under Construction", "Requires Review"):
            return "PARTIAL", "reported as thin/empty instead of following the JavaScript redirect"
        return "MISMATCH", f"status {actual}, {body_chars(text)} chars of content ({c.get('error')})"
    if "307 (httpbin" in sub or "cross-domain" in sub:
        if actual == "Redirected":
            return "MATCH", ""
        host = urlparse(fu).hostname or ""
        if actual == "Crawled" and host.startswith("example.") and "example" in text.lower():
            return "PARTIAL", f"Crawled with final URL {fu} (the crawler has no Redirected status; the final URL is not stored in the DB)"
        return "MISMATCH", f"status {actual}, final url '{fu}' ({c.get('error')})"
    if "chain of 7" in sub:
        host = urlparse(fu).hostname or ""
        return ("MATCH", "") if actual in ("Redirected", "Crawled") and host.startswith("example.") else ("MISMATCH", f"status {actual}: {c.get('error')}")
    if "9-hop" in sub:
        return ("MATCH", "") if actual == "Crawled" else ("MISMATCH", f"status {actual}: {c.get('error')}")
    if "malformed robots" in sub:
        return ("MATCH", "") if actual == "Crawled" else ("MISMATCH", f"status {actual}: {c.get('error')}")
    if "robots.txt returns 503" in sub or "robots.txt 5xx" in sub:
        if home_only:
            return "MISMATCH", f"homepage was fetched ({len(home_only)} page requests) although robots.txt answers 5xx"
        return ("MATCH", "") if actual in ("Blocked", "Unreachable") else ("MISMATCH", f"status {actual}")
    if "Shift_JIS" in sub:
        return ("MATCH", "") if "株式会社テスト" in text else ("MISMATCH", f"Japanese text not readable (status {actual}, {len(text)} chars)")
    return "MISMATCH", f"no oracle rule implemented for '{sub}'"


def finish(row, c, res):
    checks_ = res["checks"]
    failed = [n for n, ok, _d in checks_ if not ok]
    sv = res["status_verdict"]
    verdict = sv
    if sv in ("MATCH", "PARTIAL") and failed:
        verdict = "MISMATCH"
        res["reason"] = (res["reason"] + "; " if res["reason"] else "") + "failed checks: " + ", ".join(failed)
    # environment / site-change overlay (only for real sites; never for tests we control)
    p = c.get("probe")
    cls = classify_probe(p)
    tags = (row.get("tags") or "").split(";")
    flags = []
    if p and not p.get("dns_system_ok") and p.get("dns_public_ok"):
        flags.append("DNS-ISP-MISMATCH")
    # If the crawler's OWN telemetry reproduces the premise of the row (e.g. robots.txt really answered 5xx), the site did not change: it is a crawler result.
    reqs = [r for r in c.get("requests", []) if r.get("origin") == "crawler"]
    premise_seen = False
    exps = row["expected_status"]
    if exps == "robots-5xx":
        premise_seen = any(purpose(r["url"]) == "robots" and (r.get("status") or 0) >= 500 for r in reqs)
    elif exps.startswith("http:") and exps[5:].isdigit() and exps != "http:200":  # a plain 200 proves nothing about page CONTENT
        premise_seen = any(r.get("status") == int(exps[5:]) for r in reqs if purpose(r["url"]) == "page")
    if premise_seen:
        flags.append("premise reproduced in crawler telemetry")
    if row["source_type"] != "local-scenario" and verdict in ("MISMATCH", "PARTIAL") and not premise_seen:
        agrees = probe_agrees(row["expected_outcome"], cls, row["category"], row["subcategory"])
        any_dns_ok = p.get("dns_any_ok", bool(p.get("dns_system_ok") or p.get("dns_public_ok"))) if p else False
        crawler_dns_fail = "cannot resolve host" in (c.get("error") or "")
        visible_kind = {"Crawled", "Redirected", "Parked", "Under Construction", "Requires Review"}
        if "DNS-ISP-MISMATCH" in flags or (crawler_dns_fail and any_dns_ok and row["expected_outcome"] in visible_kind):
            verdict = "ENV-DEPENDENT"
            flags.append("crawler's DNS lookup failed on this network, but the name resolves (public resolver or a later try): ISP resolver problem")
        elif cls == "Unreachable" and any_dns_ok and not (p or {}).get("dns_dead") and row["expected_outcome"] in visible_kind and not c.get("status") == "crawled":
            verdict = "ENV-DEPENDENT"
            flags.append("name resolves but the site cannot be reached from this network now (timeout / connection error in crawler AND probe): connectivity or geo/ISP effect")
        elif ("network-dependent" in tags or "geo-risk" in tags) and cls in ("Unreachable", "Blocked") and row["expected_outcome"] == "Crawled":
            verdict = "ENV-DEPENDENT"
            flags.append(f"run-time probe reads the site as '{cls}' from this network")
        elif agrees is False:
            verdict = "SITE-CHANGED"
            flags.append(f"run-time probe reads the site as '{cls}' (dataset expected '{row['expected_outcome']}')")
    res["env_flags"] = flags
    res["verdict"] = verdict
    res["probe_class"] = cls
    return res
