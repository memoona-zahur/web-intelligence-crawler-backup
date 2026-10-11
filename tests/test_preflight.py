"""Pre-flight and run wrapper for real-site runs: concurrency 5, real contact, budget, manifest check. No run is ever started here."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "crawl_eval" / "tools"))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "crawl_eval" / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_phase2 = load("run_phase2")
preflight = run_phase2.preflight        # the same module object the wrapper uses, so patches reach it


def test_only_concurrency_5_passes_without_an_explicit_override():
    assert preflight.check_concurrency(5, None) is None
    for wrong in (1, 3, 10, 20):
        assert "must use --concurrency 5" in preflight.check_concurrency(wrong, None)
    assert preflight.check_concurrency(10, 10) is None                     # explicit override for exactly that value
    assert preflight.check_concurrency(10, 20) is not None                 # an override for another value does not count


def test_run_budget_is_two_smoke_and_four_full():
    ledger = {"runs": [{"kind": "smoke", "status": "finished"}, {"kind": "smoke", "status": "started"}]}
    assert "budget of 2" in preflight.ledger_allows(ledger, "smoke")
    assert preflight.ledger_allows(ledger, "full") is None
    ledger["runs"] += [{"kind": "full", "status": "finished"}] * 4
    assert "budget of 4" in preflight.ledger_allows(ledger, "full")
    assert preflight.ledger_allows({"runs": [{"kind": "smoke", "status": "failed"}]}, "smoke") is None     # a failed start does not use up the budget


def test_manifest_check_catches_wrong_concurrency_and_changed_code():
    good = {"concurrency_used": 5, "app_code_unchanged_before": True, "app_code_unchanged_after": True, "code_sha256": "abc"}
    assert preflight.verify_manifest(good) == []
    assert any("concurrency_used=10" in p for p in preflight.verify_manifest({**good, "concurrency_used": 10}))
    assert any("code hash changed" in p for p in preflight.verify_manifest({**good, "app_code_unchanged_after": False}))
    assert any("code_sha256" in p for p in preflight.verify_manifest({**good, "code_sha256": None}))


@pytest.fixture()
def healthy(monkeypatch):
    monkeypatch.setattr(preflight, "judge_ok", lambda: True)
    monkeypatch.setattr(preflight, "contract_ok", lambda: True)
    monkeypatch.setattr(preflight, "git_state", lambda: (True, "abcdef1234567890", "crawler-v2"))
    monkeypatch.setenv("CRAWLER_MODE", "production")
    monkeypatch.setenv("CRAWLER_CONTACT_URL", "https://policy.real-company.org/crawler")


def test_preflight_passes_with_concurrency_5_a_real_contact_and_clean_code(healthy):
    failures, snapshot = preflight.run_checks(5)
    assert failures == [] and snapshot["commit"].startswith("abcdef") and dict(snapshot["settings"])["mode"] == "production"
    assert dict(snapshot["settings"])["User-Agent format"] == "WebsiteIntelligenceBot/2.0 (+<contact>)"


@pytest.mark.parametrize("contact", ["", "test@example.invalid", "https://example.com/c"])
def test_preflight_fails_without_a_real_contact(healthy, monkeypatch, contact):
    monkeypatch.setenv("CRAWLER_CONTACT_URL", contact)
    failures, _ = preflight.run_checks(5)
    assert any("CRAWLER_CONTACT_URL" in f for f in failures)


def test_preflight_fails_outside_production_and_with_dirty_code_or_broken_judge(healthy, monkeypatch):
    monkeypatch.setenv("CRAWLER_MODE", "dev")
    assert any("production" in f for f in preflight.run_checks(5)[0])
    monkeypatch.setenv("CRAWLER_MODE", "production")
    monkeypatch.setattr(preflight, "git_state", lambda: (False, "abc", "crawler-v2"))
    assert any("uncommitted" in f for f in preflight.run_checks(5)[0])
    monkeypatch.setattr(preflight, "judge_ok", lambda: False)
    monkeypatch.setattr(preflight, "contract_ok", lambda: False)
    failures = preflight.run_checks(5)[0]
    assert any("frozen judge" in f for f in failures) and any("contract" in f for f in failures)


def test_preflight_fails_for_another_concurrency_unless_overridden(healthy):
    assert any("--concurrency 5" in f for f in preflight.run_checks(10)[0])
    assert preflight.run_checks(10, 10)[0] == []


def test_wrapper_dry_run_prints_the_command_with_concurrency_5_and_starts_nothing(healthy, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(run_phase2, "LEDGER", tmp_path / "ledger.json")
    started = []
    monkeypatch.setattr(run_phase2.subprocess, "run", lambda *a, **k: started.append(a) or None)
    assert run_phase2.main(["--kind", "smoke", "--run-id", "t_smoke1", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "--concurrency 5" in out and "--smoke" in out and "--code-manifest auto" in out and "--run-id t_smoke1" in out
    assert started == [] and not (tmp_path / "ledger.json").exists()


def test_wrapper_refuses_other_concurrency_and_an_exhausted_budget(healthy, monkeypatch, tmp_path, capsys):
    ledger_file = tmp_path / "ledger.json"
    monkeypatch.setattr(run_phase2, "LEDGER", ledger_file)
    assert run_phase2.main(["--kind", "full", "--run-id", "x", "--concurrency", "10", "--dry-run"]) == 1
    assert "PRE-FLIGHT FAILED" in capsys.readouterr().out
    ledger_file.write_text(json.dumps({"runs": [{"kind": "smoke", "status": "finished"}, {"kind": "smoke", "status": "finished"}]}))
    assert run_phase2.main(["--kind", "smoke", "--run-id", "x", "--dry-run"]) == 1
    assert "budget of 2" in capsys.readouterr().out


def test_wrapper_refuses_without_a_real_contact(healthy, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(run_phase2, "LEDGER", tmp_path / "ledger.json")
    monkeypatch.delenv("CRAWLER_CONTACT_URL")
    assert run_phase2.main(["--kind", "smoke", "--run-id", "x"]) == 1
    assert "CRAWLER_CONTACT_URL is required" in capsys.readouterr().out and not (tmp_path / "ledger.json").exists()


def test_a_finished_run_is_checked_and_recorded(healthy, monkeypatch, tmp_path):
    monkeypatch.setattr(run_phase2, "LEDGER", tmp_path / "ledger.json")
    monkeypatch.setattr(run_phase2, "ROOT", tmp_path)

    class Done:
        returncode = 0

    def fake_run(cmd, **kw):
        out = tmp_path / "crawl_eval" / "results" / "t1"
        out.mkdir(parents=True, exist_ok=True)
        (out / "run_manifest.json").write_text(json.dumps({"concurrency_used": 5, "app_code_unchanged_before": True, "app_code_unchanged_after": True, "code_sha256": "x"}))
        return Done()

    monkeypatch.setattr(run_phase2.subprocess, "run", fake_run)
    assert run_phase2.main(["--kind", "smoke", "--run-id", "t1"]) == 0
    entry = json.loads((tmp_path / "ledger.json").read_text())["runs"][0]
    assert entry["status"] == "finished" and entry["concurrency"] == 5 and (tmp_path / "crawl_eval" / "results" / "t1" / "preflight.json").exists()


def test_crawler_cli_says_what_to_set_instead_of_a_traceback(monkeypatch, capsys):
    from app import crawler_cli

    monkeypatch.setenv("CRAWLER_MODE", "production")
    monkeypatch.delenv("CRAWLER_CONTACT_URL", raising=False)
    monkeypatch.setattr("sys.argv", ["crawler"])
    with pytest.raises(SystemExit) as exc:
        crawler_cli.main()
    out = capsys.readouterr().out
    assert exc.value.code == 2 and "Cannot start: CRAWLER_CONTACT_URL is required" in out and "Traceback" not in out


def test_robots_timeout_constant_is_gone():
    from app.crawler import config

    assert not hasattr(config, "ROBOTS_TIMEOUT")        # it was declared but never used; robots.txt uses the normal step timeout
