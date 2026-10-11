"""Independent, polite probe of candidate websites (oracle evidence). Does NOT use app/ code.

For each domain (once): DNS (system + 1.1.1.1, NS records) -> robots.txt -> homepage GET only if robots
allows us -> /sitemap.xml (or the one named in robots). Max 8 domains at a time, one request at a time per domain.
Results go to C:/crawl_eval_data/scratch/probe/<pool>.jsonl (resumable).

    python probe.py <pool_csv> [<pool_csv> ...] [--limit N]
"""
from __future__ import annotations

import asyncio
import csv
import gzip
import json
import re
import socket
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib import robotparser

import dns.exception
import dns.resolver
import httpx
from bs4 import BeautifulSoup

OUT_DIR = Path("C:/crawl_eval_data/scratch/probe")
OUT_DIR.mkdir(parents=True, exist_ok=True)
UA = "WebsiteIntelligenceEval/1.0 (academic crawler field test; Lahore)"
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5", "Accept-Language": "en, *;q=0.5"}
MAX_BYTES = 3_000_000
CONCURRENCY = 8

PARKING_NS = ("sedoparking", "parkingcrew", "bodis.com", "above.com", "dan.com", "afternic", "hugedomains",
              "parklogic", "namebrightdns", "cashparking", "fabulous.com", "voodoo.com", "skenzo", "smartname",
              "domainsponsor", "trafficz", "sav.com", "parked", "registrar-servers.com-parking", "uniregistry",
              "domaincontrol-parking", "porkbun-parking", "undeveloped.com", "buydomains", "park-mx")
PARKED_TEXT = ("this domain is for sale", "domain may be for sale", "buy this domain", "domain is for sale",
               "is for sale", "inquire about this domain", "hugedomains", "sedo.com", "domain parking",
               "this domain name is parked", "parked free", "the domain name", "make an offer", "premium domain",
               "this web page is parked", "domain has expired", "this domain has expired", "expired domain")
CONSTRUCTION = ("coming soon", "under construction", "site is under construction", "website coming soon",
                "welcome to nginx", "apache2 ubuntu default page", "apache2 debian default page", "it works!",
                "index of /", "iis windows server", "default web site page", "future home of", "default parallels plesk",
                "test page for the apache", "web server is working", "this is a default page", "site under maintenance",
                "website under construction", "launching soon", "default page", "cpanel", "plesk")
BOT = ("just a moment", "checking your browser", "cf-chl", "attention required", "captcha", "access denied",
       "incapsula", "perimeterx", "datadome", "pardon our interruption", "request unsuccessful", "are you a robot",
       "verify you are human", "bot detection", "enable javascript and cookies", "unusual traffic")
ADULT_BLOCK = ("porn", "xxx", "adult content", "casino", "betting", "viagra", "escort", "sex ", "nude", "gambling",
               "slot machine", "poker online", "18+")
BUILDERS = {
    "wix": ("wixstatic.com", "wix.com", "x-wix-request-id", "_wixcidx"),
    "squarespace": ("squarespace.com", "static1.squarespace", "sqs-block", "squarespace-cdn"),
    "shopify": ("cdn.shopify.com", "shopify.com/s/", "myshopify.com", "x-shopify", "shopify-section"),
    "webflow": ("webflow.com", "w-nav", "data-wf-site", "data-wf-page"),
    "wordpress": ("wp-content", "wp-includes", "wordpress"),
    "weebly": ("weebly.com", "weeblycloud"),
    "godaddy-builder": ("websitebuilder.godaddy", "img1.wsimg.com", "wsimg.com"),
}
SPA_MARKERS = ('id="root"', 'id="app"', 'id="__next"', "ng-version", "data-reactroot", 'id="___gatsby"',
               "__nuxt", 'id="__nuxt"', "data-v-app", "ng-app")

_resolver = dns.resolver.Resolver(configure=False)
_resolver.nameservers = ["1.1.1.1", "8.8.8.8"]
_resolver.lifetime = 8


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dns_info(host: str) -> dict:
    info: dict = {"system_ok": False, "system_error": "", "rcode": "", "ns": [], "a": []}
    try:
        res = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        info["system_ok"] = True
        info["a"] = sorted({r[4][0] for r in res})[:6]
    except socket.gaierror as exc:
        info["system_error"] = f"{exc.errno}:{exc}"
    for kind in ("A", "AAAA"):
        try:
            ans = _resolver.resolve(host, kind)
            info["rcode"] = "NOERROR"
            info["a"] = sorted(set(info["a"]) | {str(r) for r in ans})[:6]
        except dns.resolver.NXDOMAIN:
            info["rcode"] = "NXDOMAIN"
            break
        except dns.resolver.NoAnswer:
            info["rcode"] = info["rcode"] or "NOERROR"
        except (dns.exception.Timeout, dns.resolver.NoNameservers):
            info["rcode"] = info["rcode"] or "TIMEOUT"
    try:
        info["ns"] = sorted(str(r).lower() for r in _resolver.resolve(host, "NS"))
    except Exception:  # NS may not exist for subdomains; not an error for us
        pass
    return info


async def fetch(client: httpx.AsyncClient, url: str, max_hops: int = 10) -> dict:
    """GET with manual redirects. Returns facts, never raises."""
    out: dict = {"url": url, "chain": [], "error": "", "error_kind": ""}
    cur = url
    started = time.perf_counter()
    for _ in range(max_hops + 1):
        try:
            async with client.stream("GET", cur, headers=HEADERS, follow_redirects=False) as r:
                body = b""
                async for chunk in r.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        out["truncated"] = True
                        break
                out["chain"].append([cur, r.status_code])
                out["status"] = r.status_code
                out["headers"] = {k.lower(): v for k, v in r.headers.items() if k.lower() in (
                    "content-type", "server", "location", "content-length", "content-encoding", "retry-after",
                    "cf-mitigated", "x-datadome", "x-sucuri-id", "x-served-by", "via", "x-powered-by", "refresh")}
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    cur = urljoin(cur, r.headers["location"])
                    continue
                out["final_url"] = str(r.url)
                out["body"] = body
                out["bytes"] = len(body)
                break
        except httpx.TimeoutException as exc:
            out["error_kind"], out["error"] = "timeout", f"{type(exc).__name__}"
            break
        except httpx.ConnectError as exc:
            msg = str(exc)
            out["error"] = msg[:300]
            low = msg.lower()
            if "certificate" in low or "ssl" in low or "tls" in low:
                out["error_kind"] = "tls"
            elif "refused" in low or "10061" in low:
                out["error_kind"] = "refused"
            elif "getaddrinfo" in low or "name or service" in low or "11001" in low:
                out["error_kind"] = "dns"
            else:
                out["error_kind"] = "connect"
            break
        except httpx.HTTPError as exc:
            out["error_kind"], out["error"] = "http", f"{type(exc).__name__}: {str(exc)[:200]}"
            break
        except (ssl.SSLError, OSError) as exc:
            out["error_kind"], out["error"] = "tls" if isinstance(exc, ssl.SSLError) else "os", str(exc)[:200]
            break
        except (ValueError, httpx.InvalidURL) as exc:  # unusable URL text (e.g. odd characters in a harvested URL)
            out["error_kind"], out["error"] = "invalid_url", f"{type(exc).__name__}: {str(exc)[:150]}"
            break
    else:
        out["error_kind"], out["error"] = "redirect_limit", f">{max_hops} redirects"
    out["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    return out


def decode(body: bytes, headers: dict) -> tuple[str, str]:
    ctype = headers.get("content-type", "")
    m = re.search(r"charset=([\w\-]+)", ctype, re.I)
    header_cs = m.group(1).lower() if m else ""
    head = body[:4096].decode("ascii", errors="ignore")
    m2 = re.search(r'<meta[^>]+charset=["\']?([\w\-]+)', head, re.I) or re.search(
        r'content=["\'][^"\']*charset=([\w\-]+)', head, re.I)
    meta_cs = m2.group(1).lower() if m2 else ""
    bom = "utf-8-bom" if body.startswith(b"\xef\xbb\xbf") else ""
    enc = header_cs or meta_cs or "utf-8"
    try:
        text = body.decode(enc, errors="replace")
    except LookupError:
        text = body.decode("utf-8", errors="replace")
    return text, f"header={header_cs or '-'};meta={meta_cs or '-'};{bom}".rstrip(";")


def analyse_html(text: str, base: str, host: str) -> dict:
    soup = BeautifulSoup(text, "lxml")
    low_raw = text.lower()
    for t in soup(["script", "style", "noscript", "template", "svg"]):
        t.decompose()
    visible = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    title = soup.title.get_text(" ", strip=True)[:200] if soup.title else ""
    html_tag = soup.find("html")
    lang = (html_tag.get("lang") if html_tag else "") or ""
    refresh = soup.find("meta", attrs={"http-equiv": re.compile("refresh", re.I)})
    meta_refresh = refresh.get("content", "")[:200] if refresh else ""
    js_redirect = bool(re.search(r"(window\.|document\.)?location(\.href)?\s*=|location\.replace\(", low_raw)) and len(visible) < 200
    builders = [name for name, keys in BUILDERS.items() if any(k in low_raw for k in keys)]
    gen = soup.find("meta", attrs={"name": "generator"})
    links = []
    base_host = host.removeprefix("www.")
    for a in soup.find_all("a", href=True)[:400]:
        href = urljoin(base, a["href"].strip())
        p = urlparse(href)
        if p.scheme in ("http", "https") and (p.hostname or "").lower().removeprefix("www.") == base_host:
            links.append([href.split("#")[0], a.get_text(" ", strip=True)[:60]])
    uniq, seen = [], set()
    for h, t in links:
        if h not in seen:
            seen.add(h)
            uniq.append([h, t])
    scripts = {"arabic": 0, "cjk": 0, "devanagari": 0, "cyrillic": 0, "latin": 0, "other": 0}
    for ch in visible[:3000]:
        o = ord(ch)
        if 0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F:
            scripts["arabic"] += 1
        elif 0x3040 <= o <= 0x30FF or 0x4E00 <= o <= 0x9FFF or 0xAC00 <= o <= 0xD7AF:
            scripts["cjk"] += 1
        elif 0x0900 <= o <= 0x097F:
            scripts["devanagari"] += 1
        elif 0x0400 <= o <= 0x04FF:
            scripts["cyrillic"] += 1
        elif ch.isalpha():
            scripts["latin"] += 1
    low_vis = (title + " " + visible).lower()
    return {
        "title": title, "lang": lang.lower(), "text_len": len(visible), "text_sample": visible[:400],
        "meta_refresh": meta_refresh, "js_redirect": js_redirect, "builders": builders,
        "generator": (gen.get("content", "")[:80] if gen else ""),
        "spa_marker": any(m in low_raw for m in SPA_MARKERS), "script_tags": low_raw.count("<script"),
        "has_password": bool(soup.find("input", attrs={"type": "password"})),
        "parked_text": [k for k in PARKED_TEXT if k in low_vis][:4],
        "construction_text": [k for k in CONSTRUCTION if k in low_vis or k in low_raw[:3000]][:4],
        "bot_text": [k for k in BOT if k in low_vis or k in low_raw[:6000]][:4],
        "adult_text": [k for k in ADULT_BLOCK if k in low_vis][:3],
        "error_title": bool(re.search(r"\b(404|403|500|not found|error|forbidden|unavailable)\b", title.lower())),
        "scripts": scripts, "links": uniq[:150],
    }


def analyse_robots(status: int | None, body: bytes) -> dict:
    info = {"status": status, "disallow_all": False, "crawl_delay": None, "has_sitemap": [], "malformed": False,
            "partial_disallow": False, "allowed_for_us": True}
    if status != 200:
        return info
    text = body.decode("utf-8", errors="replace")
    if "<html" in text[:500].lower():
        info["malformed"] = True
        return info
    rp = robotparser.RobotFileParser()
    rp.parse(text.splitlines())
    info["allowed_for_us"] = rp.can_fetch(UA, "/")
    info["disallow_all"] = not rp.can_fetch("*", "/")
    info["partial_disallow"] = any(l.lower().startswith("disallow:") and l.split(":", 1)[1].strip() not in ("", "/")
                                   for l in text.splitlines())
    info["has_sitemap"] = (rp.site_maps() or [])[:3]
    delay = rp.crawl_delay("*")
    info["crawl_delay"] = delay
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    known = ("user-agent", "disallow", "allow", "sitemap", "crawl-delay", "host", "clean-param", "request-rate", "noindex")
    bad = [l for l in lines if ":" not in l or l.split(":", 1)[0].strip().lower() not in known]
    info["malformed"] = bool(lines) and len(bad) > max(2, len(lines) // 3)
    return info


def analyse_sitemap(res: dict) -> dict:
    info = {"status": res.get("status"), "kind": "none", "count": 0, "bytes": res.get("bytes", 0), "gz": False}
    if res.get("status") != 200:
        return info
    body = res.get("body", b"")
    if body[:2] == b"\x1f\x8b":
        info["gz"] = True
        try:
            body = gzip.decompress(body)[:5_000_000]
        except Exception:
            info["kind"] = "invalid"
            return info
    low = body[:3000].lower()
    if b"<sitemapindex" in low:
        info["kind"] = "index"
    elif b"<urlset" in low:
        info["kind"] = "urlset"
    else:
        info["kind"] = "invalid"
    info["count"] = body.lower().count(b"<loc>")
    return info


async def probe_one(client: httpx.AsyncClient, sem: asyncio.Semaphore, row: dict) -> dict:
    async with sem:
        url = row["url"].strip()
        host = (urlparse(url).hostname or "").lower()
        rec = {"host": host, "input_url": url, "probed_at": now(), "qid": row.get("qid", ""), "label": row.get("label", ""),
               "country": row.get("country", ""), "pool": row.get("pool", ""), "class": row.get("class", "")}
        loop = asyncio.get_running_loop()
        rec["dns"] = await loop.run_in_executor(None, dns_info, host)
        if not rec["dns"]["system_ok"] and rec["dns"]["rcode"] != "NOERROR":
            rec["outcome"] = "dns_fail"
            return rec
        origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        rob = await fetch(client, f"{origin}/robots.txt")
        rec["robots"] = analyse_robots(rob.get("status"), rob.get("body", b""))
        rec["robots"]["fetch_error"] = rob.get("error_kind", "")
        rec["robots"]["final_url"] = rob.get("final_url", "")
        rec["robots"]["ctype"] = rob.get("headers", {}).get("content-type", "")
        if rec["robots"]["status"] == 200 and not rec["robots"]["allowed_for_us"]:
            rec["outcome"] = "robots_disallow"
            return rec
        home = await fetch(client, url)
        rec["http"] = {k: v for k, v in home.items() if k != "body"}
        if "status" not in home:
            rec["outcome"] = f"fetch_error:{home.get('error_kind')}"
            if home.get("error_kind") == "tls":
                async with httpx.AsyncClient(verify=False, timeout=20) as insecure:
                    probe2 = await fetch(insecure, url)
                rec["http"]["works_without_verify"] = "status" in probe2
                rec["http"]["status_without_verify"] = probe2.get("status")
            return rec
        rec["outcome"] = "fetched"
        body = home.get("body", b"")
        ctype = home.get("headers", {}).get("content-type", "")
        rec["http"]["ctype"] = ctype
        if "html" in ctype.lower() or not ctype:
            text, enc = decode(body, home.get("headers", {}))
            rec["encoding"] = enc
            final = home.get("final_url", url)
            rec["html"] = analyse_html(text, final, urlparse(final).hostname or host)
        if home.get("status") == 200:
            sm_url = urljoin(origin + "/", (rec["robots"]["has_sitemap"] or ["/sitemap.xml"])[0].strip())
            sm = await fetch(client, sm_url)
            rec["sitemap"] = analyse_sitemap(sm)
            rec["sitemap"]["url"] = sm_url
        return rec


def load_rows(paths: list[str]) -> list[dict]:
    rows = []
    for p in paths:
        pool = Path(p).stem.removeprefix("pool_")
        with open(p, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                r["pool"] = pool
                rows.append(r)
    return rows


async def main(paths: list[str], limit: int | None) -> None:
    rows = load_rows(paths)
    if limit:
        rows = rows[:limit]
    done: set[str] = set()
    for f in OUT_DIR.glob("*.jsonl"):
        for line in f.read_text(encoding="utf-8").split("\n"):
            try:
                done.add(json.loads(line)["host"])
            except Exception:
                pass
    todo = [r for r in rows if (urlparse(r["url"]).hostname or "").lower() not in done]
    print(f"{len(rows)} candidates, {len(todo)} to probe", flush=True)
    out_file = OUT_DIR / f"{Path(paths[0]).stem}.jsonl"
    sem = asyncio.Semaphore(CONCURRENCY)
    limits = httpx.Limits(max_connections=40, max_keepalive_connections=0)
    async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=10), limits=limits, verify=True) as client:
        no_limit = asyncio.Semaphore(10**6)  # the real limit is applied in guarded(); the 120 s cap starts AFTER acquiring it

        async def guarded(row: dict) -> dict:
            try:
                async with sem:
                    return await asyncio.wait_for(probe_one(client, no_limit, row), timeout=120)
            except Exception as exc:  # a probe bug must not stop the run; recorded as probe error
                return {"host": (urlparse(row["url"]).hostname or "?").lower(), "input_url": row["url"], "pool": row.get("pool", ""),
                        "qid": row.get("qid", ""), "label": row.get("label", ""), "country": row.get("country", ""),
                        "outcome": f"probe_error:{type(exc).__name__}", "probe_error": str(exc)[:200], "probed_at": now()}

        tasks = [asyncio.create_task(guarded(r)) for r in todo]
        n = 0
        with out_file.open("a", encoding="utf-8") as fh:
            for coro in asyncio.as_completed(tasks):
                rec = await coro
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                n += 1
                if n % 50 == 0:
                    print(f"  {n}/{len(todo)}", flush=True)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    lim = None
    if "--limit" in sys.argv:
        lim = int(sys.argv[sys.argv.index("--limit") + 1])
        args = [a for a in args if a != str(lim)]
    asyncio.run(main(args, lim))
