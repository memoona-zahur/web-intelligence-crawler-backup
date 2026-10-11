"""Open the database and bring its schema up to date with Alembic migrations.

Production uses PostgreSQL (DATABASE_URL, pending sir confirmation); without DATABASE_URL the local SQLite file data/websites.db is used,
which is also what unit tests and the evaluation harness use. Every schema change is a migration in migrations/versions (CR-H01, K04).
"""

import hashlib
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

import app.settings as settings
from app.models import Base

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "websites.db"


def make_engine(url: str | None = None):
    """Engine for DATABASE_URL (PostgreSQL) or the local SQLite file. SQLite gets WAL + a busy timeout so several processes can share it."""
    url = url or settings.database_url()
    if url.startswith("sqlite"):
        engine = create_engine(url, echo=False, connect_args={"timeout": 30})

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - exercised implicitly
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=30000")
            finally:
                cursor.close()

        return engine
    return create_engine(url, echo=False, pool_pre_ping=True, pool_size=10, max_overflow=10)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine)


# Columns of the very first schema that old databases may lack. create_all does not alter old tables.
EXTRA_COLUMNS = {
    "job_id": "INTEGER",
    "clean_text": "TEXT",
    "crawl_error": "TEXT",
    "pages_crawled": "INTEGER",
    "last_crawled_at": "DATETIME",
    "company_name": "VARCHAR(512)",
    "description": "TEXT",
    "business_type": "VARCHAR(64)",
    "industry": "VARCHAR(128)",
    "niche": "VARCHAR(128)",
    "products": "TEXT",
    "services": "TEXT",
    "confidence": "INTEGER",
    "evidence": "TEXT",
    "classification_meta": "TEXT",
    "claimed_at": "DATETIME",
    "crawl_status": "VARCHAR(32)",
    "classification_status": "VARCHAR(32)",
    "content_hash": "VARCHAR(64)",
    "secondary_industry": "VARCHAR(255)",
    "sub_niche": "VARCHAR(255)",
    "business_model": "VARCHAR(255)",
    "geographic_markets": "VARCHAR(512)",
}

JOB_EXTRA_COLUMNS = {
    "note": "TEXT",
}

INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_websites_status ON websites (status)",
    "CREATE INDEX IF NOT EXISTS ix_websites_industry ON websites (industry)",
    "CREATE INDEX IF NOT EXISTS ix_websites_business_type ON websites (business_type)",
    "CREATE INDEX IF NOT EXISTS ix_websites_confidence ON websites (confidence)",
    "CREATE INDEX IF NOT EXISTS ix_jobs_status ON jobs (status)",
    "CREATE INDEX IF NOT EXISTS ix_jobs_kind ON jobs (kind)",
    "CREATE INDEX IF NOT EXISTS ix_websites_crawl_status ON websites (crawl_status)",
    "CREATE INDEX IF NOT EXISTS ix_websites_classification_status ON websites (classification_status)",
    "CREATE INDEX IF NOT EXISTS ix_evidence_website ON evidence_records (website_id)",
)

_AI_STATUSES = ("classified", "needs_review", "insufficient_evidence", "classify_failed")


def _add_missing(connection, table: str, columns: dict[str, str]) -> None:
    existing = {column["name"] for column in inspect(connection).get_columns(table)}
    for name, column_type in columns.items():
        if name not in existing:
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}"))


def alembic_config(connection=None) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def run_migrations(target_engine=None) -> None:
    """Bring the schema to the newest revision. Old unversioned databases are upgraded in place and then stamped."""
    target = target_engine or engine
    with target.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if "websites" in tables and "alembic_version" not in tables:
            _add_missing(connection, "websites", EXTRA_COLUMNS)
            if "jobs" in tables:
                _add_missing(connection, "jobs", JOB_EXTRA_COLUMNS)
            for statement in INDEX_STATEMENTS:
                if "evidence_records" in statement and "evidence_records" not in tables:
                    continue
                connection.execute(text(statement))
            _backfill_statuses(connection)
        command.upgrade(alembic_config(connection), "head")


def init_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    run_migrations(engine)


def _backfill_statuses(connection) -> None:
    """Fill the split status columns on rows saved before they existed."""
    ai_list = ", ".join(f"'{status}'" for status in _AI_STATUSES)
    connection.execute(
        text(
            f"""
            UPDATE websites
            SET classification_status = status,
                crawl_status = CASE
                    WHEN clean_text IS NOT NULL AND clean_text != '' THEN 'crawled'
                    ELSE ''
                END
            WHERE crawl_status IS NULL AND status IN ({ai_list})
            """
        )
    )
    connection.execute(
        text(
            """
            UPDATE websites
            SET crawl_status = status
            WHERE crawl_status IS NULL
            """
        )
    )
    rows = connection.execute(
        text(
            """
            SELECT id, clean_text FROM websites
            WHERE content_hash IS NULL AND clean_text IS NOT NULL AND clean_text != ''
            """
        )
    ).all()
    for site_id, clean_text in rows:
        digest = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
        connection.execute(
            text("UPDATE websites SET content_hash = :digest WHERE id = :site_id"),
            {"digest": digest, "site_id": site_id},
        )


def get_session() -> Session:
    return SessionLocal()
