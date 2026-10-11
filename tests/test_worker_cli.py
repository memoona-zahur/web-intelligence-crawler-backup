"""The worker command line and the remaining operator commands (CR-G03, G05, K05)."""

import asyncio

import pytest

from app import ops
from app.crawler import runner, worker
from app.crawler.runner import RunSummary
from app.settings import SettingsError


def test_worker_main_runs_and_prints_the_summary(monkeypatch, capsys):
    calls = {}

    async def fake_run_worker(concurrency, forever, poll, **kwargs):
        calls.update(concurrency=concurrency, forever=forever, poll=poll, **kwargs)
        return RunSummary(total=3, counts={"crawled": 2, "parked": 1}, seconds=1.5)

    monkeypatch.setattr(worker, "run_worker", fake_run_worker)
    assert worker.main(["--workers", "4", "--forever", "--poll", "0.5", "--no-enqueue", "--limit", "9"]) == 0
    out = capsys.readouterr().out
    assert calls == {"concurrency": 4, "forever": True, "poll": 0.5, "enqueue_pending": False, "limit": 9}
    assert "crawled" in out and "parked" in out and "1.5" in out


def test_worker_defaults(monkeypatch):
    seen = {}

    async def fake_run_worker(concurrency, forever, poll, **kwargs):
        seen.update(concurrency=concurrency, forever=forever, enqueue=kwargs["enqueue_pending"])
        return RunSummary()

    monkeypatch.setattr(worker, "run_worker", fake_run_worker)
    assert worker.main([]) == 0 and seen == {"concurrency": None, "forever": False, "enqueue": True}


def test_worker_refuses_to_start_without_a_contact_in_production(monkeypatch, capsys):
    monkeypatch.setenv("CRAWLER_MODE", "production")
    monkeypatch.delenv("CRAWLER_CONTACT_URL", raising=False)
    assert worker.main([]) == 2
    assert "CRAWLER_CONTACT_URL" in capsys.readouterr().out


def test_worker_stops_cleanly_on_ctrl_c(monkeypatch, capsys):
    async def interrupted(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(worker, "run_worker", interrupted)
    assert worker.main([]) == 130
    assert "released back to the queue" in capsys.readouterr().out


def test_the_cli_still_prints_a_summary(monkeypatch, capsys, make_website):
    from app import crawler_cli
    from app.crawler.pipeline import CrawlResult

    make_website("https://acme.com")

    async def fake(client, url, cache):
        return CrawlResult("crawled", "TEXT", None, 1)

    monkeypatch.setattr(runner, "crawl_one", fake)
    monkeypatch.setattr("sys.argv", ["crawler"])
    crawler_cli.main()
    out = capsys.readouterr().out
    assert "Crawled 1 website(s)" in out and "crawled" in out


def test_report_backup_recover_and_benchmark_commands(make_website, capsys, tmp_path, monkeypatch):
    make_website("https://acme.com", status="crawling")
    ops.main(["recover"])
    assert "Reset 1 crawling website(s)" in capsys.readouterr().out
    ops.main(["report"])
    assert "Websites saved: 1" in capsys.readouterr().out
    ops.main(["report", "--json"])
    assert '"websites": 1' in capsys.readouterr().out
    ops.main(["benchmark", "--rows", "20"])
    assert "Measured" in capsys.readouterr().out
    monkeypatch.setattr(ops, "backup_database", lambda: tmp_path / "backup.db")
    ops.main(["backup"])
    assert "Backup written" in capsys.readouterr().out


def test_commands_that_need_an_argument_say_so(capsys):
    for argv in (["cancel"], ["import"], ["import-from-db"], ["recrawl"], ["export-crawl"]):
        with pytest.raises(SystemExit):
            ops.main(argv)
    with pytest.raises(SystemExit):
        ops.main(["cancel", "--job", "999"])


def test_requeue_and_queue_status_with_nothing_to_do(capsys):
    ops.main(["queue-status"])
    assert "queue is empty" in capsys.readouterr().out
    ops.main(["requeue"])
    assert "Re-queued 0" in capsys.readouterr().out
    ops.main(["purge-raw"])
    assert "Removed 0" in capsys.readouterr().out
