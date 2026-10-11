# Phase 2 — status of every requirement (CR-ID), end of build step 6

**What the words mean.** Nothing here is a field-test verdict: no real website has been crawled by the new code yet.
- **TESTED** = built, and covered by automated tests that were run (fixtures, mocked network, local servers, real Chromium on local pages).
- **TESTED (SQLite)** = same, but the PostgreSQL part is **NOT TESTED** (PostgreSQL is not installed yet; `tests/test_queue_pg.py` is written and skips until `TEST_DATABASE_URL` is set).
- **FIELD** = built and tested locally; whether it works on real sites is measured by Smoke-1 / Full-1 (needs the real `CRAWLER_CONTACT_URL`).
- **DEFERRED** = optional requirement left out on purpose.
Phase 1 column = verdict of the existing code in `existing-code_full_20261011`. Test files are under `tests/`; `issue` = Phase 1 issue id.

| CR | Pri | P1 | Phase 2 status | How it is handled (code) | Evidence (tests) / what is still needed |
|---|---|---|---|---|---|
| A01 | M | PARTIAL | TESTED | `importer._read`, `ops import` (CSV/XLSX/lines, id + source columns) | test_normalize_v2 (record id/source), test_ops (CSV, Excel). Web-form Excel upload path unchanged, not re-tested |
| A02 | M | PASS | TESTED | `import_urls` adds only new sites | test_normalize_v2::incremental |
| A03 | S | FAIL | TESTED (SQLite source) | `ops import-from-db` (read-only SELECT, validated names) | test_ops::import_from_an_existing_database_table, ::refuses_odd_table_names. PostgreSQL source NOT TESTED |
| A04 | M | PARTIAL | TESTED | several URLs per paste / `ops import`; `ops requeue --url` | test_normalize_v2, test_ops::requeue |
| A05 | O | FAIL | DEFERRED | API submission is "later phase" in RD §4 | listed as deferred |
| A06 | M | PARTIAL | TESTED | `normalize.py`: IDNA, trailing dot, `//host`, full-width, ports, www, case | test_normalize_v2 (25 spellings, ISS-18) |
| A07 | M | PARTIAL | TESTED | original kept (credentials removed, F08), `source_file`, `source_batch`, `source_record_id` columns | test_normalize_v2, test_ops |
| A08 | M | PARTIAL | TESTED | `normalize_website` never raises; per-line validation; `import_issues` | test_normalize_v2 (garbage list, blank-line crash found and fixed, ISS-04/19/36) |
| A09 | S | PARTIAL | TESTED | `ops recrawl --older-than N` (classification kept until text changes) | test_ops::recrawl_* |
| A10 | M | PARTIAL | TESTED | `jobs` counts + `import_issues` rows with reasons | test_normalize_v2::import_summary_reviewable |
| A11 | M | PARTIAL | TESTED (SQLite) | batched duplicate check, 25 MB default limit | 60,000 lines in 21.6 s on SQLite (test); Phase 1: 49.9 s. PostgreSQL 60k test written, NOT TESTED |
| A12 | M | PARTIAL | TESTED | `crawl_tasks`, `crawl_errors`, `jobs` progress | test_queue, test_runner_v2, test_persist |
| A13 | M | PARTIAL | TESTED (SQLite) | task states queued → claimed → crawling → extracting → done / retry_scheduled / failed / cancelled; leases; recovery; prompt cancel | test_queue, test_runner_v2 (worker death, cancel < 3 s, lease renewal/loss). PG NOT TESTED |
| B01 | M | PARTIAL | TESTED / FIELD | status + category per failure: dns, tls, timeout, network, http_4xx/5xx, robots_*, redirect | test_pipeline_v2 (incl. TLS), test_guard_v2 |
| B02 | M | FAIL | TESTED / FIELD | `quality.assess_page` parked detector (text, provider hosts, marketplace) | test_quality_v2 (7 parked + false-positive guard); harness local row T0631 MATCH; 30 real parked rows = FIELD |
| B03 | M | PARTIAL | TESTED / FIELD | coming-soon / default-server detector | test_quality_v2 (8); harness T0675, T0676 MATCH; real rows = FIELD |
| B04 | M | PASS | TESTED / FIELD | challenge detector (never bypassed, never sent to the browser) | test_quality_v2 (6), test_pipeline_v2 |
| B05 | M | PARTIAL | TESTED | normalisation merges spellings; redirect to a site already in the list sets `duplicate_of_id` | test_normalize_v2, test_persist::..._flagged_as_a_duplicate. Different hosts of one company (blog.x.com vs x.com) are deliberately separate sites |
| B06 | M | PARTIAL | TESTED | status words: crawled, redirected, parked, under_construction, requires_review, blocked, robots_blocked, unreachable, invalid, failed + lifecycle (pending/queued/crawling/extracting = "Active") + `website_status` word | test_pipeline_v2, test_persist, test_runner_v2; judge v3 reads the new words |
| B07 | M | PARTIAL | TESTED | `crawl_outcome` Completed / Partial / Failed / Blocked; partial keeps evidence | test_pipeline_v2, test_persist::partial_crawl... |
| B08 | M | PARTIAL | TESTED | crawl status columns separate from `classification_status`; failed recrawl marks old text stale | test_persist::crawl_status_is_separate..., ::failed_recrawl_keeps_old_text_but_marks_it_stale |
| B09 | M | PARTIAL | TESTED | import validation before any task exists; `is_global` rule; DNS check at fetch | test_guard_v2 (36 non-global addresses, 8 odd spellings of private addresses, 9 internal names, 7 non-http schemes), test_normalize_v2 |
| B10 | M | FAIL | TESTED | every redirect hop and every browser request goes through the guard; Chromium has no network of its own | test_guard_v2 (redirect hops), **test_browser_real (JavaScript redirect to 127.0.0.2: secret never fetched)** |
| C01 | M | PASS | TESTED / FIELD | focused crawl: coverage-based page selection | test_pipeline_v2 |
| C02 | M | PASS | TESTED | homepage first | test_pipeline_v2 |
| C03 | M | PARTIAL | TESTED / FIELD | page types About/Products/Services/Industries/Customers/Contact; word lists for 18 languages (15 of them tested) | test_discover_v2 (65 genuine paths in 15 languages, all recognised; Phase 1 scored 28 of 36 such paths 0); gold-set recall = FIELD |
| C04 | S | PARTIAL | TESTED | fetch order About → Products → Services → Industries → Customers → Contact; other pages only if evidence is thin | test_discover_v2::preference_order, test_pipeline_v2 |
| C05 | M | FAIL | TESTED / FIELD | link text, menu position, title/aria-label, sitemap, page title confirmation, non-standard paths | test_discover_v2, test_pipeline_v2 (non-English, sitemap-only) |
| C06 | M | PARTIAL | TESTED | whole-word skip rules; section words always skip; policy words skip unless a business word is present | test_discover_v2 (29 junk paths, whole-word tests) |
| C07 | M | PARTIAL | TESTED / FIELD | budget 8 (config 5-10); stop when core page types are read AND enough text | test_pipeline_v2 (budget, early stop) |
| C08 | M | PARTIAL | TESTED | robots sitemaps, common locations, index, gz (bounded), ranking, never the whole sitemap, entity bombs refused | test_discover_v2 (sitemap section: 9 tests) |
| C09 | M | PARTIAL | TESTED | canonical keys, depth/repeat/date/pagination traps, candidate cap | test_discover_v2, test_pipeline_v2::duplicate_urls...; local trap rows = see scenario run |
| C10 | M | FAIL | TESTED | `rel=canonical`, case/slash/index.html/tracking parameters | test_discover_v2::urls_that_differ_only..., test_pipeline_v2 |
| D01 | M | PASS | TESTED | httpx, HTTP first for every page | test_fetcher* |
| D02 | M | PARTIAL | TESTED | 10 redirects, meta-refresh, charset detection, content-type rules, timeouts | test_fetcher_v2, test_extract_v2 (Shift_JIS/Latin-1/UTF-16/BOM), test_pipeline_v2 (meta refresh) |
| D03 | M | PARTIAL | TESTED | text, meta, h1-h6, tables, lists, links, structured data | test_extract_v2 |
| D04 | M | PARTIAL | TESTED | `assess_page`, thresholds in `config` | test_quality_v2 |
| D05 | M | PARTIAL | TESTED / FIELD | browser only for a script shell; never for challenge/parked/login; max 3 per site; waits for text to settle | test_pipeline_v2 (6 browser tests), test_browser_real (SPA read after 700 ms render) |
| D06 | M | PARTIAL | TESTED | no images/media/fonts/CSS/ads; request cap; guard + gate on every request; one Chromium reused | test_browser_real (assets not requested, cap, SSRF). Byte cap and per-render timeout: code only, NOT separately tested |
| D07 | M | PARTIAL | TESTED | `pages.method`, browser attempts traced | test_persist, test_pipeline_v2 |
| D08 | M | PASS | FIELD | HTTP-first design | browser-fallback rate measured in Full-1 |
| D09 | M | FAIL | TESTED | streamed byte cap, gzip/deflate expanded with a hard output limit, ratio cap, whole-request deadline, redirect cap | test_fetcher_v2 (150 MB gzip bomb: peak memory < 60 MB; slow drip cut at the deadline; endless stream stopped) |
| D10 | M | FAIL | TESTED | websites + pages columns | test_persist |
| E01 | M | PASS | TESTED | only cleaned text leaves the crawler | test_extract_v2 |
| E02 | M | PARTIAL | TESTED | keeps title, meta, h1-h6, paragraphs, lists, tables, definition lists, text blocks | test_extract_v2 |
| E03 | M | PARTIAL | TESTED | scripts, nav, footer, cookie/popup banners removed (whole-word hints), repeated lines kept once | test_extract_v2 (14 wrapper-class cases, ISS-05) |
| E04 | M | PARTIAL | TESTED | JSON-LD (graph), Open Graph, meta, canonical; validated, source URL kept | test_extract_v2 (structured section), test_pipeline_v2 |
| E05 | M | PARTIAL | TESTED | duplicate lines across pages, page and site hashes, kept/dropped character counts | test_pipeline_v2, test_persist |
| E06 | M | PARTIAL | TESTED | hash compare; classification kept when text unchanged | test_persist |
| E07 | M | FAIL | TESTED | `page_contents` apart from `pages`; optional gzip raw HTML + purge | test_persist (raw off by default, on + purge) |
| E08 | M | PARTIAL | TESTED | per-page cleaned content + source URL + method | test_persist |
| E09 | M | PARTIAL | TESTED | URL, retrieved-at, method per page; every section of `clean_text` maps to a page row | test_persist::each_stored_fact_traces... |
| E10 | M | PARTIAL | TESTED | `truncation_note` says what was cut | test_pipeline_v2::truncation... |
| E11 | M | NOT TESTED | TESTED | `app/sanitize.py` in `ops export-crawl` and in the company CSV/XLSX/JSON export | test_ops (formula cells neutralised, control characters removed) |
| E12 | O | FAIL | DEFERRED | personal-data policy needed; structured data deliberately ignores telephone/e-mail | test_extract_v2::no_contact_details_are_collected |
| F01 | M | PARTIAL | TESTED / FIELD | RFC 9309 via protego; 5xx/429 = not crawled now; policy in `docs/robots-policy.md`; setting `ROBOTS_5XX_POLICY` (pending sir) | test_fetcher_v2 (21 robots tests), test_pipeline_v2; harness T0818 MATCH |
| F02 | M | PARTIAL | TESTED | one name `WebsiteIntelligenceBot/2.0 (+contact)`; production refuses to start without a real contact; test contact never sent to non-local hosts | test_settings, test_fetcher_v2 (contact policy), test_runner_v2, test_worker_cli |
| F03 | M | PARTIAL | TESTED | per-domain gate (1 request at a time, min gap), concurrency setting, `.env` loaded for every entry point | test_politeness, test_runner_v2, test_settings |
| F04 | M | FAIL | TESTED | exponential back-off + jitter, 3 attempts, Retry-After | test_fetcher_v2, test_politeness |
| F05 | M | PARTIAL | TESTED / FIELD | gap doubles after 403/429/5xx; 2 strikes stop the site; challenge pages recorded as Blocked; no bypass of any kind | test_politeness, test_pipeline_v2 |
| F06 | M | PARTIAL | TESTED | domain health written (latency, failures, last success, back-off) | test_persist |
| F07 | M | PARTIAL | TESTED (SQLite) | queue reads the back-off; one running task per domain (unique index); a slow site cannot block others | test_queue, test_runner_v2; SQLite scale test: 0 same-domain overlaps in 3 x 1,000 sites. PG NOT TESTED |
| F08 | M | PARTIAL | TESTED | credentials removed from stored URLs, cookies never kept | test_normalize_v2, test_fetcher_v2 |
| F09 | M | PARTIAL | TESTED | failure reason + retry count per site (`crawl_errors`, `retry_count`, `next_retry_at`); `ops requeue`; `ops recrawl` | test_persist, test_ops, test_runner_v2 |
| F10 | S | N/A | TESTED (document) | no proxies or IP rotation; connection pooling; network caveats recorded | `docs/robots-policy.md`, this file |
| G01 | M | PARTIAL | TESTED (SQLite) | durable queue table (pending sir confirmation) | test_queue; PG NOT TESTED |
| G02 | M | PARTIAL | TESTED (SQLite) | bounded concurrency, scheduled retries (`not_before`), idempotent enqueue, hash reprocess, batch progress | test_queue, test_runner_v2 |
| G03 | M | NOT TESTED | TESTED (SQLite) | separate crawl-worker process (`python -m app.crawler.worker`); AI workers are a different program | 3 processes sharing one SQLite queue: scale test PASS at concurrency 5/10/20. PG with 3 processes NOT TESTED |
| G04 | M | PARTIAL | TESTED | `ops metrics`: success rate, latency p50/p95, errors, retries, throughput | test_ops |
| G05 | M | PARTIAL | TESTED | JSON event log, plain error text, no swallowed exceptions (every failure keeps its reason), save failures recorded | test_runner_v2, test_pipeline_v2 |
| G06 | M | PARTIAL | TESTED | per-site isolation; a crash, a failing save or a bad import line never stops the batch | test_runner_v2, test_normalize_v2 |
| G07 | M | PASS | DOC | planning figure only; no worker count or runtime assumed | `docs/open-questions-for-sir.md` |
| G08 | M | PARTIAL | PARTLY TESTED | pilot-first; local benchmark at 5/10/20 | SQLite done (`crawl_eval/results/scale_sqlite_local`). **PostgreSQL scale test NOT TESTED**; real sites stay at 5 |
| G09 | M | PARTIAL | TESTED | monitoring (`ops metrics`, `queue-status`), retries, export checkpoint (`ops export-crawl`) | test_ops |
| H01 | M | PARTIAL | TESTED (SQLite) | Alembic migrations 0001-0003, models == migrations, idempotent | test_migrations. **PostgreSQL NOT TESTED** (needs install) |
| H02 | M | FAIL | TESTED | tables: websites, jobs, crawl_tasks, pages, page_contents, fetch_attempts, crawl_errors, import_issues, domain_stats | test_migrations, test_persist |
| H03 | M | PARTIAL | TESTED | timestamps, hashes, retry metadata | test_persist |
| H04 | M | PARTIAL | TESTED | the 12 crawl export columns | test_ops::csv_export_has_the_crawl_columns... |
| H05 | M | FAIL | TESTED | Crawled Pages and Errors sheets | test_ops |
| I01 | M | N/A | FIELD | same dataset, smoke 100 → full | needs Smoke-1 |
| I02 | M | PARTIAL | FIELD | harness metrics (frozen), `ops metrics` | needs the field runs |
| I03 | M | PASS | DOC | no production-ready or "60,000 in X hours" claim is made | this file |
| I04 | M | N/A | FIELD | pilot report | needs the field runs |
| J01 | M | PARTIAL | TESTED | one test module per item (see the stop report) | `pytest` output |
| J02 | M | PARTIAL | TESTED | fixtures: HTML, redirects, errors, empty responses, duplicates, sitemaps, structured data, JS-rendered (real Chromium) | tests/sitekit.py + test modules |
| J03 | M | PASS | TESTED | unit tests use a mocked network and no DNS | conftest `no_dns`; browser tests use local servers only |
| J04 | M | PARTIAL | TESTED | real pytest output and coverage in the stop report; README figures corrected (ISS-30) | stop report |
| K01-K07 | M | N/A | REVIEWED | names/seams kept (harness contract 68/68), modular typed code, config in `.env`/settings, Alembic for every schema change, only the approved packages added, idempotent tasks, only executed results reported | `crawl_eval/tools/check_harness_contract.py`, git history |
