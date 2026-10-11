# Run summary – new-local-scenarios-1

Code under test: `new-local-scenarios` (git `ea0cafa4`, tag `phase2-dev-selftest`). App code unchanged during the run: **True**. Dataset `local_scenarios.csv` sha256 `35c840640e6755fb…`. Concurrency used: **5** (the crawler's own default is 10; Phase 2 must use the same value as the final Phase 1 run).



## Verdicts

| Verdict | Rows |
|---|---:|
| MATCH | 60 |
| PARTIAL | 0 |
| MISMATCH | 0 |
| ENV-DEPENDENT | 0 |
| SITE-CHANGED | 0 |
| ORACLE-LIMITATION | 0 |
| HARNESS-ERROR | 0 |
| NOT-RUN | 0 |
| **Total** | 60 |

`ENV-DEPENDENT` = result caused by this network (Pakistan ISP resolver, geo-blocking), not counted as a crawler bug. `SITE-CHANGED` = the site no longer behaves as it did when the dataset was built.

## By category

| Category | Rows | MATCH | PARTIAL | MISMATCH | ENV | SITE-CHG | Other |
|---|---:|---:|---:|---:|---:|---:|---:|
| Bot-protected / WAF | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| Crawl traps | 20 | 20 | 0 | 0 | 0 | 0 | 0 |
| Encoding oddities | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| HTTP errors | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| Login-walled | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| Non-HTML and heavy content | 9 | 9 | 0 | 0 | 0 | 0 | 0 |
| Parked / for-sale domains | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| Redirect behaviour | 6 | 6 | 0 | 0 | 0 | 0 | 0 |
| Thin / empty / error-only pages | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| Timeouts / refused / slow | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| Under construction / default pages | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| robots.txt | 6 | 6 | 0 | 0 | 0 | 0 | 0 |

## Numbers from this run only

* Crawler statuses: {'parked': 1, 'under_construction': 3, 'unreachable': 4, 'blocked': 3, 'failed': 9, 'crawled': 34, 'requires_review': 3, 'invalid': 1, 'robots_blocked': 2}
* Happy-path rows: 0; crawled: 0; with ≥500 characters of text: 0
* Per-site time p50 8.29 s, p95 52.04 s; HTTP requests 498; retries 13; browser used on 1 rows
* Wall time of crawl 278.6 s; throughput 775.3 sites/hour (this run, concurrency 5, mixed fast/slow test rows — not a forecast); peak memory of the Python process 140.2 MB (Chromium not included)

## Rows that did not match (first 60)

| Id | Category | URL | Expected | Actual | Verdict | Reason |
|---|---|---|---|---|---|---|
