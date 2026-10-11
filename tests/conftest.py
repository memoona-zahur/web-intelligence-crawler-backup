"""Shared fixtures: isolated temp database and a Website factory."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.database as database
from app.models import Base, Website


@pytest.fixture(scope="session")
def _schema_template(tmp_path_factory):
    """The empty schema is built once; every test copies it (building 11 tables per test cost 0.8 s)."""
    path = tmp_path_factory.mktemp("schema") / "template.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    engine.dispose()
    return path


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch, _schema_template):
    """Every test gets its own empty SQLite file — the real data/ DB is never touched."""
    import shutil

    target = tmp_path / "test.db"
    shutil.copy(_schema_template, target)
    engine = create_engine(f"sqlite:///{target}")
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setenv("OBSERVE_ECHO", "0")
    monkeypatch.setenv("OBSERVE_LOG", str(tmp_path / "events.jsonl"))
    # Phase 2: unit tests run in TEST mode (test contact, local/mocked hosts only) and without real waiting.
    monkeypatch.setenv("CRAWLER_MODE", "test")
    monkeypatch.delenv("CRAWLER_CONTACT_URL", raising=False)
    monkeypatch.delenv("ROBOTS_5XX_POLICY", raising=False)
    monkeypatch.setattr("app.crawler.config.DOMAIN_DELAY", 0.0)
    monkeypatch.setattr("app.crawler.config.RETRY_BACKOFF", 0.0)
    monkeypatch.setattr("app.crawler.config.DOMAIN_DELAY_MAX", 0.0)    # no real waiting after a 429/5xx in unit tests
    yield engine


@pytest.fixture(autouse=True)
def no_dns(monkeypatch):
    """CR-J03: unit tests never touch the network, not even DNS. The guard has its own tests (test_guard*.py) that call it directly."""
    monkeypatch.setattr("app.crawler.fetcher.assert_public_url", lambda url: url)


@pytest.fixture()
def make_website(db):
    def _make(url: str, status: str = "pending", **extra) -> int:
        with database.get_session() as session:
            site = Website(
                original_url=url,
                normalized_website=url,
                status=status,
                **extra,
            )
            session.add(site)
            session.commit()
            return site.id

    return _make


@pytest.fixture()
def allow_hosts(monkeypatch):
    """Disable DNS/SSRF checks so mocked-HTTP tests stay offline and deterministic.

    The guard itself has its own dedicated tests in test_guard.py.
    """
    monkeypatch.setattr("app.crawler.fetcher.assert_public_url", lambda url: url)
