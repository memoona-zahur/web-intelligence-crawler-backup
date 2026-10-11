"""The durable crawl queue, stored in the database (CR-A12, A13, G01, G02, G03, F07, K05).

Why a table and not Redis/Celery: the queue and the crawl data change in the same transaction, a restart loses nothing, and no extra server is
needed (Redis has no native Windows build; Celery does not support Windows). Decision pending sir confirmation - see docs/open-questions-for-sir.md.

Rules enforced here:
- one active task per website (partial unique index uq_crawl_tasks_active_website)
- one RUNNING task per domain (partial unique index uq_crawl_tasks_running_domain): two workers can never crawl one domain at the same time
- a task is leased for a limited time; a worker that dies simply stops renewing it and the task is picked up again (recover_expired)
- a domain whose health says 'back off' is not claimed until the back-off is over (domain_stats is READ here, ISS-22)
- idempotent: enqueue never creates a second active task; claiming is a conditional UPDATE, so two claimers cannot both win
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crawler import config
from app.domains import domain_key, host_of
from app.models import TASK_ACTIVE_STATES, TASK_RUNNING_STATES, CrawlTask, DomainStat, Website
from app.recovery import utcnow

RUNNABLE_STATES = ("queued", "retry_scheduled")
TERMINAL_STATES = ("done", "failed", "cancelled", "insufficient_evidence")
DEFAULT_LEASE_SECONDS = 600
MAX_ATTEMPTS = 3
RETRY_BASE_SECONDS = 900          # 15 minutes, doubled per attempt (robots 5xx, unreachable, 429 ...)
RETRY_MAX_SECONDS = 24 * 3600


@dataclass
class ClaimedTask:
    task_id: int
    website_id: int
    url: str
    attempt: int
    job_id: int | None
    domain_key: str


def enqueue(session: Session, website_ids: list[int], job_id: int | None = None, priority: int = 0) -> int:
    """Create a queued task for every website that has no active task yet. Returns the number of tasks created."""
    created = 0
    now = utcnow()
    for start in range(0, len(website_ids), 500):
        chunk = website_ids[start:start + 500]
        busy = {w: (tid, st) for w, tid, st in session.execute(
            select(CrawlTask.website_id, CrawlTask.id, CrawlTask.state).where(CrawlTask.website_id.in_(chunk), CrawlTask.state.in_(TASK_ACTIVE_STATES))).all()}
        for site in session.scalars(select(Website).where(Website.id.in_(chunk))):
            if site.id in busy:
                task_id, task_state = busy[site.id]
                if task_state in RUNNABLE_STATES:  # not running: hand it to this run and make it runnable now
                    session.execute(update(CrawlTask).where(CrawlTask.id == task_id).values(job_id=job_id, state="queued", not_before=None, priority=priority))
                    site.status = config.STATUS_QUEUED
                    site.crawl_status = config.STATUS_QUEUED
                    created += 1
                continue
            if not site.domain_key:
                site.domain_key = domain_key(site.normalized_website)
            session.add(CrawlTask(website_id=site.id, job_id=job_id, domain_key=site.domain_key or site.normalized_website, state="queued",
                                  attempt=0, max_attempts=MAX_ATTEMPTS, priority=priority, created_at=now))
            site.status = config.STATUS_QUEUED
            site.crawl_status = config.STATUS_QUEUED
            site.claimed_at = None
            created += 1
        session.flush()
    return created


def enqueue_pending(session: Session, limit: int | None = None, job_id: int | None = None) -> int:
    """Queue every website that is still 'pending' (an import creates pending rows; this is the step that queues them)."""
    stmt = select(Website.id).where(Website.status == config.STATUS_PENDING).order_by(Website.id)
    if limit:
        stmt = stmt.limit(limit)
    ids = list(session.scalars(stmt))
    return enqueue(session, ids, job_id=job_id)


def _host_backoffs(session: Session, hosts: set[str], now: datetime) -> dict[str, datetime]:
    if not hosts:
        return {}
    rows = session.execute(select(DomainStat.domain, DomainStat.backoff_until).where(DomainStat.domain.in_(hosts), DomainStat.backoff_until > now)).all()
    return {domain: until for domain, until in rows}


def claim_next(session: Session, worker_id: str, job_id: int | None = None, lease_seconds: int = DEFAULT_LEASE_SECONDS,
               now: datetime | None = None, candidates: int = 30) -> ClaimedTask | None:
    """Claim the next runnable task, or None. Safe with many workers (conditional UPDATE + unique index on the running domain)."""
    now = now or utcnow()
    running = CrawlTask.__table__.alias("running")
    stmt = (
        select(CrawlTask.id, CrawlTask.website_id, CrawlTask.job_id, CrawlTask.domain_key, CrawlTask.attempt, Website.normalized_website)
        .join(Website, Website.id == CrawlTask.website_id)
        .where(
            CrawlTask.state.in_(RUNNABLE_STATES),
            or_(CrawlTask.not_before.is_(None), CrawlTask.not_before <= now),
            ~exists().where(and_(running.c.domain_key == CrawlTask.domain_key, running.c.state.in_(TASK_RUNNING_STATES))),
        )
        .order_by(CrawlTask.priority.desc(), CrawlTask.id)
        .limit(candidates)
        .with_for_update(skip_locked=True, of=CrawlTask)
    )
    if job_id is not None:
        stmt = stmt.where(CrawlTask.job_id == job_id)
    rows = session.execute(stmt).all()
    if not rows:
        session.rollback()
        return None
    backoffs = _host_backoffs(session, {host_of(r.normalized_website).removeprefix("www.") for r in rows}, now)

    for row in rows:
        host = host_of(row.normalized_website).removeprefix("www.")
        if host in backoffs:  # domain health says 'wait': park the task until then instead of hammering the site
            session.execute(update(CrawlTask).where(CrawlTask.id == row.id, CrawlTask.state.in_(RUNNABLE_STATES))
                            .values(state="retry_scheduled", not_before=backoffs[host], last_error=f"domain back-off until {backoffs[host].isoformat(timespec='seconds')}"))
            session.commit()
            continue
        try:
            with session.begin_nested():
                result = session.execute(
                    update(CrawlTask)
                    .where(CrawlTask.id == row.id, CrawlTask.state.in_(RUNNABLE_STATES))
                    .values(state="claimed", worker_id=worker_id, attempt=CrawlTask.attempt + 1, started_at=now,
                            lease_until=now + timedelta(seconds=lease_seconds))
                )
                if result.rowcount != 1:
                    continue  # another worker was faster
                session.execute(update(Website).where(Website.id == row.website_id)
                                .values(status=config.STATUS_CRAWLING, crawl_status=config.STATUS_CRAWLING, claimed_at=now))
        except IntegrityError:
            continue  # the domain is being crawled by someone else right now
        session.commit()
        return ClaimedTask(row.id, row.website_id, row.normalized_website, row.attempt + 1, row.job_id, row.domain_key)
    session.commit()
    return None


def set_state(session: Session, task_id: int, state: str) -> None:
    session.execute(update(CrawlTask).where(CrawlTask.id == task_id).values(state=state))
    session.commit()


def heartbeat(session: Session, task_id: int, worker_id: str, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> bool:
    """Renew the lease. False when the task is no longer ours (cancelled or taken over)."""
    result = session.execute(update(CrawlTask).where(CrawlTask.id == task_id, CrawlTask.worker_id == worker_id, CrawlTask.state.in_(TASK_RUNNING_STATES))
                             .values(lease_until=utcnow() + timedelta(seconds=lease_seconds)))
    session.commit()
    return result.rowcount == 1


def retry_delay_seconds(attempt: int, retry_after: float | None = None) -> float:
    delay = min(RETRY_MAX_SECONDS, RETRY_BASE_SECONDS * (2 ** max(0, attempt - 1)))
    if retry_after:
        delay = max(delay, min(float(retry_after), RETRY_MAX_SECONDS))
    return delay


def finish(session: Session, task_id: int, state: str = "done", error: str | None = None, not_before: datetime | None = None) -> None:
    """Close a task: done / failed / insufficient_evidence, or retry_scheduled with a time (never loses the failure reason)."""
    values: dict = {"state": state, "finished_at": utcnow(), "lease_until": None, "last_error": error}
    if state == "retry_scheduled":
        values.update(not_before=not_before, finished_at=None, worker_id=None)
    session.execute(update(CrawlTask).where(CrawlTask.id == task_id).values(**values))
    session.commit()


def cancel_job(session: Session, job_id: int, include_scheduled: bool = True) -> int:
    """Cancel every task of a job that has not finished (scheduled retries too, unless told otherwise). Running crawls notice the job status."""
    states = TASK_ACTIVE_STATES if include_scheduled else tuple(s for s in TASK_ACTIVE_STATES if s != "retry_scheduled")
    result = session.execute(update(CrawlTask).where(CrawlTask.job_id == job_id, CrawlTask.state.in_(states))
                             .values(state="cancelled", finished_at=utcnow(), lease_until=None, last_error="cancelled by an operator"))
    session.commit()
    return result.rowcount


def recover_expired(session: Session, now: datetime | None = None, worker_id: str | None = None) -> int:
    """Tasks whose lease ran out (the worker died or hung) go back to the queue; their websites go back to 'queued'.

    With worker_id: release the tasks of that worker at once (clean shutdown). Returns the number of tasks recovered.
    """
    now = now or utcnow()
    cond = CrawlTask.state.in_(TASK_RUNNING_STATES)
    if worker_id is not None:
        cond = and_(cond, CrawlTask.worker_id == worker_id)
    else:
        cond = and_(cond, or_(CrawlTask.lease_until.is_(None), CrawlTask.lease_until < now))
    ids = list(session.execute(select(CrawlTask.id, CrawlTask.website_id).where(cond)).all())
    for task_id, website_id in ids:
        session.execute(update(CrawlTask).where(CrawlTask.id == task_id).values(state="queued", worker_id=None, lease_until=None,
                                                                              last_error="lease expired: worker stopped, task re-queued"))
        session.execute(update(Website).where(Website.id == website_id, Website.status == config.STATUS_CRAWLING)
                        .values(status=config.STATUS_QUEUED, crawl_status=config.STATUS_QUEUED, claimed_at=None))
    session.commit()
    return len(ids)


def open_count(session: Session, job_id: int | None = None, now: datetime | None = None) -> int:
    """Tasks that will run in this session of work: queued (runnable now), claimed, crawling, extracting. Scheduled retries do not count."""
    now = now or utcnow()
    stmt = select(func.count()).select_from(CrawlTask).where(
        or_(CrawlTask.state.in_(TASK_RUNNING_STATES),
            and_(CrawlTask.state == "queued", or_(CrawlTask.not_before.is_(None), CrawlTask.not_before <= now)))
    )
    if job_id is not None:
        stmt = stmt.where(CrawlTask.job_id == job_id)
    return int(session.scalar(stmt) or 0)


def counts_by_state(session: Session, job_id: int | None = None) -> dict[str, int]:
    stmt = select(CrawlTask.state, func.count()).group_by(CrawlTask.state)
    if job_id is not None:
        stmt = stmt.where(CrawlTask.job_id == job_id)
    return {state: n for state, n in session.execute(stmt).all()}
