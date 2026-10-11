"""Local scale test of the queue (plan user addition 2; CR-G01-G03, G08). No real website is contacted.

    python -B crawl_eval/tools/scale_test.py --db sqlite --sites 1000 --concurrency 5 10 20 --workers 3
    python -B crawl_eval/tools/scale_test.py --db postgresql+psycopg://user:pw@localhost:5432/crawl_scale --sites 1000 --concurrency 5 10 20 --workers 3

For each concurrency level: a fresh database, 1,000 imported websites (900 separate domains + 100 sub-domains of 10 shared domains, to exercise the
one-running-task-per-domain rule), N worker PROCESSES (default 3) sharing the queue. Then checks:
  every website finished or has a scheduled retry (nothing lost) | no task attempted twice by mistake | no two tasks of one domain overlapped |
  the work was spread over the workers | timings and peak memory per worker process.
Numbers describe THIS machine and THIS fake workload only; nothing is extrapolated to 60,000 sites.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
os.environ.setdefault("CRAWLER_MODE", "test")
os.environ["OBSERVE_ECHO"] = "0"

DATA = Path("C:/crawl_eval_data/db")


def site_urls(count: int) -> list[str]:
    urls = [f"site{i:04d}.test" for i in range(count - 100)]
    urls += [f"unit{j}.shared{j % 10:02d}.test" for j in range(100)]
    return urls


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    return round(values[min(len(values) - 1, int(len(values) * p))], 1)


def run_level(db: str, sites: int, concurrency: int, workers: int, out_dir: Path) -> dict:
    from sqlalchemy import func, select, text
    from sqlalchemy.orm import sessionmaker

    import app.database as database
    from app.crawler import queue
    from app.importer import import_urls
    from app.models import Base, CrawlTask, FetchAttempt, Page, Website

    if db == "sqlite":
        DATA.mkdir(parents=True, exist_ok=True)
        path = DATA / f"scale_c{concurrency}_{datetime.now():%H%M%S}.db"
        url = f"sqlite:///{path}"
    else:
        url = db
    engine = database.make_engine(url)
    if url.startswith("postgresql"):
        with engine.begin() as conn:  # a clean schema for each level
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
    database.run_migrations(engine)
    Session = sessionmaker(bind=engine)

    t0 = time.monotonic()
    with Session() as session:
        result = import_urls(session, "\n".join(site_urls(sites)), source_file="scale_test")
        imported = result.added
        queued = queue.enqueue_pending(session)
        session.commit()
    prep_seconds = time.monotonic() - t0

    env = dict(os.environ, DATABASE_URL=url, CRAWLER_MODE="test", PYTHONDONTWRITEBYTECODE="1")
    env["CRAWLER_CONTACT_URL"] = "https://policy.scale-test-mock.org/crawler"   # the fake transport is in-process: nothing leaves this machine
    procs, outs = [], []
    started = time.monotonic()
    for n in range(workers):
        out_file = out_dir / f"worker_c{concurrency}_{n}.json"
        outs.append(out_file)
        procs.append(subprocess.Popen([sys.executable, "-B", str(ROOT / "crawl_eval" / "tools" / "scale_worker.py"), str(concurrency), str(out_file)], env=env, cwd=ROOT))
    codes = [p.wait() for p in procs]
    wall = time.monotonic() - started

    with Session() as session:
        statuses = {s: n for s, n in session.execute(select(Website.status, func.count()).group_by(Website.status)).all()}
        states = queue.counts_by_state(session)
        attempts = {a: n for a, n in session.execute(select(CrawlTask.attempt, func.count()).group_by(CrawlTask.attempt)).all()}
        pages = session.scalar(select(func.count()).select_from(Page)) or 0
        fetches = session.scalar(select(func.count()).select_from(FetchAttempt)) or 0
        ms = [float(m) for (m,) in session.execute(select(FetchAttempt.ms).where(FetchAttempt.http_status == 200, FetchAttempt.ms.is_not(None))).all()]
        per_worker = {w: n for w, n in session.execute(select(CrawlTask.worker_id, func.count()).where(CrawlTask.worker_id.is_not(None)).group_by(CrawlTask.worker_id)).all()}
        unfinished = [s for s in statuses if s in ("pending", "queued", "crawling", "extracting")]
        # no two tasks of one domain at the same time: compare started/finished windows per domain
        rows = session.execute(select(CrawlTask.domain_key, CrawlTask.started_at, CrawlTask.finished_at).where(CrawlTask.finished_at.is_not(None), CrawlTask.attempt >= 1)).all()
    overlaps = 0
    by_domain: dict[str, list] = {}
    for key, begin, end in rows:
        by_domain.setdefault(key, []).append((begin, end))
    for key, windows in by_domain.items():
        windows.sort()
        overlaps += sum(1 for a, b in zip(windows, windows[1:]) if b[0] < a[1])
    worker_reports = [json.loads(f.read_text()) for f in outs if f.exists()]
    row = {
        "database": "postgresql" if url.startswith("postgresql") else "sqlite", "sites": sites, "imported": imported, "queued": queued, "concurrency_per_worker": concurrency,
        "worker_processes": workers, "exit_codes": codes, "prep_seconds": round(prep_seconds, 1), "wall_seconds": round(wall, 1),
        "sites_per_hour_THIS_RUN_ONLY": round(sum(n for s, n in statuses.items() if s not in ("pending", "queued")) / wall * 3600),
        "website_status": statuses, "task_states": states, "task_attempts": attempts, "unfinished_websites": sum(statuses[s] for s in unfinished),
        "pages_saved": pages, "fetch_attempts_saved": fetches, "fake_page_latency_ms_p50": percentile(ms, 0.5), "fake_page_latency_ms_p95": percentile(ms, 0.95),
        "tasks_per_worker_slot": per_worker, "same_domain_overlaps": overlaps, "peak_rss_mb_per_worker_process": [w["peak_rss_mb"] for w in worker_reports],
        "worker_reports": worker_reports,
    }
    row["checks"] = {
        "all_workers_exited_0": all(c == 0 for c in codes),
        "nothing_lost": row["unfinished_websites"] == 0 and sum(states.values()) == sites,
        "no_task_attempted_twice_by_mistake": set(attempts) <= {1},
        "no_same_domain_overlap": overlaps == 0,
        "work_shared_by_all_processes": len({w.rsplit("-", 1)[0] for w in per_worker}) == workers,
        # the fake workload is designed so that ~88% of sites are good (incl. 2% partial and 1% redirected), the rest fail / park / block
        "outcomes_as_designed": (statuses.get("crawled", 0) + statuses.get("redirected", 0)) >= 0.80 * sites and statuses.get("parked", 0) >= 1 and pages > 3 * sites,
    }
    engine.dispose()
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="sqlite", help="'sqlite' or a PostgreSQL SQLAlchemy URL (postgresql+psycopg://...)")
    parser.add_argument("--sites", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[5, 10, 20])
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    label = "postgresql" if args.db.startswith("postgres") else "sqlite"
    out_dir = Path(args.out) if args.out else ROOT / "crawl_eval" / "results" / f"scale_{label}_{datetime.now():%Y%m%d-%H%M%S}"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for c in args.concurrency:
        print(f"--- {label}: {args.sites} sites, {args.workers} worker processes x concurrency {c}", flush=True)
        row = run_level(args.db, args.sites, c, args.workers, out_dir)
        rows.append(row)
        print(json.dumps({k: row[k] for k in ("wall_seconds", "sites_per_hour_THIS_RUN_ONLY", "website_status", "same_domain_overlaps", "peak_rss_mb_per_worker_process", "checks")}, indent=1), flush=True)
    (out_dir / "scale_results.json").write_text(json.dumps(rows, indent=1, default=str), encoding="utf-8")
    lines = [f"# Local scale test on {label} ({datetime.now():%Y-%m-%d %H:%M})", "", "Fake in-memory sites, no real website contacted; politeness spacing shortened (the spacing logic is unit-tested). "
             "Numbers describe this machine and this workload only.", "",
             "| Concurrency per process | Processes | Wall s | Sites/hour (this run) | Pages saved | Overlaps | Peak MB per process | All checks |", "|---|---:|---:|---:|---:|---:|---|---|"]
    for r in rows:
        lines.append(f"| {r['concurrency_per_worker']} | {r['worker_processes']} | {r['wall_seconds']} | {r['sites_per_hour_THIS_RUN_ONLY']} | {r['pages_saved']} | {r['same_domain_overlaps']} | "
                     f"{r['peak_rss_mb_per_worker_process']} | {'PASS' if all(r['checks'].values()) else 'FAIL ' + str([k for k, v in r['checks'].items() if not v])} |")
    (out_dir / "scale_results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if all(all(r["checks"].values()) for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
