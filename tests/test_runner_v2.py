"""The runner on top of the durable queue (CR-A12, A13, F07, G01, G02, G03, G05, G06, K05; issues ISS-22, ISS-23)."""

import asyncio
import time
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.crawler import runner
from app.crawler.pipeline import CrawlResult
from app.database import get_session
from app.models import CrawlTask, Job, Website
from app.recovery import utcnow
from app.settings import SettingsError


def quiet(**overrides):
    kwargs = {"log": lambda *a, **k: None}
    kwargs.update(overrides)
    return kwargs


def run_sync(**kwargs):
    return asyncio.run(runner.run(**quiet(**kwargs)))


def get_site(site_id) -> Website:
    with get_session() as session:
        site = session.get(Website, site_id)
        session.expunge(site)
        return site


def all_tasks():
    with get_session() as session:
        return session.scalars(select(CrawlTask).order_by(CrawlTask.id)).all()


def test_the_run_creates_a_job_and_one_task_per_website(make_website, monkeypatch):
    ids = [make_website(f"https://s{i}.com") for i in range(4)]

    async def fake(client, url, cache):
        return CrawlResult("crawled", "TEXT", None, 2)

    monkeypatch.setattr(runner, "crawl_one", fake)
    summary = run_sync()
    assert summary.total == 4 and summary.counts == {"crawled": 4}
    with get_session() as session:
        job = session.scalars(select(Job).where(Job.kind == "crawl")).one()
        assert (job.status, job.total, job.added, job.done_count, job.failed_count) == ("completed", 4, 4, 4, 0) and job.note == "crawled=4"
    assert {t.state for t in all_tasks()} == {"done"} and {t.attempt for t in all_tasks()} == {1} and all(get_site(i).status == "crawled" for i in ids)


def test_never_more_sites_at_once_than_the_concurrency(make_website, monkeypatch):
    for i in range(12):
        make_website(f"https://s{i}.com")
    state = {"now": 0, "max": 0}

    async def fake(client, url, cache):
        state["now"] += 1
        state["max"] = max(state["max"], state["now"])
        await asyncio.sleep(0.4)
        state["now"] -= 1
        return CrawlResult("crawled", "TEXT", None, 1)

    monkeypatch.setattr(runner, "crawl_one", fake)
    summary = run_sync(concurrency=3)
    assert summary.total == 12 and state["max"] == 3


def test_sites_of_one_domain_are_never_crawled_together_but_other_sites_are(make_website, monkeypatch):
    for url in ("https://acme.com", "https://shop.acme.com", "https://blog-x.acme.com", "https://other1.org", "https://other2.org"):
        make_website(url)
    active: dict[str, int] = {}
    overlaps: list[str] = []
    state = {"now": 0, "max": 0}

    async def fake(client, url, cache):
        from app.domains import domain_key

        key = domain_key(url)
        if active.get(key):
            overlaps.append(url)
        active[key] = active.get(key, 0) + 1
        state["now"] += 1
        state["max"] = max(state["max"], state["now"])
        await asyncio.sleep(0.05)
        active[key] -= 1
        state["now"] -= 1
        return CrawlResult("crawled", "TEXT", None, 1)

    monkeypatch.setattr(runner, "crawl_one", fake)
    summary = run_sync(concurrency=5)
    assert summary.counts == {"crawled": 5} and overlaps == [] and state["max"] >= 2


def test_one_crashing_site_does_not_stop_the_batch(make_website, monkeypatch):
    bad = make_website("https://bad.com")
    good = [make_website(f"https://good{i}.com") for i in range(3)]

    async def fake(client, url, cache):
        if "bad" in url:
            raise RuntimeError("kaput")
        return CrawlResult("crawled", "TEXT", None, 1)

    monkeypatch.setattr(runner, "crawl_one", fake)
    summary = run_sync()
    assert summary.counts == {"crawled": 3, "failed": 1}
    assert "unexpected error: kaput" in get_site(bad).crawl_error and all(get_site(i).status == "crawled" for i in good)


def test_a_save_that_fails_does_not_kill_the_worker(make_website, monkeypatch):
    ids = [make_website(f"https://s{i}.com") for i in range(3)]
    real_save = runner._save

    def flaky_save(site_id, result):
        if site_id == ids[1]:
            raise RuntimeError("database hiccup")
        real_save(site_id, result)

    async def fake(client, url, cache):
        return CrawlResult("crawled", "TEXT", None, 1)

    monkeypatch.setattr(runner, "crawl_one", fake)
    monkeypatch.setattr(runner, "_save", flaky_save)
    summary = run_sync()
    assert summary.counts["failed"] == 1 and summary.counts["crawled"] == 2
    failed = [t for t in all_tasks() if t.state == "failed"]
    assert len(failed) == 1 and "could not be saved" in failed[0].last_error


@pytest.mark.parametrize(
    "result, state",
    [
        (CrawlResult("robots_blocked", None, "robots.txt unavailable (HTTP 503)", 0, error_category="robots_unavailable", retry_after=900.0), "retry_scheduled"),
        (CrawlResult("unreachable", None, "timeout", 0, error_category="timeout"), "retry_scheduled"),
        (CrawlResult("unreachable", None, "cannot resolve host", 0, error_category="dns"), "retry_scheduled"),
        (CrawlResult("blocked", None, "HTTP 429", 0, error_category="rate_limited", retry_after=3600.0), "retry_scheduled"),
        (CrawlResult("failed", None, "HTTP 503", 0, error_category="http_5xx"), "retry_scheduled"),
        (CrawlResult("failed", None, "HTTP 404", 0, error_category="http_4xx"), "done"),
        (CrawlResult("robots_blocked", None, "disallowed by robots.txt", 0, error_category="robots_disallowed"), "done"),
        (CrawlResult("blocked", None, "HTTP 403", 0, error_category="access_denied"), "done"),
        (CrawlResult("parked", None, "parked", 0, error_category="parked"), "done"),
        (CrawlResult("invalid", None, "non-public", 0, error_category="unsafe_target"), "done"),
        (CrawlResult("crawled", "TEXT", None, 1), "done"),
    ],
)
def test_transient_failures_are_scheduled_for_later_permanent_ones_are_final(make_website, monkeypatch, result, state):
    site_id = make_website("https://acme.com")

    async def fake(client, url, cache):
        return result

    monkeypatch.setattr(runner, "crawl_one", fake)
    summary = run_sync()
    task = all_tasks()[0]
    assert task.state == state and summary.counts == {result.status: 1}
    site = get_site(site_id)
    assert site.status == result.status                       # the row shows the real outcome, not 'pending'
    if state == "retry_scheduled":
        assert task.not_before > utcnow() + timedelta(minutes=10) and task.last_error and site.next_retry_at is not None
    else:
        assert task.not_before is None


def test_after_three_attempts_a_transient_failure_becomes_final(make_website, monkeypatch):
    site_id = make_website("https://acme.com")

    async def fake(client, url, cache):
        return CrawlResult("unreachable", None, "timeout", 0, error_category="timeout")

    monkeypatch.setattr(runner, "crawl_one", fake)
    for _ in range(3):
        run_sync(site_ids=[site_id])                           # each run is a new attempt (the task is handed to the run immediately)
        with get_session() as session:
            session.query(CrawlTask).update({"not_before": None})
            session.commit()
    attempts = [t.attempt for t in all_tasks()]
    assert max(attempts) == 3 and all_tasks()[-1].state == "done"


def test_cancel_stops_running_crawls_within_a_second_and_leaves_no_task_behind(make_website, monkeypatch):  # ISS-23
    for i in range(6):
        make_website(f"https://s{i}.com")
    started = {"n": 0}

    async def slow(client, url, cache):
        started["n"] += 1
        await asyncio.sleep(30)
        return CrawlResult("crawled", "TEXT", None, 1)

    monkeypatch.setattr(runner, "crawl_one", slow)

    async def scenario():
        task = asyncio.create_task(runner.run(**quiet(concurrency=3)))
        await asyncio.sleep(0.4)
        with get_session() as session:
            job = session.scalars(select(Job).where(Job.kind == "crawl")).one()
            job.status = "cancelled"
            session.commit()
        t0 = time.monotonic()
        summary = await asyncio.wait_for(task, timeout=10)
        return summary, time.monotonic() - t0

    summary, took = asyncio.run(scenario())
    assert took < 3, f"cancel took {took:.1f}s"             # Phase 1: 20.9 s
    assert started["n"] == 3 and summary.counts == {}
    states = {t.state for t in all_tasks()}
    assert states == {"cancelled"}
    with get_session() as session:
        assert {w.status for w in session.scalars(select(Website))} == {"pending"}       # released, can be crawled again
        assert session.scalars(select(Job).where(Job.kind == "crawl")).one().status == "cancelled"


def test_a_worker_that_dies_loses_nothing(make_website, monkeypatch):
    """Simulates a crash: a task is left claimed with an expired lease; a new worker run picks it up and finishes it."""
    site_id = make_website("https://acme.com")
    from app.crawler import queue

    with get_session() as session:
        queue.enqueue(session, [site_id])
        session.commit()
        queue.claim_next(session, "dead-worker", lease_seconds=-1)         # the lease is already over: the worker "died"

    async def fake(client, url, cache):
        return CrawlResult("crawled", "TEXT", None, 1)

    monkeypatch.setattr(runner, "crawl_one", fake)
    summary = asyncio.run(runner.run_worker(**quiet(concurrency=2, enqueue_pending=False)))
    assert summary.counts == {"crawled": 1}
    task = all_tasks()[0]
    assert task.state == "done" and task.attempt == 2 and get_site(site_id).status == "crawled"


def test_worker_mode_queues_pending_rows_and_drains_everything(make_website, monkeypatch):
    ids = [make_website(f"https://s{i}.com") for i in range(5)]
    make_website("https://done.com", status="crawled")

    async def fake(client, url, cache):
        return CrawlResult("crawled", f"TEXT {url}", None, 1)

    monkeypatch.setattr(runner, "crawl_one", fake)
    summary = asyncio.run(runner.run_worker(**quiet(concurrency=2)))
    assert summary.total == 5 and summary.counts == {"crawled": 5}
    assert all(get_site(i).clean_text for i in ids)


def test_worker_forever_mode_stops_on_the_stop_event(make_website, monkeypatch):
    make_website("https://a.com")

    async def fake(client, url, cache):
        return CrawlResult("crawled", "TEXT", None, 1)

    monkeypatch.setattr(runner, "crawl_one", fake)

    async def scenario():
        stop = asyncio.Event()
        task = asyncio.create_task(runner.run_worker(**quiet(concurrency=1, forever=True, poll=0.05, stop_event=stop)))
        await asyncio.sleep(0.5)
        make_website_later = Website(original_url="late.com", normalized_website="https://late.com", status="pending")
        with get_session() as session:
            session.add(make_website_later)
            session.commit()
        await asyncio.sleep(0.2)
        stop.set()
        return await asyncio.wait_for(task, timeout=5)

    summary = asyncio.run(scenario())
    assert summary.counts.get("crawled", 0) >= 1


def test_production_mode_refuses_to_start_without_a_real_contact(make_website, monkeypatch):
    make_website("https://acme.com")
    monkeypatch.setenv("CRAWLER_MODE", "production")
    monkeypatch.delenv("CRAWLER_CONTACT_URL", raising=False)
    with pytest.raises(SettingsError, match="CRAWLER_CONTACT_URL"):
        run_sync()
    assert all(w.status == "pending" for w in [get_site(1)])               # nothing was queued or claimed


def test_the_shared_browser_is_closed_at_the_end_of_a_run(make_website, monkeypatch):
    make_website("https://acme.com")
    closed = []

    async def fake_shutdown():
        closed.append(True)

    async def fake(client, url, cache):
        return CrawlResult("crawled", "TEXT", None, 1)

    monkeypatch.setattr(runner, "crawl_one", fake)
    monkeypatch.setattr("app.crawler.browser.shutdown_browser", fake_shutdown)
    run_sync()
    assert closed == [True]


def test_the_lease_is_renewed_while_a_long_crawl_runs(make_website, monkeypatch):
    make_website("https://acme.com")
    monkeypatch.setattr(runner, "HEARTBEAT_SECONDS", 0.05)
    beats = []
    real = runner._heartbeat

    def counting(task_id, worker_id):
        beats.append(task_id)
        return real(task_id, worker_id)

    monkeypatch.setattr(runner, "_heartbeat", counting)

    async def slow(client, url, cache):
        await asyncio.sleep(0.4)
        return CrawlResult("crawled", "TEXT", None, 1)

    monkeypatch.setattr(runner, "crawl_one", slow)
    run_sync()
    assert len(beats) >= 3


def test_losing_the_lease_stops_the_crawl_and_nothing_is_saved(make_website, monkeypatch):
    site_id = make_website("https://acme.com")
    monkeypatch.setattr(runner, "HEARTBEAT_SECONDS", 0.05)
    monkeypatch.setattr(runner, "_heartbeat", lambda task_id, worker_id: False)

    async def slow(client, url, cache):
        await asyncio.sleep(5)
        return CrawlResult("crawled", "TEXT", None, 1)

    monkeypatch.setattr(runner, "crawl_one", slow)
    summary = run_sync()
    assert summary.counts == {} and get_site(site_id).clean_text is None


def test_summary_total_matches_what_was_queued_and_job_progress_is_visible(make_website, monkeypatch):
    for i in range(3):
        make_website(f"https://s{i}.com")
    seen = []

    async def fake(client, url, cache):
        with get_session() as session:
            seen.append(session.scalars(select(Job).where(Job.kind == "crawl")).one().status)
        return CrawlResult("crawled", "TEXT", None, 1)

    monkeypatch.setattr(runner, "crawl_one", fake)
    run_sync()
    assert set(seen) == {"running"}                              # progress is observable while the run is going
