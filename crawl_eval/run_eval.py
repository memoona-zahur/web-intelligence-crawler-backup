"""Field-test harness: runs the UNCHANGED crawler on crawl_eval/dataset/testing_URLs.csv and judges expected vs actual.

    C:\\crawl_eval_data\\venv\\Scripts\\python.exe crawl_eval\\run_eval.py --smoke --label existing-code --concurrency 5
    ... --resume --run-id <id>        continue an interrupted run
    ... --report-only <results dir>   rebuild reports from per_site.jsonl without touching the network

Nothing under app/ is edited. Wrappers (telemetry.py) are in-memory and pass-through; see run_manifest.json.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # never write __pycache__ into app/

import argparse
import asyncio
import csv
import hashlib
import importlib.util
import json
import os
import platform
import re
import socket
import struct
import subprocess
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "C:/crawl_eval_data/browsers")
os.environ["OBSERVE_ECHO"] = "0"

DATA = Path("C:/crawl_eval_data")
UA_HARNESS = "WebsiteIntelligenceEval/1.0 (academic crawler field test; Lahore)"
SCENARIO_BASE, SCENARIO_COUNT = 8800, 62
SCENARIO_PORTS = set(range(SCENARIO_BASE, SCENARIO_BASE + SCENARIO_COUNT)) | {8899}


# ------------------------------------------------------------------ helpers
def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def udp_dns_rcode(host: str, server: str = "1.1.1.1", timeout: float = 3.0):
    """Minimal DNS A query to a public resolver. Returns (rcode, answers) or (None, 0) on timeout."""
    try:
        q = struct.pack(">HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0) + b"".join(bytes([len(p)]) + p.encode("idna") for p in host.split(".")) + b"\x00" + struct.pack(">HH", 1, 1)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        s.sendto(q, (server, 53))
        data, _ = s.recvfrom(2048)
        s.close()
        return data[3] & 0x0F, struct.unpack(">H", data[6:8])[0]
    except Exception:
        return None, 0


async def runtime_probe(host: str, url: str, head: bool, client) -> dict:
    loop = asyncio.get_running_loop()
    rec = {"host": host, "dns_system_ok": False, "dns_public_ok": False, "dns_dead": False, "head_status": None, "error": ""}
    try:
        await loop.run_in_executor(None, socket.getaddrinfo, host, None)
        rec["dns_system_ok"] = True
    except socket.gaierror:
        pass
    rcode, answers = await loop.run_in_executor(None, udp_dns_rcode, host)
    rec["dns_public_rcode"] = rcode
    rec["dns_public_ok"] = rcode == 0 and answers > 0
    rec["dns_dead"] = (not rec["dns_system_ok"]) and rcode == 3
    rec["predicted"] = "unknown"
    if not head:
        return rec
    if not (rec["dns_system_ok"] or rec["dns_public_ok"]):
        rec.update(predicted="Unreachable", error="no-dns")
        return rec
    # What would a person see? Try the stored URL, then the other scheme (the crawler also falls back https -> http). Respect robots.txt.
    p = urlparse(url)
    tries = [url] + ([f"http://{p.netloc}{p.path or ''}"] if p.scheme == "https" else [])
    last_err = ""
    for u in tries:
        origin = f"{urlparse(u).scheme}://{urlparse(u).netloc}"
        try:
            rb = await client.get(origin + "/robots.txt", headers={"User-Agent": UA_HARNESS}, follow_redirects=True, timeout=8)
            if rb.status_code == 200 and "<html" not in rb.text[:300].lower():
                import urllib.robotparser as rp
                parser = rp.RobotFileParser()
                parser.parse(rb.text.splitlines())
                if not parser.can_fetch(UA_HARNESS, "/"):
                    rec.update(predicted="Blocked", note="robots.txt disallows everything for the probe too", scheme=urlparse(u).scheme)
                    return rec
            async with client.stream("GET", u, headers={"User-Agent": UA_HARNESS, "Accept": "text/html,*/*;q=0.5"}, follow_redirects=True, timeout=15) as r:
                body = b""
                async for chunk in r.aiter_bytes():
                    body += chunk
                    if len(body) > 200_000:
                        break
                rec.update(head_status=r.status_code, final_url=str(r.url), scheme=urlparse(u).scheme, bytes=len(body))
                rec["predicted"], rec["note"] = predict_word(r.status_code, body, r.headers.get("content-type", ""))
                return rec
        except Exception as exc:
            last_err = type(exc).__name__
    rec.update(predicted="Unreachable", error=last_err)
    return rec


_PARK = re.compile(r"for sale|is parked|buy this domain|domain.{0,20}expired|inquire about this domain|parkpage", re.I)
_CONS = re.compile(r"coming soon|under construction|welcome to nginx|apache2? (ubuntu|debian)? ?default|index of /|default web site page|site is being built|launching soon", re.I)
_BOT = re.compile(r"just a moment|checking your browser|attention required|captcha|access denied|pardon our interruption|verify you are human|enable javascript and cookies", re.I)


def predict_word(status: int, body: bytes, ctype: str):
    """Independent human-style reading of a page (never uses the crawler's code)."""
    if status in (401, 403, 429):
        return "Blocked", f"http {status}"
    if status >= 400:
        return "Failed", f"http {status}"
    if "html" not in ctype.lower() and ctype:
        return "Failed", f"not html ({ctype[:30]})"
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(body, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    pw = bool(soup.find("input", attrs={"type": "password"}))
    for t in soup(["script", "style", "noscript", "template", "svg"]):
        t.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    blob = f"{title} {text[:2000]}"
    if _BOT.search(blob) and len(text) < 3000:
        return "Blocked", "challenge page"
    if _PARK.search(title) or (_PARK.search(text[:1500]) and len(text) < 9000):
        return "Parked", "parked/for-sale wording"
    if _CONS.search(blob) and len(text) < 700:
        return "Under Construction", "placeholder wording"
    if pw and len(text) < 500:
        return "Requires Review", "login wall"
    if len(text) < 60:
        return "Requires Review", f"almost no static text ({len(text)} chars)"
    return "Crawled", f"{len(text)} chars"


async def dns_robust(host: str) -> dict:
    """DNS from every angle, 3 tries each (a single dropped packet must not look like a dead domain)."""
    loop = asyncio.get_running_loop()
    res = {"system": [], "1.1.1.1": [], "8.8.8.8": []}
    for _ in range(3):
        try:
            await loop.run_in_executor(None, socket.getaddrinfo, host, None)
            res["system"].append(True)
        except socket.gaierror:
            res["system"].append(False)
        for srv in ("1.1.1.1", "8.8.8.8"):
            rcode, answers = await loop.run_in_executor(None, udp_dns_rcode, host, srv, 4.0)
            res[srv].append(rcode if rcode is not None else "timeout" if answers == 0 else rcode)
            if rcode == 0 and answers > 0:
                res[srv][-1] = "ok"
        await asyncio.sleep(1.0)
    ok = any(res["system"]) or any(v == "ok" for k in ("1.1.1.1", "8.8.8.8") for v in res[k])
    nx = any(v == 3 for k in ("1.1.1.1", "8.8.8.8") for v in res[k])
    return {"dns_any_ok": ok, "dns_nxdomain_seen": nx and not ok, "dns_recheck": res}


async def probe_recheck(out: Path):
    """For every probe that read the site as Unreachable: robust DNS (system + two public resolvers, 3 tries); if the name resolves, one fresh GET."""
    import httpx
    for name in ("probes_after.json", "probes_after_reused.json"):
        f = out / name
        if not f.exists():
            continue
        probes = json.loads(f.read_text(encoding="utf-8"))
        todo = [rid for rid, p in probes.items() if p.get("predicted") == "Unreachable" and p.get("host")]
        sem = asyncio.Semaphore(4)
        async with httpx.AsyncClient() as client:
            async def one(rid):
                async with sem:
                    p = probes[rid]
                    p.update(await dns_robust(p["host"]))
                    if p["dns_any_ok"] and p.get("error") in ("no-dns", "ConnectTimeout", "ConnectError", "ReadTimeout"):
                        site = None
                        try:
                            # rows keep their crawl URL in per_site.jsonl; ask it from there
                            site = site_url_of[rid]
                        except KeyError:
                            pass
                        if site and p.get("error") == "no-dns":
                            fresh = await runtime_probe(p["host"], site, True, client)
                            p["fresh_get_after_dns_ok"] = {k: fresh.get(k) for k in ("predicted", "head_status", "note", "error")}
                            if fresh.get("predicted") != "unknown":
                                p["predicted"], p["note"], p["error"] = fresh["predicted"], fresh.get("note", ""), fresh.get("error", "")
                                p["head_status"] = fresh.get("head_status")
            site_url_of = {}
            for line in (out / "per_site.jsonl").read_text(encoding="utf-8").split("\n"):
                if line.strip():
                    x = json.loads(line)
                    site_url_of[x["row_id"]] = x["site_url"]
            await asyncio.gather(*[one(rid) for rid in todo])
        f.write_text(json.dumps(probes, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{name}: robust DNS re-check for {len(todo)} 'Unreachable' probes; names that resolve: {sum(1 for r in todo if probes[r].get('dns_any_ok'))}")


async def probe_after(out: Path):
    """After the crawl: independent GET-based probe of every real / public-test row that did not MATCH (separates 'site changed / env' from 'crawler wrong')."""
    import httpx
    results, _m = build_reports(out, quiet=True)
    manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    rows = {r["id"]: r for r in csv.DictReader((HERE / "dataset" / manifest["dataset_file"]).open(encoding="utf-8-sig"))}
    recs = {}
    for line in (out / "per_site.jsonl").read_text(encoding="utf-8").split("\n"):
        if line.strip():
            x = json.loads(line)
            recs[x["row_id"]] = x
    todo = []
    for r in results:
        row = rows[r["id"]]
        x = recs.get(r["id"])
        if r["verdict"] in ("MATCH", "NOT-RUN") or row["source_type"] == "local-scenario" or not x or x.get("reused_from"):
            continue  # reused rows keep the probe taken in the smoke run
        try:
            h = urlparse(x["site_url"]).hostname or ""
        except ValueError:
            continue
        if not h or re.fullmatch(r"[\d.:]+", h) or h == "localhost" or h.endswith((".local", ".internal")):
            continue
        get = row["source_type"] == "real" and not (row["category"] == "robots.txt" and "disallow all" in row["subcategory"])
        todo.append((r["id"], h, x["site_url"], get))
    probes = {}
    sem = asyncio.Semaphore(4)
    async with httpx.AsyncClient() as client:
        async def one(rid, h, url, get):
            async with sem:
                try:
                    probes[rid] = await runtime_probe(h, url, get, client)
                    probes[rid]["probed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                except Exception as exc:
                    probes[rid] = {"host": h, "error": f"probe-bug:{type(exc).__name__}", "predicted": "unknown"}
        await asyncio.gather(*[one(*t) for t in todo])
    (out / "probes_after.json").write_text(json.dumps(probes, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"post-crawl probe: {len(probes)} rows probed (only rows that did not MATCH)")


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def scenario_up() -> bool:
    try:
        socket.create_connection(("127.0.0.1", SCENARIO_BASE), timeout=2).close()
        return True
    except OSError:
        return False


def start_scenario_server():
    py = DATA / "venv_tools" / "Scripts" / "python.exe"
    subprocess.Popen([str(py), "-I", str(HERE / "scenario_server.py")], cwd=str(ROOT), creationflags=0x08000000)
    for _ in range(20):
        time.sleep(0.5)
        if scenario_up():
            return True
    return False


# ------------------------------------------------------------------ main run
async def run(args) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = args.run_id or f"{args.label}_{ts}{'_smoke' if args.smoke else ''}"
    out = HERE / "results" / run_id
    out.mkdir(parents=True, exist_ok=True)
    log_f = (out / "run.log").open("a", encoding="utf-8")

    def log(msg: str):
        line = f"{datetime.now().strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        log_f.write(line + "\n")
        log_f.flush()

    log(f"run {run_id} label={args.label} smoke={args.smoke} limit={args.limit} concurrency={args.concurrency} resume={args.resume}")
    hm = load_module(HERE / "tools" / "hash_manifest.py", "hash_manifest")
    if args.code_manifest == "auto":  # Phase 2: the code under test is hashed now; the check after the run proves it did not change DURING the run
        manifest_file = out / "code_manifest.json"
        if not (args.resume and manifest_file.exists()):
            hm.create(manifest_file)
    elif args.code_manifest:
        manifest_file = Path(args.code_manifest)
    else:  # default = Phase 1 behaviour: the frozen baseline manifest
        manifest_file = HERE / "baseline" / "run_manifest.json"
    code_sha256 = json.loads(manifest_file.read_text(encoding="utf-8")).get("combined_sha256")
    code_ok_before = hm.verify(manifest_file) == 0
    log(f"app code hash check before run: {'OK' if code_ok_before else 'MISMATCH'}")

    # ---- isolated database (never data/websites.db) ----
    db_path = DATA / "db" / f"{run_id}.db"
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    import app.database as database
    from app.models import Base, DomainStat, Job, Website

    engine = create_engine(f"sqlite:///{db_path}")
    database.engine, database.SessionLocal = engine, sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    os.environ["OBSERVE_LOG"] = str(out / "app_events.jsonl")

    import telemetry
    tel = telemetry.Telemetry(SCENARIO_PORTS)
    telemetry.install(tel)
    tel.start_memory()

    from app import importer
    from app.crawler import config as cconfig
    from app.crawler import runner
    from app.limits import crawl_concurrency

    if not scenario_up():
        log("scenario server not running: starting it")
        if not start_scenario_server():
            raise SystemExit("could not start scenario server")
    # ---- dataset ----
    ds_path = Path(args.urls) if args.urls else HERE / "dataset" / "testing_URLs.csv"
    rows = list(csv.DictReader(ds_path.open(encoding="utf-8-sig")))
    by_id = {r["id"]: r for r in rows}
    sel = [r for r in rows if r["smoke"] == "Y"] if args.smoke else list(rows)
    if args.limit:
        sel = sel[: args.limit]
    log(f"dataset {ds_path.name} sha256 {sha256_file(ds_path)[:16]} rows={len(rows)} selected={len(sel)}")

    # ---- import ALL rows through the real importer (import verdicts for every row) ----
    imp_file = out / "import_decisions.json"
    lines = [r["url"] for r in rows]
    if args.resume and imp_file.exists():
        imp = json.loads(imp_file.read_text(encoding="utf-8"))
        log("resume: import decisions loaded from file")
    else:
        # The real importer may RAISE on a malformed line and then imports nothing (the whole batch is lost).
        # The harness records the crash (that is a finding), removes the offending line and imports the rest.
        import_rows, crashes = list(rows), {}
        while True:
            tel.import_log["raws"], tel.import_log["decisions"] = [], []
            try:
                with database.get_session() as session:
                    result = importer.import_urls(session, "\n".join(r["url"] for r in import_rows))
                break
            except Exception as exc:  # noqa: BLE001 - recording a crawler crash, not hiding it
                k = len(tel.import_log["decisions"])
                bad = import_rows[k]
                crashes[bad["id"]] = {"decision": "crash", "error": f"{type(exc).__name__}: {exc}", "raw": bad["url"][:120],
                                      "lost_rows_in_that_attempt": len(import_rows)}
                log(f"IMPORTER CRASH on row {bad['id']} {bad['url'][:40]!r}: {type(exc).__name__}: {exc} (batch of {len(import_rows)} rows lost); retrying without it")
                import_rows = [r for r in import_rows if r["id"] != bad["id"]]
        raws, decs = tel.import_log["raws"], tel.import_log["decisions"]
        log(f"importer: added={result.added} duplicates={len(result.duplicates)} invalid={len(result.invalid)}; raws={len(raws)} lines={len(import_rows)}; crashes={len(crashes)}")
        imp = dict(crashes)
        harness_import_problem = len(raws) != len(import_rows) or len(decs) != len(raws)
        with database.get_session() as session:
            by_orig = {w.original_url: w for w in session.scalars(select(Website))}
        for i, r in enumerate(import_rows):
            if harness_import_problem:
                imp[r["id"]] = {"decision": "harness-error", "note": f"import alignment: raws={len(raws)} lines={len(lines)} decisions={len(decs)}"}
                continue
            d = decs[i]
            raw1 = raws[i].strip()
            if d["normalized"] is None or not d["safe"]:
                dec = "invalid"
            elif raw1 in by_orig and by_orig[raw1].normalized_website == d["normalized"]:
                dec = "added"
            else:
                dec = "duplicate"
            imp[r["id"]] = {"decision": dec, "normalized": d["normalized"], "raw_first_cell": raws[i][:120]}
        imp_file.write_text(json.dumps(imp, ensure_ascii=False, indent=0), encoding="utf-8")
        (out / "harness_import_problem.txt").write_text(str(harness_import_problem), encoding="utf-8")
    # ---- decide how each selected row is crawled ----
    plan = {}  # row id -> {via, site_url}
    direct_types = {"local-scenario", "public-test-endpoint"}
    with database.get_session() as session:
        for r in sel:
            rid = r["id"]
            if r["category"] != "Input handling" and r["source_type"] in direct_types:
                url = r["url"]
                site = session.scalar(select(Website).where(Website.normalized_website == url))
                if site is None:
                    session.add(Website(original_url=url, normalized_website=url, status="pending", source_batch="harness-direct"))
                plan[rid] = {"via": "direct", "site_url": url}
            elif imp[rid]["decision"] == "added":
                plan[rid] = {"via": "importer", "site_url": imp[rid]["normalized"]}
        session.commit()
        # Input-handling rows that the importer ACCEPTED are also crawled (fetch-time guard test), whether or not in smoke
        extra = [r for r in rows if r["category"] == "Input handling" and imp[r["id"]]["decision"] == "added" and r["id"] not in plan and r in sel]
        for r in extra:
            plan[r["id"]] = {"via": "importer", "site_url": imp[r["id"]]["normalized"]}
    site_ids = {}
    with database.get_session() as session:
        for w in session.scalars(select(Website)):
            site_ids[w.normalized_website] = w.id
    done_rows = set()
    ps_file = out / "per_site.jsonl"
    if args.resume and ps_file.exists():
        done_rows = {json.loads(l)["row_id"] for l in ps_file.read_text(encoding="utf-8").split("\n") if l.strip()}
    # ---- reuse an earlier run (the smoke run) so every real site is visited ONCE; same code, same dataset, checked below ----
    reused: set[str] = set()
    if args.include_from:
        src = Path(args.include_from)
        src_man = json.loads((src / "run_manifest.json").read_text(encoding="utf-8"))
        if src_man["dataset_sha256"] != sha256_file(ds_path):
            raise SystemExit("--include-from run used a different dataset file")
        if not (src_man["app_code_unchanged_before"] and src_man["app_code_unchanged_after"]):
            raise SystemExit("--include-from run did not prove the code unchanged")
        if src_man.get("code_sha256") and src_man["code_sha256"] != code_sha256:
            raise SystemExit("--include-from run used different code (code hash differs)")
        with ps_file.open("a", encoding="utf-8") as fh:
            for line in (src / "per_site.jsonl").read_text(encoding="utf-8").split("\n"):
                if line.strip():
                    x = json.loads(line)
                    if x["row_id"] in plan and x["row_id"] not in done_rows and x["row_id"] not in reused:
                        x["reused_from"] = src.name
                        fh.write(json.dumps(x, ensure_ascii=False) + "\n")
                        reused.add(x["row_id"])
        if (src / "probes_after.json").exists():
            (out / "probes_after_reused.json").write_text((src / "probes_after.json").read_text(encoding="utf-8"), encoding="utf-8")
        done_rows |= reused
        log(f"reused {len(reused)} row results from {src.name} (not crawled again)")
    todo = [rid for rid in plan if rid not in done_rows]
    HEAVY = {f"127.0.0.1:{SCENARIO_BASE + n}" for n in (1, 2, 3, 4, 5, 7, 8, 17)}

    def is_heavy(rid):
        u = urlparse(plan[rid]["site_url"])
        return f"{u.hostname}:{u.port}" in HEAVY

    normal = sorted(r for r in todo if not is_heavy(r))
    heavy = sorted(r for r in todo if is_heavy(r))
    log(f"crawl plan: {len(plan)} rows ({sum(1 for p in plan.values() if p['via']=='direct')} direct, {sum(1 for p in plan.values() if p['via']=='importer')} via importer); "
        f"reused {len(reused)}; to do now: {len(normal)} normal + {len(heavy)} heavy (final stage)")

    probes: dict = {}  # the run-time probe is done AFTER the crawl, only for rows that did not match (probe_after)

    # ---- memory watchdog: protects the laptop; SOFT = cancel run and record, HARD = kill process (a blocking decompression cannot be cancelled) ----
    stop_ev = asyncio.Event()
    loop = asyncio.get_running_loop()
    wd = telemetry.Watchdog(soft_mb=2048, hard_mb=3072, free_soft_mb=1536, free_hard_mb=1024, record_path=out / "watchdog_hard.json",
                            on_soft=lambda: loop.call_soon_threadsafe(stop_ev.set))
    wd.start()
    stopped_by_watchdog = {"hit": False}

    def write_records(rids, extra=None):
        with database.get_session() as session, ps_file.open("a", encoding="utf-8") as fh:
            for rid in rids:
                url = plan[rid]["site_url"]
                w = session.get(Website, site_ids[url])
                if w.status in ("pending", "crawling") and not (extra or {}).get(rid):
                    continue  # not finished: stays NOT-RUN
                reqs = [r for r in tel.requests if r.get("site") == url]
                rec = {"row_id": rid, "via": plan[rid]["via"], "site_url": url, "imp": imp[rid], "probe": probes.get(rid),
                       "db": {"status": w.status, "crawl_status": w.crawl_status, "crawl_error": w.crawl_error, "pages_crawled": w.pages_crawled,
                              "last_crawled_at": str(w.last_crawled_at), "content_hash": w.content_hash, "original_url": w.original_url, "clean_text": w.clean_text},
                       "tel_site": next((s for s in tel.sites if s["site"] == url), None), "requests": reqs,
                       "attempts": [a for a in tel.attempts if a.get("site") == url], "guard": [g for g in tel.guard if g.get("site") == url],
                       "robots": [x for x in tel.robots if x.get("site") == url], "browser": [x for x in tel.browser if x.get("site") == url]}
                if extra and extra.get(rid):
                    rec.update(extra[rid])
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    async def run_batch(rids, conc, timeout) -> bool:
        ids = [site_ids[plan[r]["site_url"]] for r in rids]
        task = asyncio.create_task(runner.run(site_ids=ids, concurrency=conc, log=lambda m: log("  runner: " + str(m))))
        waiter = asyncio.create_task(stop_ev.wait())
        done, _ = await asyncio.wait({task, waiter}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        stopped = waiter in done
        if task in done:
            log(f"  batch counts: {dict(task.result().counts)} in {task.result().seconds}s")
        else:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            log("  HARNESS: batch cancelled by " + ("MEMORY WATCHDOG" if stopped else "batch timeout"))
        waiter.cancel()
        return stopped

    # ---- stage 1: everything except the heavy scenarios ----
    t_run = time.monotonic()
    batch_n = 50
    for b in range(0, len(normal), batch_n):
        batch = normal[b: b + batch_n]
        wd.context = {"stage": "main", "row": f"batch {b // batch_n + 1}"}
        log(f"stage 1 batch {b // batch_n + 1}: {len(batch)} sites")
        stopped = await run_batch(batch, args.concurrency, args.batch_timeout)
        write_records(batch)
        log(f"  checkpoint written ({min(b + batch_n, len(normal))}/{len(normal)})")
        if stopped:
            stopped_by_watchdog["hit"] = True
            break
    # ---- stage 2 (FINAL): heavy scenarios one at a time, concurrency 1, memory timeline per row ----
    heavy_mem = []
    if heavy and not stopped_by_watchdog["hit"]:
        log(f"stage 2 (final, heavy scenarios): {len(heavy)} rows, one at a time")
    for rid in heavy:
        if stopped_by_watchdog["hit"]:
            break
        url = plan[rid]["site_url"]
        wd.context = {"stage": "heavy", "row": rid, "url": url}
        t_a = time.monotonic() - wd.t0
        base = rss_now = telemetry.rss_mb()
        log(f"  heavy row {rid} {url} (rss now {base:.0f} MB, machine free {telemetry.free_phys_mb():.0f} MB)")
        stopped = await run_batch([rid], 1, args.batch_timeout)
        t_b = time.monotonic() - wd.t0
        peak = wd.peak_between(t_a, t_b)
        heavy_mem.append({"row": rid, "url": url, "rss_before_mb": round(base, 1), "rss_peak_mb": round(peak, 1), "peak_delta_mb": round(peak - base, 1),
                          "rss_after_mb": round(telemetry.rss_mb(), 1), "seconds": round(t_b - t_a, 1), "watchdog_soft_stop": stopped,
                          "timeline_every_0.5s": [(t, r) for t, r, _f in wd.timeline if t_a <= t <= t_b][::4]})
        write_records([rid], extra={rid: {"watchdog_stopped": stopped}} if stopped else None)
        if stopped:
            stopped_by_watchdog["hit"] = True
            log("  MEMORY WATCHDOG stopped the run during this row; remaining heavy rows are NOT-RUN")
    (out / "heavy_memory.json").write_text(json.dumps(heavy_mem, indent=1), encoding="utf-8")
    wall = time.monotonic() - t_run
    wd.stop()
    tel.stop_memory()
    # secret-in-DB scan (CR-F08): did a password inside a URL end up stored?
    with database.get_session() as session:
        secret_stored = any("secret@" in (w.original_url or "") or ":secret" in (w.original_url or "") for w in session.scalars(select(Website)))
        domain_stats = session.scalar(select(__import__("sqlalchemy").func.count()).select_from(DomainStat))
        job_rows = [(j.id, j.kind, j.status, j.added, j.note) for j in session.scalars(select(Job)) if j.kind == "crawl"]
    code_ok_after = hm.verify(manifest_file) == 0
    log(f"app code hash check after run: {'OK' if code_ok_after else 'MISMATCH'}")
    (out / "requests.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in tel.requests) + "\n", encoding="utf-8")
    manifest = {
        "run_id": run_id, "label": args.label, "started": ts, "smoke": args.smoke, "concurrency_used": args.concurrency,
        "crawler_own_default_concurrency": {"config.CONCURRENCY": cconfig.CONCURRENCY, "limits.crawl_concurrency()": crawl_concurrency()},
        "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(), "git_tag": args.code_tag,
        "code_manifest": manifest_file.name, "code_sha256": code_sha256,
        "app_code_unchanged_before": code_ok_before, "app_code_unchanged_after": code_ok_after,
        "dataset_file": str(ds_path.name), "dataset_sha256": sha256_file(ds_path), "rows_total": len(rows), "rows_selected": len(sel), "rows_crawled": len(plan),
        "python": platform.python_version(), "os": platform.platform(), "db": str(db_path), "wrappers": telemetry.WRAPPERS,
        "guard_relaxed_for": f"127.0.0.1 ports {SCENARIO_BASE}-{SCENARIO_BASE + SCENARIO_COUNT - 1} and 8899 only",
        "safety_net": "requests aimed at non-global addresses that the crawler's guard did not stop are not sent (recorded SAFETY_NET_BLOCKED)",
        "direct_insert_rows": sum(1 for p in plan.values() if p["via"] == "direct"),
        "memory_note": "RSS is this Python process only; Chromium child processes are not included",
        "wall_seconds_crawl": round(wall, 1), "secret_stored": secret_stored, "domain_stats_rows": domain_stats, "crawl_jobs": job_rows,
        "peak_rss_mb": round(max([m for _t, m in tel.mem] or [0]), 1),
        "rows_reused_from_earlier_run": sorted(reused), "include_from": args.include_from,
        "watchdog": {"soft_mb": wd.soft_mb, "hard_mb": wd.hard_mb, "free_soft_mb": wd.free_soft_mb, "free_hard_mb": wd.free_hard_mb,
                     "soft_limit_event": wd.soft_hit, "hard_limit_record_file": str(out / "watchdog_hard.json")},
        "machine": {"total_ram_gb": 15.9, "note": "Windows 10, 15.9 GB RAM (read at start of project)"},
        "data_folder_note": "An empty data/ folder exists in the repo root; it was created by the existing test suite during Step 0 (1:05 PM 2026-10-10). The harness never opens data/websites.db.",
        "stage_2_heavy_rows": len(heavy),
    }
    (out / "run_manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    log_f.close()
    return out


# ------------------------------------------------------------------ reports
def pct(vals, p):
    if not vals:
        return None
    vals = sorted(vals)
    return round(vals[min(len(vals) - 1, int(len(vals) * p))], 2)


def build_reports(out: Path, quiet: bool = False, apply_reclass: bool = True):
    import judge
    manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    ds_path = HERE / "dataset" / manifest["dataset_file"]
    rows = {r["id"]: r for r in csv.DictReader(ds_path.open(encoding="utf-8-sig"))}
    imp = json.loads((out / "import_decisions.json").read_text(encoding="utf-8"))
    probes_after = {}
    for name in ("probes_after_reused.json", "probes_after.json"):  # reused (smoke) probes first, then this run's own
        if (out / name).exists():
            probes_after.update(json.loads((out / name).read_text(encoding="utf-8")))
    ol = HERE / "dataset" / "oracle_limitations.json"
    oracle_lim = json.loads(ol.read_text(encoding="utf-8"))["rows"] if ol.exists() else {}
    rcf = HERE / "dataset" / "label_reclassifications.json"
    reclass = json.loads(rcf.read_text(encoding="utf-8"))["rows"] if (rcf.exists() and apply_reclass) else {}
    recs = {}
    for line in (out / "per_site.jsonl").read_text(encoding="utf-8").split("\n"):
        if line.strip():
            x = json.loads(line)
            recs[x["row_id"]] = x
    selected =[rid for rid, r in rows.items() if (r["smoke"] == "Y" or not manifest["smoke"])]
    results = []
    for rid in sorted(selected):
        row = rows[rid]
        x = recs.get(rid)
        c = {"imp": imp.get(rid), "secret_stored": manifest.get("secret_stored")}
        if manifest.get("git_tag", "crawler-baseline-v1") != "crawler-baseline-v1":
            c["status_vocab"] = "v3"  # Phase 2 code: it can say Parked / Redirected / ...; the judge must not claim the vocabulary is missing
        if x:
            ts = x.get("tel_site") or {}
            db = x["db"]
            st = db["status"] if db["status"] not in ("pending", "crawling") else None
            c.update(status=st, error=db["crawl_error"], clean_text=db["clean_text"], seconds=ts.get("seconds"), requests=x["requests"], final_url=ts.get("final_url"),
                     probe=probes_after.get(rid) or x.get("probe"))
        elif rows[rid]["category"] != "Input handling" and imp[rid]["decision"] != "added" and rows[rid]["source_type"] == "real":
            pass
        j = judge.judge(row, c)
        rc = reclass.get(rid)
        if rc and j["verdict"] == rc.get("from", "SITE-CHANGED"):  # fresh-probe review at Phase 1 close: the label did not hold (see label_review.md)
            j["reason"] = f"RECLASSIFIED {j['verdict']} -> {rc['to']}: {rc['reason']}"
            j["verdict"] = rc["to"]
        if rid in oracle_lim and j["verdict"] in ("MISMATCH", "PARTIAL"):
            j["reason"] = f"ORACLE-LIMITATION: {oracle_lim[rid]} (crawler result: {j['reason']})"
            j["verdict"] = "ORACLE-LIMITATION"
        if not x and row["category"] != "Input handling" and row["source_type"] == "real" and (imp.get(rid) or {}).get("decision") in ("invalid", "duplicate"):
            j.update(verdict="MISMATCH", status_verdict="MISMATCH", reason=f"importer did not create a site for this real URL (decision: {imp[rid]['decision']})", actual=f"import:{imp[rid]['decision']}")
        reqs = [r for r in (x or {}).get("requests", []) if r.get("origin") == "crawler"]
        page_reqs = [r for r in reqs if judge.purpose(r["url"]) == "page"]
        ts = (x or {}).get("tel_site") or {}
        txt = ((x or {}).get("db") or {}).get("clean_text") or ""
        att = (x or {}).get("attempts", [])
        per_url = Counter(a["url"] for a in att)
        results.append({
            "id": rid, "category": row["category"], "subcategory": row["subcategory"], "source_type": row["source_type"], "via": (x or {}).get("via", "import-only"),
            "url": row["url"], "expected_outcome": row["expected_outcome"], "expected_status": row["expected_status"], "actual": j["actual"],
            "crawler_status": ((x or {}).get("db") or {}).get("status", ""), "crawler_error": ((x or {}).get("db") or {}).get("crawl_error", ""),
            "pages_crawled": ((x or {}).get("db") or {}).get("pages_crawled", ""), "page_requests": len(page_reqs), "distinct_pages_200": len({r["url"] for r in page_reqs if r.get("status") == 200}),
            "http_requests": len(reqs), "retries": sum(n - 1 for n in per_url.values() if n > 1), "seconds": ts.get("seconds", ""), "rss_peak_mb": ts.get("rss_peak_in_window_mb", ""),
            "text_chars": len(txt), "truncated": txt.endswith("...[truncated]"), "browser_used": bool((x or {}).get("browser")), "final_url": ts.get("final_url", ""),
            "import_decision": (imp.get(rid) or {}).get("decision", ""), "status_verdict": j["status_verdict"], "checks": "; ".join(f"{n}={'PASS' if ok else 'FAIL'}" + (f" ({d})" if d and not ok else "") for n, ok, d in j["checks"]),
            "verdict": j["verdict"], "reason": j["reason"], "env_flags": ";".join(j["env_flags"]), "runtime_probe": j.get("probe_class", ""), "oracle_rule_applied": "Y" if row["oracle_rule"] else "",
            "tags": row["tags"],
        })
    if quiet:
        return results, {}
    with (out / "results.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0]))
        w.writeheader()
        w.writerows(results)
    # ---- metrics ----
    crawled = [r for r in results if r["http_requests"] or r["crawler_status"]]
    secs = [float(r["seconds"]) for r in results if r["seconds"] not in ("", None)]
    verdicts = Counter(r["verdict"] for r in results)
    by_cat = defaultdict(Counter)
    for r in results:
        by_cat[r["category"]][r["verdict"]] += 1
    status_counts = Counter(r["crawler_status"] for r in results if r["crawler_status"])
    happy = [r for r in results if r["category"] in HAPPY_CATS]
    useful = [r for r in happy if r["crawler_status"] == "crawled" and r["text_chars"] >= 500]
    metrics = {
        "run_id": manifest["run_id"], "rows_judged": len(results), "verdicts": dict(verdicts), "status_counts": dict(status_counts),
        "match_rate_all": round(verdicts["MATCH"] / len(results), 3),
        "judged_for_crawler_fault": len(results) - verdicts["ENV-DEPENDENT"] - verdicts["SITE-CHANGED"] - verdicts["ORACLE-LIMITATION"] - verdicts["NOT-RUN"],
        "happy_rows": len(happy), "happy_crawled": sum(1 for r in happy if r["crawler_status"] == "crawled"), "happy_useful_text_ge_500": len(useful),
        "latency_s_p50": pct(secs, 0.5), "latency_s_p95": pct(secs, 0.95), "total_http_requests": sum(r["http_requests"] for r in results), "retries": sum(r["retries"] for r in results),
        "browser_used_rows": sum(1 for r in results if r["browser_used"]), "wall_seconds_crawl": manifest["wall_seconds_crawl"],
        "throughput_sites_per_hour_THIS_RUN_ONLY": round(len([r for r in results if r["via"] != "import-only"]) / max(manifest["wall_seconds_crawl"], 1) * 3600, 1),
        "peak_rss_mb_python_only": manifest["peak_rss_mb"], "by_category": {k: dict(v) for k, v in by_cat.items()},
        "concurrency_used": manifest["concurrency_used"], "crawler_own_default_concurrency": manifest["crawler_own_default_concurrency"],
        "app_code_unchanged": manifest["app_code_unchanged_before"] and manifest["app_code_unchanged_after"],
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=1, ensure_ascii=False), encoding="utf-8")
    write_summary(out, manifest, results, metrics)
    return results, metrics


HAPPY_CATS = {"Corporate / B2B services", "Manufacturers, industrial, distributors, wholesalers", "E-commerce and retail", "SaaS / software / platforms",
              "Healthcare, education, finance, real estate, non-profit, government", "Small local businesses on site builders", "Large multinational enterprises",
              "Non-English / international", "JavaScript-heavy SPAs", "Minimal / one-page / static sites", "Sitemap variants and non-standard navigation"}


def write_summary(out, manifest, results, metrics):
    L = []
    A = L.append
    v = metrics["verdicts"]
    A(f"# Run summary – {manifest['run_id']}")
    A("")
    A(f"Code under test: `{manifest['label']}` (git `{manifest['git_commit'][:8]}`, tag `{manifest['git_tag']}`). App code unchanged during the run: **{metrics['app_code_unchanged']}**. "
      f"Dataset `{manifest['dataset_file']}` sha256 `{manifest['dataset_sha256'][:16]}…`. Concurrency used: **{manifest['concurrency_used']}** "
      f"(the crawler's own default is {manifest['crawler_own_default_concurrency']['config.CONCURRENCY']}; Phase 2 must use the same value as the final Phase 1 run).")
    A("")
    A(f"**This is a smoke run** (selected rows only), so no figure here may be read as a rate for the full dataset or for 60,000 URLs." if manifest["smoke"] else "")
    A("")
    A("## Verdicts")
    A("")
    A("| Verdict | Rows |")
    A("|---|---:|")
    for k in ("MATCH", "PARTIAL", "MISMATCH", "ENV-DEPENDENT", "SITE-CHANGED", "ORACLE-LIMITATION", "HARNESS-ERROR", "NOT-RUN"):
        A(f"| {k} | {v.get(k, 0)} |")
    A(f"| **Total** | {len(results)} |")
    A("")
    A("`ENV-DEPENDENT` = result caused by this network (Pakistan ISP resolver, geo-blocking), not counted as a crawler bug. `SITE-CHANGED` = the site no longer behaves as it did when the dataset was built.")
    A("")
    A("## By category")
    A("")
    A("| Category | Rows | MATCH | PARTIAL | MISMATCH | ENV | SITE-CHG | Other |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    for cat, cnt in sorted(metrics["by_category"].items()):
        tot = sum(cnt.values())
        other = tot - sum(cnt.get(k, 0) for k in ("MATCH", "PARTIAL", "MISMATCH", "ENV-DEPENDENT", "SITE-CHANGED"))
        A(f"| {cat} | {tot} | {cnt.get('MATCH', 0)} | {cnt.get('PARTIAL', 0)} | {cnt.get('MISMATCH', 0)} | {cnt.get('ENV-DEPENDENT', 0)} | {cnt.get('SITE-CHANGED', 0)} | {other} |")
    A("")
    A("## Numbers from this run only")
    A("")
    A(f"* Crawler statuses: {metrics['status_counts']}")
    A(f"* Happy-path rows: {metrics['happy_rows']}; crawled: {metrics['happy_crawled']}; with ≥500 characters of text: {metrics['happy_useful_text_ge_500']}")
    A(f"* Per-site time p50 {metrics['latency_s_p50']} s, p95 {metrics['latency_s_p95']} s; HTTP requests {metrics['total_http_requests']}; retries {metrics['retries']}; browser used on {metrics['browser_used_rows']} rows")
    A(f"* Wall time of crawl {metrics['wall_seconds_crawl']} s; throughput {metrics['throughput_sites_per_hour_THIS_RUN_ONLY']} sites/hour (this run, concurrency {metrics['concurrency_used']}, mixed fast/slow test rows — not a forecast); peak memory of the Python process {metrics['peak_rss_mb_python_only']} MB (Chromium not included)")
    A("")
    A("## Rows that did not match (first 60)")
    A("")
    A("| Id | Category | URL | Expected | Actual | Verdict | Reason |")
    A("|---|---|---|---|---|---|---|")
    for r in [r for r in results if r["verdict"] not in ("MATCH",)][:60]:
        A(f"| {r['id']} | {r['category'][:28]} | {r['url'][:50]} | {r['expected_outcome']} | {r['actual']} | {r['verdict']} | {(r['reason'] or r['checks'])[:140]} |")
    (out / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--label", default="existing-code")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--run-id")
    ap.add_argument("--batch-timeout", type=int, default=1800)
    ap.add_argument("--report-only")
    ap.add_argument("--probe-after")
    ap.add_argument("--probe-recheck")
    ap.add_argument("--code-manifest", help="'auto' = hash app/ etc. at start and prove it unchanged at the end (Phase 2 code); a path = verify against that manifest; omitted = Phase 1 baseline manifest")
    ap.add_argument("--code-tag", default="crawler-baseline-v1", help="git tag/name recorded in run_manifest.json for the code under test")
    ap.add_argument("--include-from", help="earlier run dir (same dataset + code) whose row results are reused instead of crawling those sites again")
    args = ap.parse_args()
    if args.report_only:
        build_reports(Path(args.report_only))
        return
    if args.probe_recheck:
        asyncio.run(probe_recheck(Path(args.probe_recheck)))
        build_reports(Path(args.probe_recheck))
        return
    if args.probe_after:
        asyncio.run(probe_after(Path(args.probe_after)))
        build_reports(Path(args.probe_after))
        return
    out = asyncio.run(run(args))
    asyncio.run(probe_after(out))
    asyncio.run(probe_recheck(out))
    build_reports(out)
    print("results in", out)


if __name__ == "__main__":
    main()
