"""A crawl worker process. Start as many as the machine and the target sites can take; they share the queue in the database (CR-G03).

    python -m app.crawler.worker                       # queue pending websites, work until the queue is empty
    python -m app.crawler.worker --workers 5           # 5 sites at the same time in this process
    python -m app.crawler.worker --forever --poll 5    # keep waiting for new work
    python -m app.crawler.worker --no-enqueue          # only work what is already queued

Several processes can run at once (they never crawl the same domain at the same time). Ctrl-C releases this worker's tasks back to the queue.
AI workers are a different program (python -m app.classifier), so crawl and AI capacity scale independently.
"""

from __future__ import annotations

import argparse
import asyncio

from app.crawler.runner import run_worker
from app.database import init_db
from app.limits import crawl_concurrency
from app.settings import SettingsError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crawl worker: works the shared crawl queue.")
    parser.add_argument("--workers", type=int, default=None, help=f"sites crawled at the same time in this process (default {crawl_concurrency()})")
    parser.add_argument("--forever", action="store_true", help="keep polling for new work instead of stopping when the queue is empty")
    parser.add_argument("--poll", type=float, default=5.0, help="seconds between polls when the queue is empty (with --forever)")
    parser.add_argument("--no-enqueue", action="store_true", help="do not queue pending websites first")
    parser.add_argument("--limit", type=int, default=None, help="queue at most this many pending websites")
    args = parser.parse_args(argv)

    init_db()
    try:
        summary = asyncio.run(run_worker(args.workers, args.forever, args.poll, enqueue_pending=not args.no_enqueue, limit=args.limit))
    except SettingsError as exc:
        print(f"Cannot start: {exc}")
        return 2
    except KeyboardInterrupt:
        print("Stopped. Tasks held by this worker were released back to the queue.")
        return 130
    print(f"\nWorker finished in {summary.seconds}s")
    for status, count in sorted(summary.counts.items()):
        print(f"  {status:<18} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
