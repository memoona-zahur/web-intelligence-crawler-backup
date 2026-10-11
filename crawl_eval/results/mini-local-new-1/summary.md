# Run summary – mini-local-new-1

Code under test: `new-mini` (git `b7b33b92`, tag `phase2-dev-selftest`). App code unchanged during the run: **True**. Dataset `mini_local.csv` sha256 `766cbeb5ffc6ef31…`. Concurrency used: **5** (the crawler's own default is 10; Phase 2 must use the same value as the final Phase 1 run).



## Verdicts

| Verdict | Rows |
|---|---:|
| MATCH | 8 |
| PARTIAL | 0 |
| MISMATCH | 0 |
| ENV-DEPENDENT | 0 |
| SITE-CHANGED | 0 |
| ORACLE-LIMITATION | 0 |
| HARNESS-ERROR | 0 |
| NOT-RUN | 0 |
| **Total** | 8 |

`ENV-DEPENDENT` = result caused by this network (Pakistan ISP resolver, geo-blocking), not counted as a crawler bug. `SITE-CHANGED` = the site no longer behaves as it did when the dataset was built.

## By category

| Category | Rows | MATCH | PARTIAL | MISMATCH | ENV | SITE-CHG | Other |
|---|---:|---:|---:|---:|---:|---:|---:|
| Encoding oddities | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| Login-walled | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| Parked / for-sale domains | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| Thin / empty / error-only pages | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| Under construction / default pages | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| robots.txt | 2 | 2 | 0 | 0 | 0 | 0 | 0 |

## Numbers from this run only

* Crawler statuses: {'parked': 1, 'under_construction': 2, 'robots_blocked': 1, 'crawled': 2, 'requires_review': 2}
* Happy-path rows: 0; crawled: 0; with ≥500 characters of text: 0
* Per-site time p50 1.14 s, p95 8.15 s; HTTP requests 27; retries 0; browser used on 0 rows
* Wall time of crawl 8.6 s; throughput 3348.8 sites/hour (this run, concurrency 5, mixed fast/slow test rows — not a forecast); peak memory of the Python process 103.6 MB (Chromium not included)

## Rows that did not match (first 60)

| Id | Category | URL | Expected | Actual | Verdict | Reason |
|---|---|---|---|---|---|---|
