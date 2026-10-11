# Judge v3 – proof that Phase 1 verdicts are unchanged (GATE 4a evidence)

Date: 2026-10-11 · Branch `crawler-v2` · APPROVED by the project owner at GATE 4a (with two conditions: local test of `--code-manifest auto`; regenerate stale `run_stats.md`) and re-frozen as `phase2-judge-v3`.

## What changed (3 files, 24 lines added, 6 removed)
| File | Change | Effect on Phase 1 |
|---|---|---|
| `judge.py` | `STATUS_WORD` gets 4 new entries: parked, redirected, under_construction, requires_review. The "vocabulary cannot express" reason text is skipped only when `c["status_vocab"] == "v3"`. | None: Phase 1 data never contains those words and never sets `status_vocab`. |
| `run_eval.py` | New options `--code-manifest` (`auto` / path / omitted) and `--code-tag`; manifest records `code_sha256`; `--include-from` refuses a source run with a different code hash; `build_reports` sets `status_vocab="v3"` only if the manifest tag is not `crawler-baseline-v1`. | Defaults reproduce Phase 1 exactly (baseline manifest, tag `crawler-baseline-v1`). |
| `tools/freeze_judge.py` (not a frozen file) | `write` accepts a tag and reason on the command line instead of the hard-coded Phase 1 text. | Tooling only. |
No judge rule, compatibility table, check, label rule or dataset row was changed.

## Proof
Method: copy the saved Phase 1 run `existing-code_full_20261011` to a scratch folder, rebuild all verdicts with the changed code
(`run_eval.py --report-only <copy>`; no network, no crawler), compare with the committed files.

| File | Result |
|---|---|
| `results.csv` (988 rows, every verdict, reason, check) | **byte-identical** (SHA-256 prefix `2C86F6220B9D`) |
| `metrics.json` (all counts, by-category table) | **byte-identical** (SHA-256 prefix `933AC9AB5FEC`) |
| `summary.md` regenerated vs `run_stats.md` | differ, explained: the committed `run_stats.md` is a stale copy from BEFORE label round 2 (it still shows MISMATCH 164 / ENV 29 / SITE-CHANGED 39); the regenerated file shows 169 / 27 / 36, the same numbers as the committed `metrics.json` and `summary.md` of Phase 1. Not a judge effect. |
| dataset `testing_URLs.csv` | unchanged, SHA-256 prefix `0963AB3FEAD262C8` |
Verdict counts reproduced: MATCH 752, MISMATCH 169, ENV-DEPENDENT 27, SITE-CHANGED 36, PARTIAL 3, ORACLE-LIMITATION 1.

## Local-only test of `--code-manifest auto` (GATE 4a condition A1; no real sites; 8 scenario rows, `dataset/mini_local.csv`)
| Test | Expected | Actual |
|---|---|---|
| Run A (`--code-manifest auto`, unchanged old code) | hash at start, re-check at end | `code_manifest.json` created (56 files, combined `59e787ea…`); check OK before and after; 8/8 rows crawled; manifest has `code_sha256`, tag `phase2-dev-selftest` |
| Run B (`--include-from` run A, same code) | rows reused, nothing crawled | "reused 8 row results … not crawled again"; to do now: 0 |
| Run C (`--include-from` a copy of A with an altered `code_sha256`) | refused | `--include-from run used different code (code hash differs)` |
| Run D (`--code-manifest <manifest with one file hash flipped>`) | mismatch detected | `MISMATCH {'changed': ['app/__init__.py']}` before and after; `app_code_unchanged_before/after` both False |
No bug found. Runs C and D were deliberate negative tests; their (empty) result folders were deleted. A test-setup slip of mine (PowerShell 5.1 wrote a BOM into a JSON file) was not a harness bug.
Not tested here: the new status words with a real Phase 2 crawler (needs Phase 2 code; covered by unit tests later).

## Frozen
`run_stats.md` is not in the frozen list; it was regenerated from the verified round-2 numbers (MATCH 752, PARTIAL 3, MISMATCH 169, ENV 27, SITE-CHANGED 36, ORACLE-LIMITATION 1).
Re-frozen 2026-10-11 as tag `phase2-judge-v3`, combined hash `b5b3a08be96c…` (previous `8f951d1f…` kept in `FROZEN_JUDGE.json`). `freeze_judge.py verify` → `FROZEN JUDGE OK`.
Rule from now on: no frozen file is edited except through this procedure (user's written approval → proof → re-freeze → tag).
