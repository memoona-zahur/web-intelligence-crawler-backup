# Run summary – harness-selftest2_20261011-002939

Code under test: `harness-selftest2` (git `24818a60`, tag `crawler-baseline-v1`). App code unchanged during the run: **True**. Dataset `_selftest2.csv` sha256 `d8684b3f0c23adff…`. Concurrency used: **5** (the crawler's own default is 10; Phase 2 must use the same value as the final Phase 1 run).



## Verdicts

| Verdict | Rows |
|---|---:|
| MATCH | 5 |
| PARTIAL | 0 |
| MISMATCH | 2 |
| ENV-DEPENDENT | 0 |
| SITE-CHANGED | 0 |
| HARNESS-ERROR | 0 |
| NOT-RUN | 0 |
| **Total** | 7 |

`ENV-DEPENDENT` = result caused by this network (Pakistan ISP resolver, geo-blocking), not counted as a crawler bug. `SITE-CHANGED` = the site no longer behaves as it did when the dataset was built.

## By category

| Category | Rows | MATCH | PARTIAL | MISMATCH | ENV | SITE-CHG | Other |
|---|---:|---:|---:|---:|---:|---:|---:|
| Corporate / B2B services | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| Non-HTML and heavy content | 3 | 2 | 0 | 1 | 0 | 0 | 0 |
| Redirect behaviour | 2 | 1 | 0 | 1 | 0 | 0 | 0 |
| Timeouts / refused / slow | 1 | 1 | 0 | 0 | 0 | 0 | 0 |

## Numbers from this run only

* Crawler statuses: {'crawled': 3, 'unreachable': 2, 'empty': 1, 'failed': 1}
* Happy-path rows: 1; crawled: 1; with ≥500 characters of text: 1
* Per-site time p50 6.49 s, p95 27.45 s; HTTP requests 45; retries 3; browser used on 1 rows
* Wall time of crawl 45.7 s; throughput 551.4 sites/hour (this run, concurrency 5, mixed fast/slow test rows — not a forecast); peak memory of the Python process 156.3 MB (Chromium not included)

## Rows that did not match (first 60)

| Id | Category | URL | Expected | Actual | Verdict | Reason |
|---|---|---|---|---|---|---|
| T0788 | Redirect behaviour | http://127.0.0.1:8837/ | Crawled | Under Construction | MISMATCH | expected Crawled, crawler said Under Construction: no usable text found |
| T0843 | Non-HTML and heavy content | http://127.0.0.1:8804/ | Failed | Unreachable | MISMATCH | expected Failed, crawler said Unreachable: timeout fetching http://127.0.0.1:8804/ |
