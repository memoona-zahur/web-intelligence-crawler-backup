# Harness design (Step 3) – DESIGN ONLY, not built yet

Goal: run the **unchanged** crawler on `testing_URLs.csv`, watch it without changing it, and compare *expected* vs *actual*.

## 1. One command
```
C:\crawl_eval_data\venv\Scripts\python.exe crawl_eval\run_eval.py --smoke --label existing-code
```
| Option | Meaning |
|---|---|
| `--urls PATH` | dataset file (default `dataset/testing_URLs.csv`) |
| `--smoke` | only rows with `smoke=Y` (100 rows) |
| `--limit N` | first N rows only |
| `--concurrency N` | parallel sites (default **5**, lower than the crawler's own 10, to stay polite) |
| `--label TEXT` | name of the code under test (`existing-code`, later `new-code`) |
| `--resume` | continue the same run id; finished rows are skipped |

## 2. How the real code is used (no copies)
| Step | Real code called |
|---|---|
| Isolated DB | harness points `app.database.engine/SessionLocal` at `C:\crawl_eval_data\db\<run_id>.db` (same pattern as `tests/conftest.py`). `data/websites.db` is never opened. |
| Import | `app.importer.import_urls(session, text)` with the CSV `url` column |
| Crawl | `app.crawler.runner.run(site_ids=[...], concurrency=N)` in batches of 50 rows |
| Results | read back from the isolated DB (`websites`, `jobs`, `domain_stats`) |

## 3. Wrappers (pass-through: same inputs, same outputs, same exceptions)
Every wrapper is listed in `run_manifest.json`. The crawler imports functions *by name*, so each name is patched in every module that holds it.
| Wrapped function | Patched in | What it records |
|---|---|---|
| `fetcher._one_attempt` | fetcher | every network attempt (retries are visible as repeated attempts for the same URL) |
| `fetcher.load_robots` | fetcher, pipeline | robots status, allow/deny decision for the homepage |
| `guard.assert_public_url` | guard, fetcher, browser | allow/deny and reason (guard decisions) |
| `browser.render_page` | browser, pipeline | called?, success, ms, text gain (browser use + benefit) |
| `pipeline.crawl_one` | pipeline, runner | per-site wall time, pages, status, error, peak memory |
| `runner._save` | runner | when the DB write happens (checkpoint evidence) |
| `httpx.AsyncClient.send` (transport level) | httpx | every request: time-stamps, User-Agent actually sent, status, bytes, Retry-After, redirects; also the **safety net** (see section 4) |

## 4. Scenario server and the SSRF guard
* `scenario_server.py` serves rows with `source_type=local-scenario` on `127.0.0.1:8800-8843` (plus `127.0.0.2:8810`).
* The crawler **correctly** refuses loopback, so the harness relaxes the guard **only** for those exact `host:port` pairs, through the `assert_public_url` wrapper. The report states this on page 1.
* The guard stays **fully on** for every other row: `localhost`, private ranges, metadata addresses, `localtest.me`, `lvh.me`, and the "redirect to 127.0.0.2:8810/secret" rows (the 127.0.0.2 secret server is *not* on the allow-list, so a working guard refuses it; `SECRET-TOKEN-4711` must not appear in any stored text).
* Control row: `127.0.0.1:8800` (normal site) proves the relaxed path works before scenario results are trusted.

## 5. Independent probe (changed after the smoke run – see harness_problems.md H2)
The first design (DNS + HEAD before each batch) was wrong. Now: **after** the crawl, only for real / public-test rows that did **not** MATCH, the harness does DNS (system resolver and 1.1.1.1) plus one GET of the homepage (https, then http; robots.txt respected) and reads the page like a person (`predict_word`). Public test hosts get DNS only. The reading is compared with the dataset expectation through a compatibility table (`judge.COMPAT`). Labels: **ENV-DEPENDENT** (ISP resolver fails but public DNS works, or a `network-dependent`/`geo-risk` row that this network cannot reach/gets blocked), **SITE-CHANGED** (probe disagrees with the dataset expectation and the crawler's own telemetry does not reproduce the row's premise), otherwise **MISMATCH** (crawler).

## 6. Checkpoint and resume
* `results/<run_id>/per_site.jsonl` is appended after every site; `run.log` after every batch.
* Ctrl-C or a network drop loses at most the current batch; `--resume` skips rows already in `per_site.jsonl`.
* The crawler's own recovery (`recover_abandoned`) is exercised, not bypassed.

## 7. Verdict per row (expected vs actual)
Mapping from the crawler's status words to the requirement vocabulary (CR-B06):
| Crawler status | Requirement word |
|---|---|
| crawled | Crawled |
| empty | Under Construction (nearest word; the code has no such status) |
| unreachable | Unreachable |
| blocked, robots_blocked | Blocked |
| invalid | Invalid |
| failed | Failed |
| (no status exists) | Parked, Redirected, Active, Requires Review → always a mismatch unless the oracle accepts "Crawled + extra evidence" |

Verdicts: **MATCH**, **PARTIAL** (right class, wrong word, listed per row), **MISMATCH**, **SITE-CHANGED**, **HARNESS-ERROR** (shown separately from crawler errors), plus pass/fail *checks* for rows with special criteria in `notes` (e.g. "SECRET-TOKEN absent", "pages ≤ 10", "no `/about` fetched").

## 8. What is measured per run
Success and useful-content rate, gold-set precision/recall of key pages (CR-I02), pages per site, text size, truncation, HTTP vs browser use and benefit, latency p50/p95, retries and failure reasons, blocked rate, request spacing per domain, throughput (sites/hour, **this run only – no extrapolation**), peak memory (sampled every 5 s), DB/log inspection for CR-D10/H-group, and a per-CR-ID scorecard with evidence.

## 9. Politeness limits for the live run
Each real domain is visited once per run (by the crawler: robots + homepage + at most 7 pages + sitemap; by the harness: one DNS + one HEAD). Concurrency 5. Smoke first (100 rows), then GATE 2, then the full run. No re-runs of the full set.
