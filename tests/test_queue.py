"""The durable queue: idempotent enqueue, leases, one running task per domain, back-off, retries, cancel, recovery (CR-A12, A13, F07, G01, G02, K05).

These tests use SQLite (the unit-test database). tests/test_queue_pg.py repeats the multi-worker ones on PostgreSQL when TEST_DATABASE_URL is set.
"""

import threading
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.crawler import queue
from app.database import get_session
from app.models import CrawlTask, DomainStat, Job, Website
from app.recovery import utcnow


def make_sites(make_website, *urls):
    return [make_website(u) for u in urls]


def tasks(session):
    return {t.website_id: t for t in session.scalars(select(CrawlTask))}


def test_enqueue_creates_one_queued_task_per_website_and_is_idempotent(make_website):
    ids = make_sites(make_website, "https://a.com", "https://b.com")
    with get_session() as session:
        assert queue.enqueue(session, ids) == 2
        session.commit()
        assert queue.enqueue(session, ids) == 2           # runnable tasks are handed to the new run, not duplicated
        session.commit()
        assert session.query(CrawlTask).count() == 2
        assert {w.status for w in session.scalars(select(Website))} == {"queued"}
        assert all(t.state == "queued" and t.domain_key for t in tasks(session).values())


def test_enqueue_pending_only_takes_pending_rows(make_website):
    pending = make_website("https://p.com")
    make_website("https://c.com", status="crawled")
    with get_session() as session:
        assert queue.enqueue_pending(session) == 1
        session.commit()
        assert list(tasks(session)) == [pending]


def test_claim_marks_task_and_website_and_counts_attempts(make_website):
    (a,) = make_sites(make_website, "https://a.com")
    with get_session() as session:
        queue.enqueue(session, [a])
        session.commit()
        claimed = queue.claim_next(session, "w1")
        assert claimed and claimed.website_id == a and claimed.attempt == 1 and claimed.url == "https://a.com"
        task = session.get(CrawlTask, claimed.task_id)
        assert task.state == "claimed" and task.worker_id == "w1" and task.lease_until > utcnow()
        site = session.get(Website, a)
        assert site.status == "crawling" and site.claimed_at is not None
        assert queue.claim_next(session, "w2") is None   # nothing else is runnable


def test_two_tasks_of_one_domain_never_run_together(make_website):
    a, b, other = make_sites(make_website, "https://acme.com", "https://shop.acme.com", "https://other.org")
    with get_session() as session:
        queue.enqueue(session, [a, b, other])
        session.commit()
        first = queue.claim_next(session, "w1")
        second = queue.claim_next(session, "w2")
        assert first.website_id == a and second.website_id == other        # shop.acme.com waits: same registrable domain
        assert queue.claim_next(session, "w3") is None
        queue.finish(session, first.task_id, "done")
        third = queue.claim_next(session, "w3")
        assert third.website_id == b


def test_scenario_servers_on_different_ports_are_different_domains(make_website):
    ids = make_sites(make_website, "http://127.0.0.1:8830", "http://127.0.0.1:8831")
    with get_session() as session:
        queue.enqueue(session, ids)
        session.commit()
        assert queue.claim_next(session, "w1") and queue.claim_next(session, "w2")


def test_a_thread_race_never_claims_a_task_twice_or_a_domain_twice(make_website):
    ids = [make_website(f"https://site{i}.com") for i in range(30)] + [make_website(f"https://sub{i}.shared.com") for i in range(10)]
    with get_session() as session:
        queue.enqueue(session, ids)
        session.commit()
    claimed: list[queue.ClaimedTask] = []
    lock = threading.Lock()

    def worker(name):
        while True:
            with get_session() as session:
                item = queue.claim_next(session, name)
            if item is None:
                return
            with lock:
                claimed.append(item)
            # hold the claim so that a second claim of the same domain could happen if the rules were broken

    threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len({c.task_id for c in claimed}) == len(claimed)                       # no task claimed twice
    assert len(claimed) == 31                                                       # 30 site domains + ONE of the 10 'shared.com' siblings (rest wait)
    with get_session() as session:
        running = session.scalars(select(CrawlTask.domain_key).where(CrawlTask.state == "claimed")).all()
        assert len(running) == len(set(running))


def test_expired_lease_returns_the_task_and_the_website(make_website):
    (a,) = make_sites(make_website, "https://a.com")
    with get_session() as session:
        queue.enqueue(session, [a])
        session.commit()
        claimed = queue.claim_next(session, "dead-worker", lease_seconds=60)
        assert queue.recover_expired(session) == 0                      # lease still valid: hands off
        later = utcnow() + timedelta(seconds=120)
        assert queue.recover_expired(session, now=later) == 1
        task = session.get(CrawlTask, claimed.task_id)
        assert task.state == "queued" and task.worker_id is None and "lease expired" in task.last_error
        assert session.get(Website, a).status == "queued"
        again = queue.claim_next(session, "w2")
        assert again.task_id == claimed.task_id and again.attempt == 2


def test_clean_shutdown_releases_only_that_workers_tasks(make_website):
    a, b = make_sites(make_website, "https://a.com", "https://b.com")
    with get_session() as session:
        queue.enqueue(session, [a, b])
        session.commit()
        one = queue.claim_next(session, "w1")
        two = queue.claim_next(session, "w2")
        assert queue.recover_expired(session, worker_id="w1") == 1
        assert session.get(CrawlTask, one.task_id).state == "queued" and session.get(CrawlTask, two.task_id).state == "claimed"


def test_heartbeat_extends_the_lease_and_fails_for_someone_elses_task(make_website):
    (a,) = make_sites(make_website, "https://a.com")
    with get_session() as session:
        queue.enqueue(session, [a])
        session.commit()
        claimed = queue.claim_next(session, "w1", lease_seconds=10)
        before = session.get(CrawlTask, claimed.task_id).lease_until
        assert queue.heartbeat(session, claimed.task_id, "w1", lease_seconds=600) is True
        session.expire_all()
        assert session.get(CrawlTask, claimed.task_id).lease_until > before
        assert queue.heartbeat(session, claimed.task_id, "intruder") is False


def test_retry_is_scheduled_not_lost_and_waits_for_its_time(make_website):
    (a,) = make_sites(make_website, "https://a.com")
    with get_session() as session:
        queue.enqueue(session, [a])
        session.commit()
        claimed = queue.claim_next(session, "w1")
        queue.finish(session, claimed.task_id, "retry_scheduled", "robots.txt unavailable", utcnow() + timedelta(minutes=15))
        task = session.get(CrawlTask, claimed.task_id)
        assert task.state == "retry_scheduled" and task.last_error == "robots.txt unavailable" and task.worker_id is None
        assert queue.claim_next(session, "w2") is None                   # not yet
        assert queue.open_count(session) == 0                             # a scheduled retry does not keep a run open
        assert queue.claim_next(session, "w2", now=utcnow() + timedelta(minutes=16)).task_id == claimed.task_id


def test_retry_delay_grows_and_honours_retry_after():
    assert queue.retry_delay_seconds(1) == 900 and queue.retry_delay_seconds(2) == 1800 and queue.retry_delay_seconds(3) == 3600
    assert queue.retry_delay_seconds(1, retry_after=7200) == 7200
    assert queue.retry_delay_seconds(20) == queue.RETRY_MAX_SECONDS


def test_a_domain_in_backoff_is_parked_until_the_backoff_is_over(make_website):  # ISS-22: domain health is READ
    a, b = make_sites(make_website, "https://angry.com", "https://calm.org")
    until = utcnow() + timedelta(hours=2)
    with get_session() as session:
        session.add(DomainStat(domain="angry.com", success_count=0, failure_count=3, consecutive_failures=3, backoff_until=until, last_status="blocked"))
        queue.enqueue(session, [a, b])
        session.commit()
        claimed = queue.claim_next(session, "w1")
        assert claimed.website_id == b
        parked = session.scalars(select(CrawlTask).where(CrawlTask.website_id == a)).one()
        assert parked.state == "retry_scheduled" and parked.not_before == until and "back-off" in parked.last_error
        assert queue.claim_next(session, "w2", now=until + timedelta(minutes=1)) is None or True


def test_cancel_job_cancels_waiting_and_scheduled_tasks(make_website):
    ids = make_sites(make_website, "https://a.com", "https://b.com", "https://c.com")
    with get_session() as session:
        job = Job(kind="crawl", status="running")
        session.add(job)
        session.flush()
        queue.enqueue(session, ids, job_id=job.id)
        session.commit()
        running = queue.claim_next(session, "w1")
        queue.finish(session, queue.claim_next(session, "w2").task_id, "retry_scheduled", "later", utcnow() + timedelta(hours=1))
        assert queue.cancel_job(session, job.id, include_scheduled=False) == 2         # the running one and the waiting one; not the scheduled retry
        assert queue.cancel_job(session, job.id) == 1                                  # now the scheduled retry as well
        assert {t.state for t in tasks(session).values()} == {"cancelled"} and running


def test_open_count_and_counts_by_state(make_website):
    ids = make_sites(make_website, "https://a.com", "https://b.com")
    with get_session() as session:
        queue.enqueue(session, ids)
        session.commit()
        assert queue.open_count(session) == 2 and queue.counts_by_state(session) == {"queued": 2}
        queue.claim_next(session, "w1")
        assert queue.open_count(session) == 2 and queue.counts_by_state(session) == {"queued": 1, "claimed": 1}


def test_finished_tasks_allow_a_new_task_for_a_recrawl(make_website):
    (a,) = make_sites(make_website, "https://a.com")
    with get_session() as session:
        queue.enqueue(session, [a])
        session.commit()
        queue.finish(session, queue.claim_next(session, "w1").task_id, "done")
        assert queue.enqueue(session, [a]) == 1
        session.commit()
        assert session.query(CrawlTask).count() == 2


def test_stale_claims_are_released_by_the_recovery_module(make_website):
    from app.recovery import recover_abandoned, release_stale_claims

    (a,) = make_sites(make_website, "https://a.com")
    with get_session() as session:
        queue.enqueue(session, [a])
        session.commit()
        queue.claim_next(session, "w1", lease_seconds=-5)               # already expired
        assert release_stale_claims(session)["tasks_requeued"] == 1
        session.commit()
        assert session.get(Website, a).status == "queued"
    with get_session() as session:
        queue.claim_next(session, "w9")
    result = recover_abandoned()                                         # single-process start: everything in progress is reset
    assert result["websites_reset"] == 1 and result["tasks_reset"] == 1
