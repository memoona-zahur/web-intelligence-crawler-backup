"""The ONLY way to start a real-site Phase 2 run (Smoke-1, Full-1 ...). It wraps the frozen harness; run_eval.py itself is not touched.

    python -B crawl_eval/tools/run_phase2.py --kind smoke --run-id crawler-v2_smoke1
    python -B crawl_eval/tools/run_phase2.py --kind full  --run-id crawler-v2_full1 --include-from crawl_eval/results/crawler-v2_smoke1
    add --dry-run to see the exact command without running anything

Order: pre-flight (fails on wrong concurrency / missing real contact / dirty code / broken judge or contract) -> run budget ledger
(2 smoke + 4 full) -> frozen harness with --code-manifest auto, concurrency 5 -> check of run_manifest.json -> ledger entry closed.
Nothing here is started by tests or by the build; the user starts it after setting a real CRAWLER_CONTACT_URL.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import preflight  # noqa: E402

ROOT = preflight.ROOT
LEDGER = ROOT / "crawl_eval" / "real_runs_ledger.json"


def load_ledger() -> dict:
    return json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {"budget": preflight.RUN_BUDGET, "runs": []}


def save_ledger(ledger: dict) -> None:
    LEDGER.write_text(json.dumps(ledger, indent=1), encoding="utf-8")


def harness_command(args, tag: str) -> list[str]:
    cmd = [sys.executable, "-B", str(ROOT / "crawl_eval" / "run_eval.py"), "--label", "crawler-v2", "--run-id", args.run_id, "--code-manifest", "auto",
           "--code-tag", tag, "--concurrency", str(args.concurrency)]
    if args.kind == "smoke":
        cmd.append("--smoke")
    if args.include_from:
        cmd += ["--include-from", args.include_from]
    return cmd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("smoke", "full"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--concurrency", type=int, default=preflight.REQUIRED_CONCURRENCY)
    parser.add_argument("--allow-concurrency-override", type=int, default=None)
    parser.add_argument("--include-from", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    failures, snapshot = preflight.run_checks(args.concurrency, args.allow_concurrency_override)
    ledger = load_ledger()
    reason = preflight.ledger_allows(ledger, args.kind)
    if reason:
        failures.append(reason)
    if failures:
        print("PRE-FLIGHT FAILED - nothing was started:")
        for line in failures:
            print("  -", line)
        return 1
    tag = f"crawler-v2@{snapshot['commit'][:10]}"
    cmd = harness_command(args, tag)
    print("pre-flight OK. Command:", " ".join(cmd))
    if args.dry_run:
        return 0

    out_dir = ROOT / "crawl_eval" / "results" / args.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "preflight.json").write_text(json.dumps(snapshot, indent=1, default=str), encoding="utf-8")
    entry = {"kind": args.kind, "run_id": args.run_id, "started": datetime.now().isoformat(timespec="seconds"), "status": "started", "commit": snapshot["commit"],
             "concurrency": args.concurrency}
    ledger.setdefault("runs", []).append(entry)
    save_ledger(ledger)
    env = dict(os.environ, CRAWLER_MODE="production", PYTHONDONTWRITEBYTECODE="1")
    code = subprocess.run(cmd, cwd=ROOT, env=env).returncode
    manifest_file = out_dir / "run_manifest.json"
    problems = preflight.verify_manifest(json.loads(manifest_file.read_text(encoding="utf-8"))) if manifest_file.exists() else ["run_manifest.json was not written"]
    entry.update(status="finished" if code == 0 and not problems else "failed", exit_code=code, problems=problems, finished=datetime.now().isoformat(timespec="seconds"))
    save_ledger(ledger)
    for p in problems:
        print("MANIFEST PROBLEM:", p)
    return 0 if code == 0 and not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
