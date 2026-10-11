# Judge v3 – proof that Phase 1 verdicts are unchanged (GATE 4a evidence)

Date: 2026-10-11 · Branch `crawler-v2` · Proposed change, NOT yet re-frozen (waits for the project owner's OK).

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

## Not yet proven (honest limits)
- The `--code-manifest auto` path has only been syntax-checked and its `--help` shown; it runs for the first time in a Phase 2 run.
- The new status words are exercised by unit tests only after the Phase 2 code exists.

## After approval
`freeze_judge.py write <scratch copy> phase2-judge-v3 "<reason>"` → new `FROZEN_JUDGE.json` (previous hashes kept) → commit → tag `phase2-judge-v3`.
Until then `freeze_judge.py verify` correctly says `FROZEN JUDGE CHANGED: ['judge.py', 'run_eval.py']`.
