"""Alembic migrations: models == migrations, old databases upgrade without losing rows (CR-H01, K04)."""

import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app.database import alembic_config, run_migrations
from app.models import Base


def _fresh(tmp_path, name="m.db"):
    return create_engine(f"sqlite:///{tmp_path / name}")


def test_fresh_database_gets_the_full_schema(tmp_path):
    engine = _fresh(tmp_path)
    run_migrations(engine)
    tables = set(inspect(engine).get_table_names())
    assert {"websites", "jobs", "crawl_tasks", "pages", "page_contents", "fetch_attempts", "crawl_errors", "import_issues",
            "domain_stats", "evidence_records", "alembic_version"} <= tables
    with engine.connect() as conn:
        assert conn.execute(text("select version_num from alembic_version")).scalar() == "0002_phase2_crawl_schema"


def test_migrations_match_the_models(tmp_path):
    engine = _fresh(tmp_path)
    run_migrations(engine)
    with engine.connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diffs == [], diffs


def test_create_all_database_is_accepted_and_stamped(tmp_path):
    engine = _fresh(tmp_path)
    Base.metadata.create_all(engine)
    run_migrations(engine)
    run_migrations(engine)  # idempotent
    with engine.connect() as conn:
        assert conn.execute(text("select version_num from alembic_version")).scalar() == "0002_phase2_crawl_schema"


def test_phase1_database_upgrades_and_keeps_its_rows(tmp_path):
    engine = _fresh(tmp_path)
    with engine.begin() as conn:
        command.upgrade(alembic_config(conn), "0001_baseline")
        conn.execute(text("delete from alembic_version"))  # an old database has no version table at all
        conn.execute(text("drop table alembic_version"))
        conn.execute(text("insert into websites (original_url, normalized_website, status, created_at) values ('Acme.com', 'https://acme.com', 'crawled', '2026-01-01')"))
        conn.execute(text("update websites set clean_text='ACME text', pages_crawled=3"))
    run_migrations(engine)
    with engine.connect() as conn:
        row = conn.execute(text("select normalized_website, clean_text, pages_crawled, retry_count, content_is_stale from websites")).one()
        cols = {c["name"] for c in inspect(conn).get_columns("websites")}
    assert row == ("https://acme.com", "ACME text", 3, 0, 0)
    assert {"final_url", "http_status", "website_status", "crawl_outcome", "pages_attempted", "source_record_id"} <= cols


def test_one_active_task_per_website_and_one_running_per_domain(tmp_path):
    engine = _fresh(tmp_path)
    run_migrations(engine)
    now = "2026-01-01"
    with engine.begin() as conn:
        for i in (1, 2):
            conn.execute(text(f"insert into websites (id, original_url, normalized_website, status, created_at) values ({i}, 'u{i}', 'https://u{i}.com', 'pending', '{now}')"))
        conn.execute(text(f"insert into crawl_tasks (website_id, domain_key, state, attempt, max_attempts, priority, created_at) values (1, 'u.com', 'queued', 0, 3, 0, '{now}')"))
    import pytest

    with pytest.raises(sa.exc.IntegrityError):  # second active task for website 1
        with engine.begin() as conn:
            conn.execute(text(f"insert into crawl_tasks (website_id, domain_key, state, attempt, max_attempts, priority, created_at) values (1, 'u.com', 'queued', 0, 3, 0, '{now}')"))
    with engine.begin() as conn:
        conn.execute(text("update crawl_tasks set state='crawling' where website_id=1"))
        conn.execute(text(f"insert into crawl_tasks (website_id, domain_key, state, attempt, max_attempts, priority, created_at) values (2, 'u.com', 'queued', 0, 3, 0, '{now}')"))
    with pytest.raises(sa.exc.IntegrityError):  # two running tasks for the same domain
        with engine.begin() as conn:
            conn.execute(text("update crawl_tasks set state='crawling' where website_id=2"))
