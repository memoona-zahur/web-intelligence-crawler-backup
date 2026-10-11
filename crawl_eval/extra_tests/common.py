"""Shared setup for the extra evidence tests: isolated DB + the same pass-through telemetry as the main harness. Nothing under app/ is edited."""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "crawl_eval"))
os.environ["OBSERVE_ECHO"] = "0"
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "C:/crawl_eval_data/browsers")
RESULTS = ROOT / "crawl_eval" / "results" / "extra_tests"
RESULTS.mkdir(parents=True, exist_ok=True)
PORTS = set(range(8800, 8863)) | {8899}


def setup(name: str, install_telemetry: bool = True):
    """Returns (database module, telemetry or None). DB file: C:/crawl_eval_data/db/extra_<name>.db (recreated)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import app.database as database
    from app.models import Base

    db = Path(f"C:/crawl_eval_data/db/extra_{name}.db")
    for suffix in ("", "-journal", "-wal", "-shm"):
        Path(str(db) + suffix).unlink(missing_ok=True)
    engine = create_engine(f"sqlite:///{db}")
    database.engine, database.SessionLocal = engine, sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    os.environ["OBSERVE_LOG"] = str(RESULTS / f"{name}_app_events.jsonl")
    tel = None
    if install_telemetry:
        import telemetry
        tel = telemetry.Telemetry(PORTS)
        telemetry.install(tel)
        tel.start_memory(1.0)
    return database, tel


def save(name: str, data: dict):
    (RESULTS / f"{name}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(data, indent=1, ensure_ascii=False, default=str)[:3000])
