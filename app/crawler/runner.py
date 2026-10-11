"""Queue runner: put websites on the durable queue, crawl them with a bounded pool of workers, write results (CR-A12, A13, G01-G03, G05, G06).

`run()` is the batch entry point used by the CLI, the web app and the evaluation harness: it queues the selected websites as one job and
works that job off. `run_worker()` is the long-running worker process (`python -m app.crawler.worker`): it works the whole queue, so several
worker processes can share one database. Both use the same loop, so a test of one is a test of the other.

Guarantees:
- one failing website never stops the batch; the failure keeps an actionable reason (CR-G06)
- every task has a lease that is renewed while it runs; a dead worker's tasks come back (CR-A13)
- cancel is noticed within about a second and stops running crawls at once (ISS-23)
- at most `concurrency` sites run at the same time, and never two for one domain (CR-F03, F07, G02)
- database work runs in a thread, one operation at a time per process, so the event loop is never blocked by it
"""

from __future__ import annotations

import asyncio
import os
import socket
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select, update

import app.settings as settings
from app.crawler import config, queue
from app.crawler.client import new_client
from app.crawler.fetcher import RobotsRules
from app.crawler.pipeline import CrawlResult, crawl_one
from app.crawler.persist import save_details
from app.database import get_session
from app.limits import crawl_concurrency
from app.models import Job, Website
from app.observe import log_event
from app.profile import apply_crawl_result, record_domain
from app.recovery import release_stale_claims, utcnow

RETRYABLE_CATEGORIES = {"timeout", "network", "http_5xx", "rate_limited", "robots_unavailable"}
LEASE_SECONDS = 600
HEARTBEAT_SECONDS = 60


@dataclass
class RunSummary:
    total: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    seconds: float = 0.0


# Only one batch run at a time per process: two runs would fight over the same job bookkeeping.
_RUNNING = False
_DB_LOCK = threading.Lock()


def _utcnow() -> datetime:
    return utcnow()


async def _db(fn, *args):
    """Run a database function in a thread, one at a time per process (SQLite stays happy, the event loop never waits for the database)."""
    def call():
        with _DB_LOCK:
            return fn(*args)

    return await asyncio.to_thread(call)


# ----------------------------------------------------------------------------------------------- selection and bookkeeping
def _claim(site_ids: list[int] | None, limit: int | None, force: bool) -> tuple[list[tuple[int, str]], int | None]:
    """Select the target rows, put them on the queue as one crawl job, and return plain (id, normalized_website) tuples.

    No ORM instances leave this function, so nothing can hit a detached-session error later. A crawl job id is returned when at least one row
    was queued.
    """
    with get_session() as session:
        # Rows with no claim time, or a claim older than the stuck window, belong to a run that did not finish.
        release_stale_claims(session)

        stmt = select(Website).order_by(Website.id)
        if site_ids:
            stmt = stmt.where(Website.id.in_(site_ids))
        elif not force:
            stmt = stmt.where(Website.status == config.STATUS_PENDING)
        if limit:
            stmt = stmt.limit(limit)

        claims = [(site.id, site.normalized_website) for site in session.scalars(stmt)]
        job_id = None
        if claims:
            job = Job(kind="crawl", status="running", added=len(claims), total=len(claims))
            session.add(job)
            session.flush()
            job_id = job.id
            queue.enqueue(session, [site_id for site_id, _url in claims], job_id=job_id)
        session.commit()
    return claims, job_id


def _save(site_id: int, result: CrawlResult) -> None:
    website = ""
    now = _utcnow()
    with get_session() as session:
        site = session.get(Website, site_id)
        if site is None:
            return
        website = site.normalized_website
        apply_crawl_result(site, result, now, retry_count=result.attempt_no or None)
        save_details(session, site, result, now, job_id=result.job_id, retry_count=result.attempt_no or 0)
        session.commit()
    if website:
        record_domain(website, result, now)


def _is_cancelled(job_id: int | None) -> bool:
    if job_id is None:
        return False
    with get_session() as session:
        job = session.get(Job, job_id)
        return job is not None and job.status == "cancelled"


def _close_job(job_id: int | None, status: str, summary: RunSummary, note: str = "") -> None:
    if job_id is None:
        return
    with get_session() as session:
        job = session.get(Job, job_id)
        if job is None:
            return
        job.status = status
        job.finished_at = _utcnow()
        job.added = summary.total
        job.done_count = sum(n for s, n in summary.counts.items() if s in ("crawled", "redirected"))
        job.failed_count = sum(n for s, n in summary.counts.items() if s not in ("crawled", "redirected"))
        job.note = note or ", ".join(f"{name}={count}" for name, count in sorted(summary.counts.items()))
        session.commit()


def _release_unfinished(site_ids: list[int]) -> None:
    """Rows this run claimed but did not finish go back to where they were: pending (or their classification status)."""
    if not site_ids:
        return
    with get_session() as session:
        sites = session.scalars(
            select(Website).where(Website.id.in_(site_ids), Website.status.in_((config.STATUS_CRAWLING, config.STATUS_QUEUED, config.STATUS_EXTRACTING)))
        )
        for site in sites:
            site.claimed_at = None
            if site.classification_status:
                site.status = site.classification_status
                site.crawl_status = site.crawl_status if site.crawl_status not in (config.STATUS_QUEUED, config.STATUS_CRAWLING) else config.STATUS_CRAWLED
            else:
                site.status = config.STATUS_PENDING
                site.crawl_status = config.STATUS_PENDING
        session.commit()


def _cancel_unfinished_tasks(job_id: int | None) -> None:
    if job_id is None:
        return
    with get_session() as session:
        queue.cancel_job(session, job_id, include_scheduled=False)


# ----------------------------------------------------------------------------------------------- queue operations (thread side)
def _claim_task(worker_id: str, job_id: int | None):
    with get_session() as session:
        return queue.claim_next(session, worker_id, job_id=job_id, lease_seconds=LEASE_SECONDS)


def _open_count(job_id: int | None) -> int:
    with get_session() as session:
        return queue.open_count(session, job_id)


def _heartbeat(task_id: int, worker_id: str) -> bool:
    with get_session() as session:
        return queue.heartbeat(session, task_id, worker_id, LEASE_SECONDS)


def _task_state(task_id: int, state: str) -> None:
    with get_session() as session:
        queue.set_state(session, task_id, state)


def _finish_task(task_id: int, state: str, error: str | None, delay: float | None, website_id: int | None = None) -> None:
    with get_session() as session:
        not_before = _utcnow() + timedelta(seconds=delay) if delay else None
        queue.finish(session, task_id, state, error, not_before)
        if state == "retry_scheduled" and website_id is not None:  # the row shows when the next attempt will happen
            session.execute(update(Website).where(Website.id == website_id).values(next_retry_at=not_before))
            session.commit()


def _decide(result: CrawlResult, attempt: int, max_attempts: int = queue.MAX_ATTEMPTS) -> tuple[str, float | None]:
    """('done', None) or ('retry_scheduled', seconds). Transient failures are tried again later; permanent ones are final."""
    transient = result.retry_after is not None or result.error_category in RETRYABLE_CATEGORIES or (result.error_category == "dns" and attempt < 2)
    if result.status in ("crawled", "redirected") or not transient or attempt >= max_attempts:
        return "done", None
    return "retry_scheduled", queue.retry_delay_seconds(attempt, result.retry_after)


# ----------------------------------------------------------------------------------------------- the worker loop
async def _crawl_guarded(client, url: str, robots_cache: dict[str, RobotsRules]) -> CrawlResult:
    try:
        return await asyncio.wait_for(crawl_one(client, url, robots_cache), timeout=config.SITE_DEADLINE + 180)
    except asyncio.CancelledError:
        raise
    except asyncio.TimeoutError:
        return CrawlResult(config.STATUS_FAILED, None, f"site time limit exceeded ({config.SITE_DEADLINE + 180:g}s)", 0, error_category="timeout")
    except Exception as exc:  # noqa: BLE001 - one site must never kill the batch; the reason is kept
        return CrawlResult(config.STATUS_FAILED, None, f"unexpected error: {exc}", 0, error_category="unexpected")


async def _drain(job_id: int | None, concurrency: int, log, summary: RunSummary, total: int, stop_when_empty: bool = True, poll: float = 2.0,
                 stop_event: asyncio.Event | None = None) -> bool:
    """Work the queue (one job, or everything when job_id is None). Returns True when the job was cancelled."""
    stop = stop_event or asyncio.Event()
    running: dict[int, asyncio.Task] = {}
    cancelled = {"flag": False}
    done_n = {"n": 0}
    robots_cache: dict[str, RobotsRules] = {}
    worker_ids = [f"{socket.gethostname()}-{os.getpid()}-{n}" for n in range(concurrency)]

    async with new_client() as client:

        async def watch_cancel() -> None:
            while not stop.is_set():
                await asyncio.sleep(0.5)
                if await _db(_is_cancelled, job_id):
                    cancelled["flag"] = True
                    stop.set()
                    for crawl in list(running.values()):
                        crawl.cancel()
                    return

        async def keep_lease(task_id: int, worker_id: str, crawl: asyncio.Task) -> None:
            while True:
                await asyncio.sleep(HEARTBEAT_SECONDS)
                if not await _db(_heartbeat, task_id, worker_id):
                    crawl.cancel()  # the lease is gone (cancelled, or taken over after a recovery): stop working on it
                    return

        async def process(claimed, worker_id: str) -> None:
            crawl = asyncio.create_task(_crawl_guarded(client, claimed.url, robots_cache))
            running[claimed.task_id] = crawl
            lease = asyncio.create_task(keep_lease(claimed.task_id, worker_id, crawl))
            await _db(_task_state, claimed.task_id, "crawling")
            try:
                try:
                    result = await crawl
                except asyncio.CancelledError:
                    if not crawl.cancelled():
                        raise  # this worker itself is being cancelled
                    result = None
            finally:
                lease.cancel()
                running.pop(claimed.task_id, None)
            if result is None:  # cancelled: nothing is saved; the row is released at the end of the run
                await _db(_finish_task, claimed.task_id, "cancelled", "cancelled while running", None)
                return
            result.job_id = claimed.job_id
            result.attempt_no = claimed.attempt
            await _db(_task_state, claimed.task_id, "extracting")
            try:
                await _db(_save, claimed.website_id, result)
            except Exception as exc:  # noqa: BLE001 - a failed save must not kill the worker; the task keeps the reason
                log_event("save_failed", site_id=claimed.website_id, task_id=claimed.task_id, error=f"{type(exc).__name__}: {exc}")
                await _db(_finish_task, claimed.task_id, "failed", f"result could not be saved: {type(exc).__name__}: {exc}"[:500], None)
                summary.counts["failed"] = summary.counts.get("failed", 0) + 1
                return
            state, delay = _decide(result, claimed.attempt)
            await _db(_finish_task, claimed.task_id, state, result.error if state != "done" else None, delay, claimed.website_id)
            summary.counts[result.status] = summary.counts.get(result.status, 0) + 1
            done_n["n"] += 1
            if done_n["n"] % 10 == 0 or (total and done_n["n"] == total):
                log(f"  {done_n['n']}/{total or '?'} done — {result.status} (site #{claimed.website_id})")

        async def worker(worker_id: str) -> None:
            while not stop.is_set():
                claimed = await _db(_claim_task, worker_id, job_id)
                if claimed is None:
                    if stop_when_empty and await _db(_open_count, job_id) == 0:
                        return
                    await asyncio.sleep(0.05 if stop_when_empty else poll)
                    continue
                await process(claimed, worker_id)

        watcher = asyncio.create_task(watch_cancel())
        workers = [asyncio.create_task(worker(wid)) for wid in worker_ids]
        try:
            await asyncio.gather(*workers)
        finally:
            stop.set()
            for crawl in list(running.values()):
                crawl.cancel()
            watcher.cancel()
            for w in workers:
                w.cancel()
            await asyncio.gather(watcher, *workers, return_exceptions=True)
    return cancelled["flag"]


async def _shutdown_browser() -> None:
    from app.crawler.browser import shutdown_browser

    await shutdown_browser()


# ----------------------------------------------------------------------------------------------- entry points
async def run(
    limit: int | None = None,
    site_ids: list[int] | None = None,
    force: bool = False,
    concurrency: int | None = None,
    log=print,
) -> RunSummary:
    """Crawl pending websites and fill clean_text. Returns a summary."""
    global _RUNNING
    if _RUNNING:
        log("A crawl run is already active — wait for it to finish.")
        return RunSummary()

    settings.effective_contact()  # production without CRAWLER_CONTACT_URL stops here, with a message that says what to set
    started = time.monotonic()
    summary = RunSummary()
    _RUNNING = True
    try:
        return await _run_inside(limit, site_ids, force, concurrency, log, started, summary)
    finally:
        _RUNNING = False


async def _run_inside(
    limit: int | None,
    site_ids: list[int] | None,
    force: bool,
    concurrency: int | None,
    log,
    started: float,
    summary: RunSummary,
) -> RunSummary:
    targets, job_id = _claim(site_ids, limit, force)
    summary.total = len(targets)
    if not targets:
        log("Nothing to crawl.")
        return summary

    log_event("crawl_started", sites=len(targets), job_id=job_id)
    closed = False
    cancelled = False
    try:
        cancelled = await _drain(job_id, concurrency or crawl_concurrency(), log, summary, len(targets))
        summary.seconds = round(time.monotonic() - started, 1)
        if cancelled:
            _close_job(job_id, "cancelled", summary, "Cancelled by an operator.")
            log_event("crawl_cancelled", sites=summary.total, job_id=job_id)
        else:
            _close_job(job_id, "completed", summary)
            log_event("crawl_finished", sites=summary.total, seconds=summary.seconds, counts=summary.counts, job_id=job_id)
        closed = True
        return summary
    finally:
        _cancel_unfinished_tasks(job_id)
        _release_unfinished([site_id for site_id, _url in targets])
        try:
            await _shutdown_browser()
        except Exception:  # noqa: BLE001 - never hide the real outcome behind a shutdown problem
            pass
        if not closed:
            summary.seconds = round(time.monotonic() - started, 1)
            _close_job(job_id, "failed", summary, "Crawl stopped before it finished.")
            log_event("crawl_failed", sites=summary.total, job_id=job_id)


async def run_worker(concurrency: int | None = None, forever: bool = False, poll: float = 5.0, log=print, enqueue_pending: bool = True,
                     limit: int | None = None, stop_event: asyncio.Event | None = None) -> RunSummary:
    """A worker process: recover expired leases, queue pending websites, then work the whole queue (until empty, or forever)."""
    settings.effective_contact()
    started = time.monotonic()
    summary = RunSummary()
    recovered = await _db(_recover_expired)
    if recovered:
        log(f"Re-queued {recovered} task(s) whose worker stopped.")
    if enqueue_pending:
        summary.total = await _db(_enqueue_pending, limit)
        log(f"Queued {summary.total} pending website(s).")
    workers = concurrency or crawl_concurrency()
    try:
        await _drain(None, workers, log, summary, summary.total, stop_when_empty=not forever, poll=poll, stop_event=stop_event)
    finally:
        await _db(_release_own_tasks, f"{socket.gethostname()}-{os.getpid()}-")
        try:
            await _shutdown_browser()
        except Exception:  # noqa: BLE001
            pass
        summary.seconds = round(time.monotonic() - started, 1)
    return summary


def _recover_expired() -> int:
    with get_session() as session:
        return queue.recover_expired(session)


def _enqueue_pending(limit: int | None) -> int:
    with get_session() as session:
        job = Job(kind="crawl", status="running", note="worker")
        session.add(job)
        session.flush()
        created = queue.enqueue_pending(session, limit=limit, job_id=job.id)
        job.total = job.added = created
        job.status = "completed" if not created else "running"
        session.commit()
        return created


def _release_own_tasks(prefix: str) -> None:
    """Clean shutdown: tasks this process still holds go back to the queue at once instead of waiting for the lease to run out."""
    from sqlalchemy import update

    from app.models import CrawlTask, TASK_RUNNING_STATES

    with get_session() as session:
        ids = list(session.scalars(select(CrawlTask.id).where(CrawlTask.state.in_(TASK_RUNNING_STATES), CrawlTask.worker_id.like(prefix + "%"))))
        for task_id in ids:
            session.execute(update(CrawlTask).where(CrawlTask.id == task_id).values(state="queued", worker_id=None, lease_until=None,
                                                                                     last_error="released by a clean shutdown"))
        if ids:
            session.execute(update(Website).where(Website.id.in_(select(CrawlTask.website_id).where(CrawlTask.id.in_(ids))),
                                                  Website.status == config.STATUS_CRAWLING).values(status=config.STATUS_QUEUED, claimed_at=None))
        session.commit()
