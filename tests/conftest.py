"""Shared fixtures: isolated temp database and a Website factory.

Offline by construction (CR-J03): a socket guard (tests/netguard/sitecustomize.py) makes ANY non-local connection or DNS lookup fail, in this
process and in every Python child process a test starts, and the attempt is logged even if the code under test swallows the exception.
If the log is not empty at the end the run is marked failed. Command and details: docs/testing-offline.md.
"""

import importlib.util
import os
import tempfile
from pathlib import Path

import pytest

_GUARD_DIR = Path(__file__).parent / "netguard"
_GUARD_LOG = Path(os.environ.get("NETGUARD_LOG") or Path(tempfile.gettempdir()) / "crawler_netguard.log")
os.environ["NETGUARD_LOG"] = str(_GUARD_LOG)
os.environ["PYTHONPATH"] = os.pathsep.join(p for p in (str(_GUARD_DIR), os.environ.get("PYTHONPATH", "")) if p)  # child processes load the guard too
if os.environ.get("NETGUARD") != "off":
    _spec = importlib.util.spec_from_file_location("crawler_netguard", _GUARD_DIR / "sitecustomize.py")
    _spec.loader.exec_module(importlib.util.module_from_spec(_spec))   # installs the guard in this process (idempotent)


def _leaks() -> list[str]:
    return _GUARD_LOG.read_text(encoding="utf-8").splitlines() if _GUARD_LOG.exists() else []


def pytest_sessionstart(session):
    _GUARD_LOG.unlink(missing_ok=True)


def pytest_terminal_summary(terminalreporter):
    leaks = _leaks()
    state = "OFF (NETGUARD=off)" if os.environ.get("NETGUARD") == "off" else "on"
    terminalreporter.write_sep("-", f"socket guard {state}: {len(leaks)} non-local network attempt(s) blocked")
    for line in leaks[:20]:
        terminalreporter.write_line("  " + line)


def pytest_sessionfinish(session, exitstatus):
    if _leaks() and exitstatus == 0:  # a swallowed exception must not hide a leak
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import app.database as database  # noqa: E402
from app.models import Base, Website  # noqa: E402


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


@pytest.fixture(autouse=True)
def no_browser(monkeypatch):
    """The original suite had one test (test_candidate_with_no_text_skipped) that reached the REAL browser path: a DNS lookup of example.com and,
    with Chromium installed, possibly one page request. Now the pipeline's browser returns nothing unless a test patches it explicitly.
    tests/test_browser_real.py calls app.crawler.browser directly and uses local servers only."""

    async def nothing(url):
        return None

    monkeypatch.setattr("app.crawler.pipeline.render_page", nothing)


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
