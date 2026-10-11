"""Alembic environment. Works with a connection handed in by app.database.run_migrations (tests, init_db) or from the command line."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

import app.settings as settings
from app.models import Base

config = context.config
target_metadata = Base.metadata


def _configure(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=False,
    )


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_engine(settings.database_url())
    with engine.connect() as conn:
        _configure(conn)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
