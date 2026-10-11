"""Operator commands: import, queue, requeue, recrawl, metrics, export, report, backup, recover, benchmark, cancel.

    python -m app.ops import urls.csv --source "march batch"     # CSV / XLSX / one URL per line
    python -m app.ops import-from-db --dsn postgresql://... --table companies --url-col website --id-col id
    python -m app.ops enqueue [--limit 1000]                    # put pending websites on the queue
    python -m app.ops queue-status
    python -m app.ops requeue --status failed --status unreachable    # manual re-queue (CR-F09); or --url / --id
    python -m app.ops recrawl --older-than 90                   # websites last crawled more than 90 days ago (CR-A09)
    python -m app.ops metrics [--json]                          # success rate, latency, errors, throughput (CR-G04)
    python -m app.ops export-crawl crawl.xlsx                   # crawl columns + Crawled Pages + Errors (CR-H04, H05)
    python -m app.ops report | backup | recover | benchmark | cancel --job 4 | purge-raw
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine, select, text, update

from app.backup import backup_database
from app.benchmark import measure
from app.crawler import queue
from app.crawler.persist import purge_raw_html
from app.crawler.reports import crawl_metrics, write_crawl_export
from app.database import get_session, init_db
from app.importer import excel_to_text, import_urls
from app.models import CrawlTask, Job, Website
from app.normalize import normalize_website
from app.recovery import recover_abandoned, utcnow
from app.report import build_report

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


def _print_report(report: dict) -> None:
    print(f"Websites saved: {report['websites']}")
    print(f"Crawl finished: {report['crawl_finished']}")
    print(f"With useful text: {report['useful_text']}")
    print(f"Crawl success rate: {report['crawl_success_rate']}")
    print(f"Browser fallback sites: {report['browser_fallback_sites']}")
    print(f"Classification attempts: {report['classification_attempted']}")
    print(f"Insufficient-evidence rate: {report['insufficient_evidence_rate']}")
    print(f"Needs-review rate: {report['needs_review_rate']}")
    print(f"Average confidence: {report['average_confidence']}")
    print("Status counts:")
    for status, count in sorted(report["by_status"].items()):
        print(f"  {status:<24} {count}")
    scale = report["scale"]
    print(f"Scale stage: {scale['stage']}")
    print(f"Production ready: {scale['production_ready']}")
    print(scale["next_step"])


def read_url_file(path: Path) -> str:
    """Text of an import file: .xlsx (first sheet) or plain text / CSV."""
    data = Path(path).read_bytes()
    if Path(path).suffix.lower() in (".xlsx", ".xlsm"):
        return excel_to_text(data)
    return data.decode("utf-8-sig", errors="replace")


def read_external_urls(dsn: str, table: str, url_col: str, id_col: str | None = None, limit: int | None = None) -> str:
    """Read URLs from an existing database or staging table (CR-A03). Read-only: one SELECT, identifiers are validated."""
    for name in (table, url_col, id_col or "x"):
        if not _IDENT.match(name):
            raise SystemExit(f"Not a plain table/column name: {name!r}")
    sql = f"SELECT {url_col} AS url, {id_col or 'NULL'} AS record_id FROM {table}" + (f" LIMIT {int(limit)}" if limit else "")
    engine = create_engine(dsn)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["url", "id"])
    with engine.connect() as conn:
        for url, record_id in conn.execute(text(sql)):
            if url:
                writer.writerow([str(url).strip(), "" if record_id is None else record_id])
    engine.dispose()
    return buffer.getvalue()


def requeue(statuses: list[str] | None = None, urls: list[str] | None = None, ids: list[int] | None = None) -> int:
    """Manual re-queue of failed websites (CR-F09, A04): back to 'pending' with a fresh task. Returns the number of websites."""
    with get_session() as session:
        stmt = select(Website)
        if ids:
            stmt = stmt.where(Website.id.in_(ids))
        elif urls:
            stmt = stmt.where(Website.normalized_website.in_([normalize_website(u) or u for u in urls]))
        elif statuses:
            stmt = stmt.where(Website.status.in_(statuses))
        else:
            return 0
        sites = list(session.scalars(stmt))
        for site in sites:
            session.execute(update(CrawlTask).where(CrawlTask.website_id == site.id, CrawlTask.state.in_(("queued", "retry_scheduled")))
                            .values(state="cancelled", last_error="re-queued by an operator"))
            site.status = "pending"
            site.crawl_status = "pending"
            site.next_retry_at = None
            site.claimed_at = None
        session.commit()
        return len(sites)


def recrawl(older_than_days: int, limit: int | None = None) -> int:
    """Mark websites for a re-crawl after a configurable period (CR-A09). A classification stays until the text really changes."""
    cutoff = utcnow() - timedelta(days=older_than_days)
    with get_session() as session:
        stmt = select(Website).where(Website.last_crawled_at.is_not(None), Website.last_crawled_at < cutoff,
                                     Website.status.notin_(("pending", "queued", "crawling", "extracting"))).order_by(Website.last_crawled_at)
        if limit:
            stmt = stmt.limit(limit)
        sites = list(session.scalars(stmt))
        for site in sites:
            site.status = "pending"
            site.crawl_status = "pending"
        session.commit()
        return len(sites)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Import, queue, report, export, backup and recover.")
    parser.add_argument("command", choices=("report", "backup", "recover", "benchmark", "cancel", "import", "import-from-db", "enqueue", "queue-status",
                                            "requeue", "recrawl", "metrics", "export-crawl", "purge-raw"))
    parser.add_argument("target", nargs="?", help="file for import / export-crawl")
    parser.add_argument("--job", type=int, default=None, help="job id for cancel")
    parser.add_argument("--rows", type=int, default=200, help="rows for the local benchmark")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--source", default=None, help="batch name stored with imported rows")
    parser.add_argument("--dsn", default=None, help="import-from-db: SQLAlchemy URL of the source database")
    parser.add_argument("--table", default=None)
    parser.add_argument("--url-col", default=None)
    parser.add_argument("--id-col", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--status", action="append", default=None, help="requeue: websites with this status (repeatable)")
    parser.add_argument("--url", action="append", default=None, help="requeue: this website (repeatable)")
    parser.add_argument("--id", dest="ids", action="append", type=int, default=None, help="requeue: this row id (repeatable)")
    parser.add_argument("--older-than", type=int, default=None, help="recrawl: days since the last crawl")
    args = parser.parse_args(argv)

    init_db()
    if args.command == "report":
        with get_session() as session:
            report = build_report(session)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            _print_report(report)
        return
    if args.command == "backup":
        path = backup_database()
        print(f"Backup written to {path}")
        return
    if args.command == "recover":
        result = recover_abandoned()
        print(
            f"Reset {result['websites_reset']} crawling website(s). "
            f"Marked {result['jobs_failed']} interrupted job(s) failed."
        )
        return
    if args.command == "cancel":
        if args.job is None:
            raise SystemExit("Pass --job with the id of a running job.")
        with get_session() as session:
            job = session.get(Job, args.job)
            if job is None or job.status != "running":
                raise SystemExit("That job is not running.")
            job.status = "cancelled"
            job.finished_at = utcnow()
            job.note = "Cancelled by an operator."
            session.commit()
            queue.cancel_job(session, args.job)
        print(f"Job {args.job} cancelled.")
        return
    if args.command in ("import", "import-from-db"):
        if args.command == "import":
            if not args.target:
                raise SystemExit("Pass the file to import.")
            text_data, name = read_url_file(Path(args.target)), Path(args.target).name
        else:
            if not (args.dsn and args.table and args.url_col):
                raise SystemExit("import-from-db needs --dsn, --table and --url-col.")
            text_data, name = read_external_urls(args.dsn, args.table, args.url_col, args.id_col, args.limit), f"db:{args.table}"
        with get_session() as session:
            result = import_urls(session, text_data, source_batch=args.source, source_file=name)
        print(f"Import {name}: added {result.added}, duplicates {len(result.duplicates)}, invalid {len(result.invalid)} (job {result.job_id}).")
        return
    if args.command == "enqueue":
        with get_session() as session:
            created = queue.enqueue_pending(session, limit=args.limit)
            session.commit()
        print(f"Queued {created} pending website(s).")
        return
    if args.command == "queue-status":
        with get_session() as session:
            counts = queue.counts_by_state(session)
        for state, n in sorted(counts.items()):
            print(f"  {state:<20} {n}")
        if not counts:
            print("  (queue is empty)")
        return
    if args.command == "requeue":
        print(f"Re-queued {requeue(args.status, args.url, args.ids)} website(s) (status 'pending'; run a worker to crawl them).")
        return
    if args.command == "recrawl":
        if args.older_than is None:
            raise SystemExit("Pass --older-than with a number of days.")
        print(f"Marked {recrawl(args.older_than, args.limit)} website(s) for re-crawl.")
        return
    if args.command == "metrics":
        with get_session() as session:
            metrics = crawl_metrics(session)
        if args.json:
            print(json.dumps(metrics, indent=2, default=str))
        else:
            for key, value in metrics.items():
                print(f"{key}: {value}")
        return
    if args.command == "export-crawl":
        if not args.target:
            raise SystemExit("Pass the output file (.xlsx or .csv).")
        with get_session() as session:
            counts = write_crawl_export(session, Path(args.target))
        print(f"Exported {counts['websites']} website(s), {counts['pages']} page(s), {counts['errors']} error row(s) to {args.target}")
        return
    if args.command == "purge-raw":
        print(f"Removed {purge_raw_html()} raw HTML file(s) past the retention period.")
        return
    result = measure(args.rows)
    print(
        f"Measured {result.rows} local rows in {result.filter_ms} ms (filter) "
        f"and {result.export_ms} ms (export shaping). Matched {result.matched}."
    )
    print(result.note)


if __name__ == "__main__":
    main()
