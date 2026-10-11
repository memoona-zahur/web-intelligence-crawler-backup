# Run summary – mini-local-A

Code under test: `mini-local` (git `cd1209e4`, tag `phase2-dev-selftest`). App code unchanged during the run: **True**. Dataset `mini_local.csv` sha256 `766cbeb5ffc6ef31…`. Concurrency used: **5** (the crawler's own default is 10; Phase 2 must use the same value as the final Phase 1 run).



## Verdicts

| Verdict | Rows |
|---|---:|
| MATCH | 3 |
| PARTIAL | 0 |
| MISMATCH | 5 |
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
| Login-walled | 1 | 0 | 0 | 1 | 0 | 0 | 0 |
| Parked / for-sale domains | 1 | 0 | 0 | 1 | 0 | 0 | 0 |
| Thin / empty / error-only pages | 1 | 0 | 0 | 1 | 0 | 0 | 0 |
| Under construction / default pages | 2 | 0 | 0 | 2 | 0 | 0 | 0 |
| robots.txt | 2 | 2 | 0 | 0 | 0 | 0 | 0 |

## Numbers from this run only

* Crawler statuses: {'crawled': 5, 'robots_blocked': 1, 'empty': 2}
* Happy-path rows: 0; crawled: 0; with ≥500 characters of text: 0
* Per-site time p50 0.2 s, p95 1.97 s; HTTP requests 24; retries 0; browser used on 0 rows
* Wall time of crawl 2.5 s; throughput 11520.0 sites/hour (this run, concurrency 5, mixed fast/slow test rows — not a forecast); peak memory of the Python process 82.7 MB (Chromium not included)

## Rows that did not match (first 60)

| Id | Category | URL | Expected | Actual | Verdict | Reason |
|---|---|---|---|---|---|---|
| T0631 | Parked / for-sale domains | http://127.0.0.1:8830/ | Parked | Crawled | MISMATCH | expected Parked, crawler said Crawled:  |
| T0675 | Under construction / default | http://127.0.0.1:8828/ | Under Construction | Crawled | MISMATCH | expected Under Construction, crawler said Crawled:  |
| T0676 | Under construction / default | http://127.0.0.1:8829/ | Under Construction | Crawled | MISMATCH | expected Under Construction, crawler said Crawled:  |
| T0858 | Login-walled | http://127.0.0.1:8831/ | Requires Review | Under Construction | MISMATCH | expected Requires Review, crawler said Under Construction: no usable text found |
| T0967 | Thin / empty / error-only pa | http://127.0.0.1:8826/ | Requires Review | Under Construction | MISMATCH | expected Requires Review, crawler said Under Construction: no usable text found |
