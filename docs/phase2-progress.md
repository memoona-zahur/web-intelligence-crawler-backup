# Phase 2 progress log (crawler-v2)

Read this first after a `/clear`. Full plan: `C:\Users\DELL\.claude\plans\pasted-content-id-c7ba-read-claude-md-imperative-kay.md`
(approved GATE 4 plan, sections 1-9). Rules: `CLAUDE.md`, `docs/phase-plan.md` section 2. Open policy questions: `docs/open-questions-for-sir.md`.
Python for anything importing `app/`: `C:\crawl_eval_data\venv2\Scripts\python.exe -B` (Phase 1 pins + alembic, psycopg[binary], protego, tldextract,
charset-normalizer; list in `docs/phase2-pip-freeze.txt`). The Phase 1 venv `C:\crawl_eval_data\venv` is untouched.
Chromium for the browser tests/harness: `set PLAYWRIGHT_BROWSERS_PATH=C:/crawl_eval_data/browsers`.

## Status
| Step | Work | State |
|---|---|---|
| 1 | Branch `crawler-v2`; source cross-check; judge v3 (+ proof, local `--code-manifest auto` test) | DONE. Judge re-frozen, tag `phase2-judge-v3`, `freeze_judge.py verify` = FROZEN JUDGE OK |
| 2 | Settings, Alembic (baseline + Phase 2 schema), new models | DONE (SQLite tested; PostgreSQL NOT TESTED - not installed) |
| 3 | Guard, normaliser, importer, fetcher (+ robots RFC 9309), politeness | DONE + unit tests |
| 4 | Detectors, discovery, extraction, structured data, browser | DONE + unit tests + real-Chromium tests |
| 5 | Queue, worker, runner, persistence, ops commands | DONE + unit tests; local scale test on SQLite done |
| 6 | Full test run, harness contract, scenario tests, scale test | SQLite parts DONE; **PostgreSQL parts waiting for the PostgreSQL install** |
| GATE 5 | Smoke-1 (real sites) | **NOT STARTED - needs a real `CRAWLER_CONTACT_URL` in `.env` from the project owner** |

## Decisions (user)
- robots.txt 5xx/unreachable: RFC 9309 strict (retry x2, then Blocked + retry later; 4xx = no rules). Network-level failure of the whole site = Unreachable (derived choice, listed in open questions).
- User-Agent contact: required setting `CRAWLER_CONTACT_URL`, no default in production; test contact `test@example.invalid` only in dev/test mode and never sent to a non-local host.
- DB: PostgreSQL (native Windows) + Alembic; SQLite for unit tests, the harness and small local runs. Queue: PG/SQL table `crawl_tasks` (no Redis/Celery). Pending sir confirmation.
- Cross-domain redirect: crawl target, status Redirected. Raw HTML off by default. CR-E12, CR-A05 deferred.
- Real-site budget: max 2 smoke + 4 full runs, concurrency 5; loop iterations use unit/fixture/scenario server only. Run `freeze_judge.py verify` before every field run.
- Never edit frozen `crawl_eval/` files except through the GATE 4a procedure (written approval -> proof -> re-freeze -> tag).
- Install nothing new without confirmation (PostgreSQL steps are in the stop report).

## Open questions
- Sir's confirmation of PostgreSQL + DB queue, robots policy, contact policy: `docs/open-questions-for-sir.md`.
- Real `CRAWLER_CONTACT_URL` (needed before Smoke-1).
- PostgreSQL 17 install (blocks: PG test suite, PG scale test, PG smoke path run).

## Changes to existing tests (each one encoded behaviour now judged wrong)
| File::test | Change | Reason |
|---|---|---|
| tests/conftest.py | TEST mode, zero politeness waits, no DNS in unit tests, schema copied once per session | CR-J03 (no network, not even DNS); speed (suite 136 s -> ~50 s) |
| test_requirements::test_contact_url_changes_the_user_agent | `/1.0` -> `/2.0` | ISS-31: one bot name, version 2 |
| test_pipeline::test_empty_when_below_minimum_text | status `empty` -> `requires_review` | ISS-10/12: new status vocabulary |
| test_fetcher::test_timeout_maps_to_network_and_retries | now `..._retries_once` (2 calls, not 3) + new test for refused connections (3 calls) | a timing-out server holds a worker; one retry |
| test_fetcher::test_robots_fail_open_on_server_error | now: robots 5xx = unavailable, not allowed; plus a test for `ROBOTS_5XX_POLICY=allow` | ISS-14, user decision (pending sir) |
| test_discover::test_excludes_offsite_and_subdomain_links | business subdomains of the same registrable domain are kept; blog./careers. and other domains excluded | CR-C05 |
| test_discover::test_www_variant_matches_base_host | compares `canonical_key` (host as written is kept) | no extra redirect per page |
| test_phase2::test_stops_early_when_enough_text_is_collected | now `..._when_the_important_page_types_are_read` (coverage rule) | ISS-08 |

## Test results
Last full run (2026-10-11, end of build step 6): **739 passed, 9 skipped** (the 9 PostgreSQL tests: no `TEST_DATABASE_URL`), coverage of all of `app/` **94 %** (crawler modules 91-100 %). Full output: `docs/phase2-test-output.txt`.

Other runs (all local, no real website): harness mini run 8/8 MATCH; all 60 local scenario rows MATCH (`crawl_eval/results/new-local-scenarios-1`); SQLite scale test 1,000 sites x 3 processes x concurrency 5/10/20, all checks PASS (`crawl_eval/results/scale_sqlite_local`); harness contract 68/68 (`crawl_eval/tools/check_harness_contract.py`).

## Commits / tags
| Ref | Meaning |
|---|---|
| `crawler-baseline-v1`, `phase1-complete`, `phase1-complete-v2` | Phase 1, never touched |
| `phase2-judge-v3` | judge v3 frozen (GATE 4a) |
| branch `crawler-v2` | all Phase 2 work, committed after every step |
