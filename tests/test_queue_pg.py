"""The same guarantees on PostgreSQL: migrations, partial unique indexes, SKIP LOCKED claiming across threads and PROCESSES, recovery (CR-A13, G01-G03, H01).

Runs only when TEST_DATABASE_URL points at an EMPTY PostgreSQL database made for tests, for example
    TEST_DATABASE_URL=postgresql+psycopg://postgres:<password>@localhost:5432/crawl_test
Everything in that database is deleted by these tests. Without the variable the tests are skipped (shown as 'skipped', never as passed).
"""

import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

import app.database as database
from app.crawler import queue
from app.models import Base, CrawlTask, DomainStat, Website
from app.recovery import utcnow

URL = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL.startswith("postgresql"), reason="TEST_DATABASE_URL (PostgreSQL) is not set")
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def pg_engine():
    engine = database.make_engine(URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    database.run_migrations(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def pg(pg_engine, monkeypatch):
    with pg_engine.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    monkeypatch.setattr(database, "engine", pg_engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=pg_engine))
    return pg_engine


def add_sites(engine, urls):
    from app.domains import domain_key

    with sessionmaker(bind=engine)() as session:
        ids = []
        for u in urls:
            site = Website(original_url=u, normalized_website=u, status="pending", domain_key=domain_key(u))
            session.add(site)
            session.flush()
            ids.append(site.id)
        session.commit()
    return ids


def test_postgresql_schema_matches_the_models_and_is_at_head(pg_engine):
    with pg_engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
        assert conn.execute(text("select version_num from alembic_version")).scalar() == "0003_duplicate_of"
        indexes = {row[0] for row in conn.execute(text("select indexname from pg_indexes where tablename = 'crawl_tasks'"))}
    assert {"uq_crawl_tasks_active_website", "uq_crawl_tasks_running_domain"} <= indexes


def test_migrations_are_idempotent_on_postgresql(pg_engine):
    database.run_migrations(pg_engine)
    database.run_migrations(pg_engine)


def test_partial_unique_indexes_hold_on_postgresql(pg):
    a, b = add_sites(pg, ["https://acme.com", "https://shop.acme.com"])
    with sessionmaker(bind=pg)() as session:
        queue.enqueue(session, [a, b])
        session.commit()
        first = queue.claim_next(session, "w1")
        second = queue.claim_next(session, "w2")
        assert first and second is None                       # shop.acme.com shares the domain: not claimable while acme.com runs
        with pytest.raises(sa.exc.IntegrityError):
            session.execute(sa.text(f"insert into crawl_tasks (website_id, domain_key, state, attempt, max_attempts, priority, created_at) values ({a}, 'acme.com', 'queued', 0, 3, 0, now())"))
            session.commit()


def test_many_threads_claim_without_double_claims_or_domain_overlap(pg):
    ids = add_sites(pg, [f"https://site{i}.com" for i in range(60)] + [f"https://s{i}.shared.com" for i in range(15)])
    Session = sessionmaker(bind=pg)
    with Session() as session:
        queue.enqueue(session, ids)
        session.commit()
    claimed = []
    lock = threading.Lock()

    def worker(name):
        while True:
            with Session() as session:
                item = queue.claim_next(session, name)
            if item is None:
                return
            with lock:
                claimed.append(item)

    threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len({c.task_id for c in claimed}) == len(claimed) == 61            # 60 separate domains + ONE of the 15 siblings of shared.com


def test_two_worker_processes_share_the_queue_without_overlap(pg):
    """Real processes, real PostgreSQL: each process claims tasks in a loop until nothing is runnable."""
    ids = add_sites(pg, [f"https://proc{i}.com" for i in range(80)])
    with sessionmaker(bind=pg)() as session:
        queue.enqueue(session, ids)
        session.commit()
    script = (
        "import sys, os; sys.path.insert(0, os.getcwd());"
        "from app.database import make_engine; from sqlalchemy.orm import sessionmaker; from app.crawler import queue;"
        f"S = sessionmaker(bind=make_engine({URL!r})); n = 0\n"
        "while True:\n"
        "    with S() as s:\n"
        "        item = queue.claim_next(s, sys.argv[1])\n"
        "        if item is None: break\n"
        "        queue.finish(s, item.task_id, 'done'); n += 1\n"
        "print(n)"
    )
    env = dict(os.environ, CRAWLER_MODE="test")
    procs = [subprocess.Popen([sys.executable, "-B", "-c", script, f"proc{i}"], cwd=ROOT, env=env, stdout=subprocess.PIPE, text=True) for i in range(3)]
    counts = [int(p.communicate()[0].strip()) for p in procs]
    assert sum(counts) == 80 and sum(1 for c in counts if c > 0) >= 2
    with sessionmaker(bind=pg)() as session:
        assert session.query(CrawlTask).filter_by(state="done", attempt=1).count() == 80


def test_lease_recovery_and_retry_on_postgresql(pg):
    from datetime import timedelta

    (a,) = add_sites(pg, ["https://a.com"])
    with sessionmaker(bind=pg)() as session:
        queue.enqueue(session, [a])
        session.commit()
        claimed = queue.claim_next(session, "dead", lease_seconds=1)
        assert queue.recover_expired(session, now=utcnow() + timedelta(seconds=30)) == 1
        again = queue.claim_next(session, "alive")
        assert again.task_id == claimed.task_id and again.attempt == 2
        queue.finish(session, again.task_id, "retry_scheduled", "later", utcnow() + timedelta(minutes=15))
        assert queue.claim_next(session, "alive") is None


def test_domain_backoff_is_read_on_postgresql(pg):
    from datetime import timedelta

    a, b = add_sites(pg, ["https://angry.com", "https://calm.org"])
    with sessionmaker(bind=pg)() as session:
        session.add(DomainStat(domain="angry.com", success_count=0, failure_count=3, consecutive_failures=3, backoff_until=utcnow() + timedelta(hours=1), last_status="blocked"))
        queue.enqueue(session, [a, b])
        session.commit()
        assert queue.claim_next(session, "w1").website_id == b
        assert session.scalars(select(CrawlTask).where(CrawlTask.website_id == a)).one().state == "retry_scheduled"


def test_runner_end_to_end_on_postgresql(pg, monkeypatch):
    import asyncio

    from app.crawler import runner
    from app.crawler.pipeline import CrawlResult

    add_sites(pg, [f"https://rn{i}.com" for i in range(25)])

    async def fake(client, url, cache):
        await asyncio.sleep(0.01)
        return CrawlResult("crawled", "TEXT " + url, None, 2, url, 12)

    monkeypatch.setattr(runner, "crawl_one", fake)
    summary = asyncio.run(runner.run(log=lambda *_a: None, concurrency=8))
    assert summary.counts == {"crawled": 25}
    with sessionmaker(bind=pg)() as session:
        assert session.query(Website).filter_by(status="crawled").count() == 25 and session.query(CrawlTask).filter_by(state="done").count() == 25


def test_import_of_sixty_thousand_urls_on_postgresql(pg):
    import time

    from app.importer import import_urls

    text_data = "\n".join(f"company{i}.com" for i in range(60_000))
    started = time.monotonic()
    with sessionmaker(bind=pg)() as session:
        result = import_urls(session, text_data)
    assert result.added == 60_000 and time.monotonic() - started < 120
