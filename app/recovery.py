"""Return interrupted crawl rows and jobs to a state a new run can continue (CR-A13, G02, K05).

A website left in `crawling` with no claim time, or a claim older than CRAWL_STUCK_MINUTES, is put back to `pending`. Queue tasks whose lease
ran out go back to `queued`. Crawl and classify jobs left `running` past that same window are marked failed. A single-process start
(`recover_abandoned`) resets every in-progress claim, because that process owns nothing yet; several workers use lease expiry instead
(`app.crawler.queue.recover_expired`) so they never take work from each other.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.limits import stuck_minutes
from app.models import TASK_RUNNING_STATES, CrawlTask, Job, Website

ACTIVE_KINDS = ("crawl", "classify")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fail_jobs(session: Session, jobs: list[Job], now: datetime, note: str) -> int:
    for job in jobs:
        job.status = "failed"
        job.finished_at = now
        job.note = note
    return len(jobs)


def release_stale_claims(session: Session, now: datetime | None = None) -> dict[str, int]:
    """Reset claims that are old enough that their worker is no longer running."""
    from app.crawler.queue import recover_expired

    now = now or utcnow()
    cutoff = now - timedelta(minutes=stuck_minutes())
    tasks = recover_expired(session, now)
    sites = list(
        session.scalars(
            select(Website).where(
                Website.status == "crawling",
                or_(Website.claimed_at.is_(None), Website.claimed_at < cutoff),
            )
        )
    )
    for site in sites:
        site.status = "pending"
        site.claimed_at = None
        # a task that is still waiting for this row would make the row look busy: put it back in the queue's hands
        session.execute(update(CrawlTask).where(CrawlTask.website_id == site.id, CrawlTask.state.in_(TASK_RUNNING_STATES))
                        .values(state="cancelled", lease_until=None, last_error="row reset by recovery"))
    jobs = list(
        session.scalars(
            select(Job).where(
                Job.kind.in_(ACTIVE_KINDS),
                Job.status == "running",
                Job.created_at < cutoff,
            )
        )
    )
    failed = _fail_jobs(session, jobs, now, "Interrupted. Stuck website rows were returned to the queue.")
    result = {"websites_reset": len(sites), "jobs_failed": failed}
    if tasks:
        result["tasks_requeued"] = tasks  # only reported when there was something to re-queue (keeps the old result shape)
    return result


def recover_abandoned(now: datetime | None = None) -> dict[str, int]:
    """Reset every in-progress claim. Call this when a single process starts."""
    from app.database import get_session

    now = now or utcnow()
    with get_session() as session:
        sites = list(session.scalars(select(Website).where(Website.status == "crawling")))
        for site in sites:
            site.status = "pending"
            site.claimed_at = None
        tasks = session.execute(
            update(CrawlTask).where(CrawlTask.state.in_(TASK_RUNNING_STATES))
            .values(state="cancelled", lease_until=None, last_error="reset by a restart")
        ).rowcount
        jobs = list(
            session.scalars(
                select(Job).where(Job.kind.in_(ACTIVE_KINDS), Job.status == "running")
            )
        )
        failed = _fail_jobs(
            session,
            jobs,
            now,
            "Interrupted by a restart. Website rows were returned to the queue.",
        )
        session.commit()
        result = {"websites_reset": len(sites), "jobs_failed": failed}
        if tasks:
            result["tasks_reset"] = tasks
        return result
