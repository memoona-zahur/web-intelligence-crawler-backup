"""Stage 1: decide which probed domains qualify for which dataset category (evidence from probe.py only).

    python select_rows.py             -> prints availability per category and writes C:/crawl_eval_data/scratch/selection.json
Rules never look at the existing crawler's behaviour. Small/risky categories are reviewed by hand afterwards
(manual_overrides.json: {"exclude": [hosts], "force": {host: category}}).
"""
from __future__ import annotations

import glob
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SEED = 20261010
SCRATCH = Path("C:/crawl_eval_data/scratch")
PROBES = SCRATCH / "probe"
rng = random.Random(SEED)

SLD = {"co", "com", "org", "net", "gov", "edu", "ac", "or", "ne", "go"}
BLOCK_HOSTS = ("facebook.", "linkedin.", "twitter.", "instagram.", "youtube.", "tiktok.", "pinterest.", "reddit.", "wikipedia.", "wikimedia.")
PARKING_NS = ("sedoparking", "parkingcrew", "bodis.com", "above.com", "dan.com", "afternic", "hugedomains", "parklogic", "namebrightdns",
              "cashparking", "fabulous.com", "voodoo.com", "skenzo", "smartname", "domainsponsor", "trafficz", "undeveloped.com", "buydomains", "park-mx")
MARKETPLACES = ("snapnames", "sedo.", "godaddy.", "dan.com", "afternic", "hugedomains", "namecheap", "nameshift", "flippa", "squadhelp", "brandbucket")
WAF_VENDOR_HINTS = {"cloudflare": ("just a moment", "attention required", "cf-chl", "cloudflare"), "imperva": ("incapsula", "pardon our interruption", "request unsuccessful"),
                    "datadome": ("datadome",), "perimeterx": ("perimeterx", "press & hold"), "akamai": ("access denied", "akamai", "reference #"),
                    "captcha": ("captcha", "are you a robot", "verify you are human")}


def reg(host: str) -> str:
    parts = host.lower().removeprefix("www.").split(".")
    if len(parts) >= 3 and parts[-2] in SLD and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def load() -> dict[str, dict]:
    out = {}
    for f in glob.glob(str(PROBES / "*.jsonl")):
        for line in Path(f).read_text(encoding="utf-8").split("\n"):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                print("skipped a damaged probe line in", Path(f).name, file=sys.stderr)
                continue
            if r["outcome"].startswith("probe_error") or r.get("host", "?") == "?":
                continue
            out[r["host"]] = r
    return out


def lang_of(r: dict) -> str:
    h = r.get("html") or {}
    lang = (h.get("lang") or "").split("-")[0].split("_")[0]
    if lang and len(lang) <= 3:
        return lang
    sc = h.get("scripts") or {}
    top = max(sc, key=sc.get) if sc and max(sc.values()) > 20 else ""
    return {"arabic": "ar", "cjk": "cjk", "devanagari": "hi", "cyrillic": "ru", "latin": "en?"}.get(top, "")


def status(r): return (r.get("http") or {}).get("status")
def html(r): return r.get("html") or {}
def tlen(r): return html(r).get("text_len", 0)


BAD_TITLE = re.compile(r"error|not found|404|403|forbidden|access denied|hosted by|default|coming soon|under construction|maintenance|wartung|index of|domain|parked|for sale|welcome to nginx|apache|test page|it works", re.I)


def good_home(r) -> bool:
    return (r["outcome"] == "fetched" and status(r) == 200 and tlen(r) >= 300 and not html(r).get("adult_text")
            and not BAD_TITLE.search(html(r).get("title", "") or "")
            and not html(r).get("bot_text") and not html(r).get("parked_text") and not html(r).get("construction_text")
            and not html(r).get("meta_refresh") and not html(r).get("has_password"))


def tech_hint(r) -> str:
    h, s = html(r), (r.get("http") or {}).get("headers", {})
    bits = list(h.get("builders", []))
    if h.get("generator"):
        bits.append("gen:" + h["generator"][:30])
    if h.get("spa_marker"):
        bits.append("spa-marker")
    if s.get("server"):
        bits.append("server:" + s["server"][:20])
    return ";".join(bits)


def chain_info(r):
    chain = (r.get("http") or {}).get("chain") or []
    hops = max(0, len(chain) - 1)
    if not chain:
        return {"hops": 0}
    first, last = urlparse(chain[0][0]), urlparse((r["http"].get("final_url") or chain[-1][0]))
    fh, lh = (first.hostname or "").lower(), (last.hostname or "").lower()
    kind = "none"
    if hops:
        if reg(fh) != reg(lh):
            kind = "cross-domain"
        elif first.scheme == "http" and last.scheme == "https" and fh.removeprefix("www.") == lh.removeprefix("www."):
            kind = "http-to-https" if fh == lh else "http-to-https+www-change"
        elif fh.removeprefix("www.") == lh.removeprefix("www.") and fh != lh:
            kind = "www-apex-toggle"
        else:
            kind = "same-site-path"
    return {"hops": hops, "kind": kind, "final": r["http"].get("final_url", ""), "first": chain[0][0]}


def main() -> None:
    P = load()
    overrides = {}
    ov_file = SCRATCH / "manual_overrides.json"
    if ov_file.exists():
        overrides = json.loads(ov_file.read_text(encoding="utf-8-sig"))
    excl = set(overrides.get("exclude", []))
    pools = Counter(r.get("pool", "") for r in P.values())
    print(len(P), "probed domains;", dict(pools))
    cats: dict[str, list[dict]] = defaultdict(list)
    used: set[str] = set()

    def add(cat, r, **extra):
        cats[cat].append({"host": r["host"], **extra})

    hosts = sorted(P)
    rng.shuffle(hosts)
    hosts = [h for h in hosts if not any(b in h for b in BLOCK_HOSTS) and h not in excl]

    # ---- error / edge categories (scarce first) ----
    for h in hosts:
        r = P[h]
        d = r["dns"]
        ns = " ".join(d.get("ns", []))
        # dead
        if r["outcome"] == "dns_fail" and d.get("rcode") == "NXDOMAIN" and not d.get("system_ok"):
            add("dead", r); continue
        if r["outcome"] == "dns_fail":
            continue
        # robots
        rb = r.get("robots") or {}
        if r["outcome"] == "robots_disallow":
            add("robots_disallow_all", r); continue
        if r["outcome"] == "fetch_error:tls":
            add("tls", r, msg=(r["http"].get("error") or "")[:90], without=r["http"].get("works_without_verify")); continue
        if r["outcome"] == "fetch_error:timeout":
            add("timeout", r); continue
        if r["outcome"] in ("fetch_error:connect",) or (r["outcome"].startswith("fetch_error") and r["http"].get("error_kind") == "refused"):
            add("refused", r); continue
        if r["outcome"] != "fetched":
            continue
        st, hh = status(r), html(r)
        if hh.get("adult_text"):
            continue
        park_ns = any(p in ns for p in PARKING_NS)
        title = (hh.get("title") or "").lower()
        if hh and ((park_ns and tlen(r) < 400) or re.search(r"for sale|is parked|domain.{0,20}expired|buy this domain", title)
                   or (any(k in ("this domain is for sale", "domain may be for sale", "buy this domain", "inquire about this domain", "this domain name is parked",
                                 "this web page is parked", "this domain has expired") for k in hh.get("parked_text", [])) and tlen(r) < 9000)) \
                and not any(m in h for m in MARKETPLACES):
            add("parked", r, ns=ns[:60], title=hh.get("title", "")[:50]); continue
        if hh and hh.get("construction_text") and tlen(r) < 700:
            add("construction", r, hits=hh["construction_text"], title=hh.get("title", "")[:50]); continue
        bot = hh.get("bot_text") or []
        hdr = (r["http"].get("headers") or {})
        if hh and st in (403, 429, 503, 202) and (bot or hdr.get("cf-mitigated")) and tlen(r) < 3000:
            vendor = next((v for v, keys in WAF_VENDOR_HINTS.items() if any(k in " ".join(bot) + " " + json.dumps(hdr).lower() for k in keys)), "other")
            add("bot", r, vendor=vendor, st=st); continue
        if hh.get("has_password") and tlen(r) < 500 and st == 200:
            add("login", r, title=hh.get("title", "")[:50]); continue
        enc = r.get("encoding", "")
        if st == 200 and tlen(r) >= 200 and re.search(r"(iso-8859|windows-12|shift_jis|euc-|gb2312|gbk|big5|koi8|tis-620|euc_kr)", enc):
            add("encoding", r, enc=enc); continue
        if st == 200 and "utf-8-bom" in enc and tlen(r) >= 200:
            add("encoding_bom", r, enc=enc)
        if st in (401, 404, 410, 500, 502, 503, 504, 400, 405, 409, 451) and not bot:
            add("http_error", r, st=st); continue
        if st == 403 and not bot and tlen(r) < 3000:
            add("http_error", r, st=st); continue
        if st == 429:
            add("rate_limited", r); continue
        if st == 200 and not hh.get("spa_marker") and (tlen(r) < 60 or (hh.get("error_title") and tlen(r) < 400)):
            add("thin", r, title=hh.get("title", "")[:50], tl=tlen(r)); continue
        ci = chain_info(r)
        if ci["hops"] and st == 200:
            add("redirect_" + ci["kind"], r, hops=ci["hops"], final=ci["final"][:90])
            if ci["hops"] >= 3:
                add("redirect_long", r, hops=ci["hops"], final=ci["final"][:90])
        if hh.get("meta_refresh") and tlen(r) < 300:
            add("redirect_meta", r, mr=hh["meta_refresh"][:60])
        if hh.get("js_redirect") and tlen(r) < 150 and not hh.get("spa_marker"):
            add("redirect_js", r)
        if (rb.get("status") in (500, 502, 503, 504)) and st == 200:
            add("robots_5xx", r, rs=rb["status"])
        if rb.get("status") == 200 and "html" in (rb.get("ctype") or "").lower() and st == 200 and good_home(r):
            add("robots_html", r)
        if rb.get("status") in (401, 403) and good_home(r):
            add("robots_403", r)
        if rb.get("crawl_delay") and good_home(r):
            add("robots_crawl_delay", r, cd=rb["crawl_delay"])
        if rb.get("status") == 404 and good_home(r):
            add("robots_missing", r)
        if rb.get("partial_disallow") and good_home(r):
            add("robots_partial", r)
        sm = r.get("sitemap") or {}
        if good_home(r) and sm:
            k = sm.get("kind")
            if k == "index":
                add("sm_index", r, n=sm.get("count"))
            if sm.get("gz"):
                add("sm_gz", r, n=sm.get("count"))
            if k == "none" and not rb.get("has_sitemap"):
                add("sm_none", r)
            if k == "invalid":
                add("sm_invalid", r)
            if k == "urlset" and (sm.get("count") or 0) >= 5000:
                add("sm_huge", r, n=sm.get("count"))
        if st == 200 and hh.get("spa_marker") and tlen(r) < 250 and hh.get("script_tags", 0) >= 3:
            add("spa_candidate", r)
        if good_home(r):
            add("ok_" + r.get("pool", "?"), r, lang=lang_of(r), builders=hh.get("builders", []), links=len(hh.get("links", [])),
                scripts=hh.get("script_tags", 0), tl=tlen(r), country=r.get("country", ""), cls=r.get("class", ""))
            if len(hh.get("links", [])) <= 12 and 200 <= tlen(r) <= 3000 and hh.get("script_tags", 0) <= 4 and not hh.get("spa_marker"):
                add("minimal", r, links=len(hh["links"]), tl=tlen(r))
            small = len(hh.get("links", [])) <= 80 and tlen(r) <= 12000 and r.get("pool", "") in ("local_small_s", "corporate", "manufacturing", "software")
            if small and (set(hh.get("builders", [])) & {"wix", "squarespace", "shopify", "webflow", "weebly", "godaddy-builder"} or (
                    "wordpress" in hh.get("builders", []) and r.get("pool", "").startswith("local_small"))):
                add("builder", r, builders=hh.get("builders", []), tl=tlen(r))
    print("\n== availability (count) ==")
    for k in sorted(cats):
        print(f"{k:28s} {len(cats[k])}")
    (SCRATCH / "selection_stage1.json").write_text(json.dumps(cats, ensure_ascii=False), encoding="utf-8")
    # Review lists for small/risky categories
    for k in ("parked", "construction", "login", "thin"):
        print(f"\n## review {k}")
        for it in cats.get(k, [])[:60]:
            print("  ", it["host"][:34].ljust(34), {x: y for x, y in it.items() if x != "host"})


if __name__ == "__main__":
    main()

