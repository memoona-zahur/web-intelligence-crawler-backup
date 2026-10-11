"""Child process for the crash-recovery test: starts a crawl of local sites and is killed by the parent. Not a test by itself."""
import asyncio
import sys

from common import setup

name = sys.argv[1]
database, _ = setup(name + "_victim", install_telemetry=False) if False else (None, None)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import app.database as database
from app.models import Base

engine = create_engine(f"sqlite:///C:/crawl_eval_data/db/extra_{name}.db")
database.engine, database.SessionLocal = engine, sessionmaker(bind=engine)
from app.crawler import runner
from app.models import Website
from sqlalchemy import select

with database.get_session() as s:
    ids = [w.id for w in s.scalars(select(Website))]
asyncio.run(runner.run(site_ids=ids, concurrency=5, log=lambda m: None))
