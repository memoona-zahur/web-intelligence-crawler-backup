# Run summary – harness-selftest_20261010-235527_smoke

Code under test: `harness-selftest` (git `24818a60`, tag `crawler-baseline-v1`). App code unchanged during the run: **True**. Dataset `_selftest.csv` sha256 `926605987e7247b7…`. Concurrency used: **5** (the crawler's own default is 10; Phase 2 must use the same value as the final Phase 1 run).

**This is a smoke run** (selected rows only), so no figure here may be read as a rate for the full dataset or for 60,000 URLs.

## Verdicts

| Verdict | Rows |
|---|---:|
| MATCH | 48 |
| PARTIAL | 3 |
| MISMATCH | 17 |
| ENV-DEPENDENT | 0 |
| SITE-CHANGED | 0 |
| HARNESS-ERROR | 0 |
| NOT-RUN | 0 |
| **Total** | 68 |

`ENV-DEPENDENT` = result caused by this network (Pakistan ISP resolver, geo-blocking), not counted as a crawler bug. `SITE-CHANGED` = the site no longer behaves as it did when the dataset was built.

## By category

| Category | Rows | MATCH | PARTIAL | MISMATCH | ENV | SITE-CHG | Other |
|---|---:|---:|---:|---:|---:|---:|---:|
| Bot-protected / WAF | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| Crawl traps | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| Dead domains (NXDOMAIN) | 4 | 0 | 0 | 4 | 0 | 0 | 0 |
| Encoding oddities | 4 | 3 | 0 | 1 | 0 | 0 | 0 |
| HTTP errors | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| Input handling | 25 | 21 | 0 | 4 | 0 | 0 | 0 |
| Login-walled | 3 | 2 | 0 | 1 | 0 | 0 | 0 |
| Non-HTML and heavy content | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| Parked / for-sale domains | 1 | 0 | 0 | 1 | 0 | 0 | 0 |
| Redirect behaviour | 4 | 0 | 3 | 1 | 0 | 0 | 0 |
| SSL/TLS problems | 4 | 3 | 0 | 1 | 0 | 0 | 0 |
| Thin / empty / error-only pages | 3 | 2 | 0 | 1 | 0 | 0 | 0 |
| Timeouts / refused / slow | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| Under construction / default pages | 2 | 0 | 0 | 2 | 0 | 0 | 0 |
| robots.txt | 4 | 3 | 0 | 1 | 0 | 0 | 0 |

## Numbers from this run only

* Crawler statuses: {'invalid': 5, 'crawled': 22, 'unreachable': 4, 'blocked': 5, 'failed': 6, 'robots_blocked': 2, 'empty': 5}
* Happy-path rows: 0; crawled: 0; with ≥500 characters of text: 0
* Per-site time p50 0.45 s, p95 17.85 s; HTTP requests 144; retries 13; browser used on 0 rows
* Wall time of crawl 28.2 s; throughput 6255.3 sites/hour (this run, concurrency 5, mixed fast/slow test rows — not a forecast); peak memory of the Python process 0.0 MB (Chromium not included)

## Rows that did not match (first 60)

| Id | Category | URL | Expected | Actual | Verdict | Reason |
|---|---|---|---|---|---|---|
| T0621 | Dead domains (NXDOMAIN) | http://crawl-eval-dead-1.invalid/ | Unreachable | Invalid | MISMATCH | expected Unreachable, crawler said Invalid: cannot resolve host 'crawl-eval-dead-1.invalid' |
| T0622 | Dead domains (NXDOMAIN) | http://crawl-eval-dead-2.invalid/ | Unreachable | Invalid | MISMATCH | expected Unreachable, crawler said Invalid: cannot resolve host 'crawl-eval-dead-2.invalid' |
| T0623 | Dead domains (NXDOMAIN) | http://crawl-eval-dead-3.invalid/ | Unreachable | Invalid | MISMATCH | expected Unreachable, crawler said Invalid: cannot resolve host 'crawl-eval-dead-3.invalid' |
| T0624 | Dead domains (NXDOMAIN) | http://crawl-eval-dead-4.invalid/ | Unreachable | Invalid | MISMATCH | expected Unreachable, crawler said Invalid: cannot resolve host 'crawl-eval-dead-4.invalid' |
| T0631 | Parked / for-sale domains | http://127.0.0.1:8830/ | Parked | Crawled | MISMATCH | expected 'Parked', which the crawler's status vocabulary cannot express (CR-B06); crawler said 'Crawled' (None) |
| T0675 | Under construction / default | http://127.0.0.1:8828/ | Under Construction | Crawled | MISMATCH | expected Under Construction, crawler said Crawled:  |
| T0676 | Under construction / default | http://127.0.0.1:8829/ | Under Construction | Crawled | MISMATCH | expected Under Construction, crawler said Crawled:  |
| T0709 | SSL/TLS problems | https://wrong.host.badssl.com/ | Unreachable | Invalid | MISMATCH | expected Unreachable, crawler said Invalid: cannot resolve host 'wrong.host.badssl.com' |
| T0778 | Redirect behaviour | https://httpbin.org/redirect-to?url=https%3A%2F%2F | Redirected | Crawled | PARTIAL | Crawled with final URL https://example.com/ (the crawler has no Redirected status; the final URL is not stored in the DB) |
| T0779 | Redirect behaviour | https://httpbin.org/redirect-to?url=https%3A%2F%2F | Redirected | Crawled | PARTIAL | Crawled with final URL https://example.org/ (the crawler has no Redirected status; the final URL is not stored in the DB) |
| T0780 | Redirect behaviour | https://httpbin.org/redirect-to?url=https%3A%2F%2F | Redirected | Crawled | PARTIAL | Crawled with final URL https://example.net/ (the crawler has no Redirected status; the final URL is not stored in the DB) |
| T0781 | Redirect behaviour | https://httpbin.org/redirect-to?url=https%3A%2F%2F | Redirected | Crawled | MISMATCH | expected 'Redirected', which the crawler's status vocabulary cannot express (CR-B06); crawler said 'Crawled' (None) |
| T0820 | robots.txt | http://127.0.0.1:8820/ | Crawled | Crawled | MISMATCH | failed checks: gap>=9.5 s |
| T0858 | Login-walled | http://127.0.0.1:8831/ | Requires Review | Under Construction | MISMATCH | expected 'Requires Review', which the crawler's status vocabulary cannot express (CR-B06); crawler said 'Under Construction' (no usable text |
| T0871 | Encoding oddities | http://127.0.0.1:8834/ | Crawled | Under Construction | MISMATCH | Japanese text not readable (status Under Construction, 0 chars) |
| T0887 | Input handling | https://example.com. | Duplicate | import:added/crawl:Crawled | MISMATCH | importer said 'added', expected 'duplicate' |
| T0889 | Input handling | //example.com | Duplicate | import:invalid | MISMATCH | importer said 'invalid', expected 'duplicate' |
| T0890 | Input handling | ｅｘａｍｐｌｅ．ｃｏｍ | Duplicate | import:invalid | MISMATCH | importer said 'invalid', expected 'duplicate' |
| T0898 | Input handling | xn--mnchen-3ya.de | Duplicate | import:added/crawl:Crawled | MISMATCH | importer said 'added', expected 'duplicate' |
| T0967 | Thin / empty / error-only pa | http://127.0.0.1:8826/ | Requires Review | Under Construction | MISMATCH | expected 'Requires Review', which the crawler's status vocabulary cannot express (CR-B06); crawler said 'Under Construction' (no usable text |
