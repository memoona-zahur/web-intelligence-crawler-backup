"""Pre-flight for a real-site run of the Phase 2 crawler (Smoke-1, Full-1 ...). Reads and checks only; it never makes a request.

    python -B crawl_eval/tools/preflight.py --concurrency 5

It FAILS (exit 1) unless all of this holds:
  - the frozen judge is intact (freeze_judge.py verify)
  - production mode and a real CRAWLER_CONTACT_URL (the test contact and placeholders are refused)
  - concurrency is exactly 5 (the value fixed for Phase 1 and Phase 2 so the runs compare line by line); another value needs the explicit
    override  --allow-concurrency-override <that same value>
  - the code under test is committed (no uncommitted change in app/, tests/, templates/, scripts/)
  - the harness contract check passes
Then it prints the effective settings. run_phase2.py calls this before it starts the harness and stores the snapshot next to the results.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

REQUIRED_CONCURRENCY = 5
RUN_BUDGET = {"smoke": 2, "full": 4}     # real-site runs allowed in total (user decision at GATE 4)


def check_concurrency(concurrency: int, override: int | None) -> str | None:
    """None when fine, else the reason."""
    if concurrency == REQUIRED_CONCURRENCY:
        return None
    if override is not None and override == concurrency:
        return None
    return (f"concurrency {concurrency} is not the Phase 2 value {REQUIRED_CONCURRENCY}; Smoke and Full runs must use --concurrency {REQUIRED_CONCURRENCY}. "
            f"A different value needs the explicit --allow-concurrency-override {concurrency}")


def ledger_allows(ledger: dict, kind: str) -> str | None:
    used = sum(1 for r in ledger.get("runs", []) if r.get("kind") == kind and r.get("status") in ("started", "finished"))
    limit = RUN_BUDGET[kind]
    return None if used < limit else f"the budget of {limit} real-site {kind} run(s) is used up ({used} recorded in crawl_eval/real_runs_ledger.json)"


def verify_manifest(manifest: dict, expected_concurrency: int = REQUIRED_CONCURRENCY) -> list[str]:
    """Problems found in a finished run's run_manifest.json (empty list = fine)."""
    problems = []
    if manifest.get("concurrency_used") != expected_concurrency:
        problems.append(f"run_manifest.json says concurrency_used={manifest.get('concurrency_used')}, expected {expected_concurrency}")
    if not (manifest.get("app_code_unchanged_before") and manifest.get("app_code_unchanged_after")):
        problems.append("the code hash changed during the run (app_code_unchanged is not true before and after)")
    if not manifest.get("code_sha256"):
        problems.append("run_manifest.json has no code_sha256 (was --code-manifest auto used?)")
    return problems


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=300)


def judge_ok() -> bool:
    done = _run([sys.executable, "-B", "crawl_eval/tools/freeze_judge.py", "verify"])
    return done.returncode == 0 and "FROZEN JUDGE OK" in done.stdout


def contract_ok() -> bool:
    return _run([sys.executable, "-B", "crawl_eval/tools/check_harness_contract.py"]).returncode == 0


def git_state() -> tuple[bool, str, str]:
    """(clean, commit, branch) for the code under test."""
    dirty = _run(["git", "status", "--porcelain", "--", "app", "tests", "templates", "scripts"]).stdout.strip()
    commit = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
    branch = _run(["git", "branch", "--show-current"]).stdout.strip()
    return (not dirty, commit, branch)


def effective_settings() -> list[tuple[str, str]]:
    import app.settings as s
    from app import limits
    from app.crawler import config as c

    contact = s.configured_contact()
    ua = s.user_agent().replace(contact, "<contact>") if contact else "(no contact set)"
    return [
        ("mode", s.mode()), ("User-Agent format", ua), ("robots policy (5xx/429/unreadable)", s.robots_5xx_policy() + " (pending sir confirmation)"),
        ("per-domain gap", f"{c.DOMAIN_DELAY} s (Crawl-delay up to {c.CRAWL_DELAY_MAX} s), 1 request at a time"),
        ("attempts / back-off", f"{c.RETRIES + 1} attempts, {c.RETRY_BACKOFF} s x 2^n, jitter {int(c.RETRY_JITTER * 100)} %, Retry-After up to {c.RETRY_AFTER_MAX} s"),
        ("timeouts", f"step {c.PAGE_TIMEOUT} s, request {c.TOTAL_TIMEOUT} s, site {c.SITE_DEADLINE} s"),
        ("size caps", f"page {c.MAX_BYTES_PER_PAGE:,} B, sitemap {c.SITEMAP_MAX_BYTES:,} B, ratio {c.MAX_DECODED_RATIO}:1, text {c.MAX_TEXT_CHARS:,} chars"),
        ("pages per site", f"{c.MAX_PAGES} (max {c.PER_TYPE_PAGES} per type)"), ("redirects", f"max {c.MAX_REDIRECTS}"),
        ("code default concurrency (NOT used by the harness)", str(limits.crawl_concurrency())),
    ]


def run_checks(concurrency: int, override: int | None = None) -> tuple[list[str], dict]:
    failures: list[str] = []
    snapshot: dict = {"required_concurrency": REQUIRED_CONCURRENCY, "requested_concurrency": concurrency, "override": override}
    reason = check_concurrency(concurrency, override)
    if reason:
        failures.append(reason)
    if not judge_ok():
        failures.append("frozen judge check failed (freeze_judge.py verify did not say FROZEN JUDGE OK)")
    import app.settings as s

    try:
        if s.mode() != "production":
            failures.append(f"CRAWLER_MODE is {s.mode()!r}; a real-site run needs production mode")
        s.effective_contact()
    except s.SettingsError as exc:
        failures.append(str(exc))
    clean, commit, branch = git_state()
    snapshot.update(commit=commit, branch=branch)
    if not clean:
        failures.append("uncommitted changes in app/, tests/, templates/ or scripts/: commit the code under test first")
    if not contract_ok():
        failures.append("harness contract check failed (crawl_eval/tools/check_harness_contract.py)")
    snapshot["settings"] = effective_settings() if not any("CRAWLER_MODE" in f or "CRAWLER_CONTACT_URL" in f for f in failures) else []
    return failures, snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pre-flight for a real-site run.")
    parser.add_argument("--concurrency", type=int, default=REQUIRED_CONCURRENCY)
    parser.add_argument("--allow-concurrency-override", type=int, default=None)
    args = parser.parse_args(argv)
    failures, snapshot = run_checks(args.concurrency, args.allow_concurrency_override)
    for key, value in snapshot.get("settings") or effective_settings():
        print(f"{key:<52} {value}")
    print(f"{'code under test':<52} {snapshot['branch']} {snapshot['commit'][:10]}")
    if failures:
        print("\nPRE-FLIGHT FAILED:")
        for line in failures:
            print("  -", line)
        return 1
    print("\nPRE-FLIGHT OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
