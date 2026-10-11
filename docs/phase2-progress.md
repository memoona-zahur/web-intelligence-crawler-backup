# Phase 2 progress log (crawler-v2)

Read this first after a `/clear`. Full plan: `C:\Users\DELL\.claude\plans\pasted-content-id-c7ba-read-claude-md-imperative-kay.md`
(copy of the approved GATE 4 plan; sections 1-9). Rules: `CLAUDE.md`, `docs/phase-plan.md` section 2.
Python for anything importing `app/`: `C:\crawl_eval_data\venv\Scripts\python.exe -B`.

## Status
| Step | Work | State |
|---|---|---|
| 1a | Branch `crawler-v2` from main 54d03d0; source cross-check | DONE (no new CR-X found) |
| 1b | Judge/harness change (plan section 5) + equivalence proof | DONE, committed 3d17da9 as a PROPOSAL; **not re-frozen, not tagged**. `freeze_judge.py verify` fails on purpose until approval. Evidence: `crawl_eval/judge_v3_equivalence.md` (results.csv + metrics.json byte-identical to Phase 1) |
| GATE 4a | Show diff + equivalence proof to the user | WAITING for approval. Then: `freeze_judge.py write <copy of a run dir> phase2-judge-v3 "<reason>"`, verify, commit, `git tag phase2-judge-v3` |
| 2 | PostgreSQL + new dependencies | BLOCKED until user confirms (see Open questions) |
| 3-6 | Build (settings, guard, importer, fetcher, politeness, detectors, discovery, extraction, browser, queue, persistence, ops) | not started |
| 7 | Smoke-1 (real sites) -> GATE 5 | not started |
| 8 | Full-1 -> GATE 6 | not started |
| 9 | Fix loop, Full-2, Full-3, comparison, sir note -> GATE 7 | not started |

## Decisions (user)
- robots.txt 5xx/unreachable: RFC 9309 strict (retry x2, then Blocked + retry later; 4xx = no rules).
- User-Agent contact: required setting `CRAWLER_CONTACT_URL`, no default; user supplies the real URL before the first real-site run.
- Judge: additive change (4 new status words + `--code-manifest`), prove Phase 1 verdicts identical, re-freeze, tag `phase2-judge-v3`.
- DB: PostgreSQL (native Windows) + Alembic; SQLite only for unit tests and the frozen harness. Queue: PG table `crawl_tasks` (no Redis/Celery).
- Cross-domain redirect: crawl target, status Redirected. Raw HTML off by default. CR-E12, CR-A05 deferred.
- Real-site budget: max 2 smoke + 4 full runs, concurrency 5; loop iterations use unit/fixture/scenario server only.
- Plan additions (GATE 4 approval): keep this file updated; commit after every build step; G08 scale test (1,000 local sites, concurrency 5/10/20) runs on PostgreSQL with 2-3 worker processes (not only SQLite); run the 100-row smoke subset once through the PG + queue path (outside the frozen harness) and report differences from the SQLite smoke; **before installing PostgreSQL or any dependency, give exact steps and wait for confirmation** (user must first check with their sir that PostgreSQL + DB queue instead of Redis/Celery is acceptable); never edit frozen `crawl_eval/` files except through GATE 4a; run `freeze_judge.py verify` before every field run; stop at GATE 4a.

## Open questions
- Sir's approval of PostgreSQL + DB queue (blocks Step 2 and everything that needs new dependencies).
- Real `CRAWLER_CONTACT_URL` (needed before Smoke-1).

## Test results
(none yet for Phase 2)

## Commits / tags
| Ref | Meaning |
|---|---|
| `crawler-baseline-v1`, `phase1-complete`, `phase1-complete-v2` | Phase 1, never touch |
| `phase2-judge-v3` | to be created at GATE 4a |
