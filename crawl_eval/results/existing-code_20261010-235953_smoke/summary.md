# Run summary – existing-code_20261010-235953_smoke

Code under test: `existing-code` (git `24818a60`, tag `crawler-baseline-v1`). App code unchanged during the run: **True**. Dataset `testing_URLs.csv` sha256 `0963ab3fead262c8…`. Concurrency used: **5** (the crawler's own default is 10; Phase 2 must use the same value as the final Phase 1 run).

**This is a smoke run** (selected rows only), so no figure here may be read as a rate for the full dataset or for 60,000 URLs.

## Verdicts

| Verdict | Rows |
|---|---:|
| MATCH | 79 |
| PARTIAL | 0 |
| MISMATCH | 16 |
| ENV-DEPENDENT | 0 |
| SITE-CHANGED | 5 |
| HARNESS-ERROR | 0 |
| NOT-RUN | 0 |
| **Total** | 100 |

`ENV-DEPENDENT` = result caused by this network (Pakistan ISP resolver, geo-blocking), not counted as a crawler bug. `SITE-CHANGED` = the site no longer behaves as it did when the dataset was built.

## By category

| Category | Rows | MATCH | PARTIAL | MISMATCH | ENV | SITE-CHG | Other |
|---|---:|---:|---:|---:|---:|---:|---:|
| Bot-protected / WAF | 2 | 1 | 0 | 0 | 0 | 1 | 0 |
| Corporate / B2B services | 7 | 7 | 0 | 0 | 0 | 0 | 0 |
| Crawl traps | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| Dead domains (NXDOMAIN) | 3 | 0 | 0 | 3 | 0 | 0 | 0 |
| E-commerce and retail | 6 | 5 | 0 | 1 | 0 | 0 | 0 |
| Encoding oddities | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| HTTP errors | 3 | 2 | 0 | 0 | 0 | 1 | 0 |
| Healthcare, education, finance, real estate, non-profit, government | 8 | 7 | 0 | 0 | 0 | 1 | 0 |
| Input handling | 8 | 7 | 0 | 1 | 0 | 0 | 0 |
| JavaScript-heavy SPAs | 5 | 4 | 0 | 1 | 0 | 0 | 0 |
| Large multinational enterprises | 3 | 3 | 0 | 0 | 0 | 0 | 0 |
| Login-walled | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| Manufacturers, industrial, distributors, wholesalers | 6 | 3 | 0 | 3 | 0 | 0 | 0 |
| Minimal / one-page / static sites | 3 | 2 | 0 | 0 | 0 | 1 | 0 |
| Non-English / international | 8 | 8 | 0 | 0 | 0 | 0 | 0 |
| Non-HTML and heavy content | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| Parked / for-sale domains | 3 | 0 | 0 | 3 | 0 | 0 | 0 |
| Redirect behaviour | 4 | 3 | 0 | 1 | 0 | 0 | 0 |
| SSL/TLS problems | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| SaaS / software / platforms | 6 | 6 | 0 | 0 | 0 | 0 | 0 |
| Sitemap variants and non-standard navigation | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| Small local businesses on site builders | 6 | 6 | 0 | 0 | 0 | 0 | 0 |
| Thin / empty / error-only pages | 2 | 0 | 0 | 2 | 0 | 0 | 0 |
| Timeouts / refused / slow | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| Under construction / default pages | 2 | 1 | 0 | 0 | 0 | 1 | 0 |
| robots.txt | 2 | 1 | 0 | 1 | 0 | 0 | 0 |

## Numbers from this run only

* Crawler statuses: {'crawled': 69, 'blocked': 7, 'empty': 6, 'invalid': 4, 'unreachable': 5, 'failed': 2, 'robots_blocked': 1}
* Happy-path rows: 60; crawled: 53; with ≥500 characters of text: 48
* Per-site time p50 7.49 s, p95 25.57 s; HTTP requests 722; retries 38; browser used on 13 rows
* Wall time of crawl 213.7 s; throughput 1583.5 sites/hour (this run, concurrency 5, mixed fast/slow test rows — not a forecast); peak memory of the Python process 141.0 MB (Chromium not included)

## Rows that did not match (first 60)

| Id | Category | URL | Expected | Actual | Verdict | Reason |
|---|---|---|---|---|---|---|
| T0081 | Manufacturers, industrial, d | https://gem.polaris.com/en-us/ | Crawled | Blocked | MISMATCH | expected Crawled, crawler said Blocked: HTTP 403 from https://www.gemcar.com |
| T0082 | Manufacturers, industrial, d | https://matthewsaurora.com/ | Crawled | Blocked | MISMATCH | expected Crawled, crawler said Blocked: HTTP 403 from https://matthewsaurora.com |
| T0093 | Manufacturers, industrial, d | http://busplant.bogdan.ua | Crawled | Under Construction | MISMATCH | expected Crawled, crawler said Under Construction: no usable text found |
| T0181 | E-commerce and retail | https://www.bim.com.tr | Crawled | Under Construction | MISMATCH | expected Crawled, crawler said Under Construction: no usable text found |
| T0288 | Healthcare, education, finan | http://www.qbe.com/ | Crawled | Blocked | SITE-CHANGED | expected Crawled, crawler said Blocked: HTTP 403 from https://www.qbe.com/ |
| T0539 | JavaScript-heavy SPAs | http://www.atbank.at | Crawled | Under Construction | MISMATCH | expected Crawled, crawler said Under Construction: no usable text found |
| T0575 | Minimal / one-page / static  | http://www.allergan.com/ | Crawled | Blocked | SITE-CHANGED | expected Crawled, crawler said Blocked: HTTP 403 from https://www.allergan.com/ |
| T0620 | Dead domains (NXDOMAIN) | http://www.necotrans.com | Unreachable | Invalid | MISMATCH | expected Unreachable, crawler said Invalid: cannot resolve host 'necotrans.com' |
| T0622 | Dead domains (NXDOMAIN) | http://crawl-eval-dead-2.invalid/ | Unreachable | Invalid | MISMATCH | expected Unreachable, crawler said Invalid: cannot resolve host 'crawl-eval-dead-2.invalid' |
| T0628 | Dead domains (NXDOMAIN) | http://crawl-eval-dead-8.invalid/ | Unreachable | Invalid | MISMATCH | expected Unreachable, crawler said Invalid: cannot resolve host 'crawl-eval-dead-8.invalid' |
| T0637 | Parked / for-sale domains | http://www.energi-mp.com/ | Parked | Crawled | MISMATCH | expected 'Parked', which the crawler's status vocabulary cannot express (CR-B06); crawler said 'Crawled' (None) |
| T0644 | Parked / for-sale domains | http://www.dantek.dk/ | Parked | Crawled | MISMATCH | expected 'Parked', which the crawler's status vocabulary cannot express (CR-B06); crawler said 'Crawled' (None) |
| T0647 | Parked / for-sale domains | http://marine5-shimizuya.com/ | Parked | Crawled | MISMATCH | expected 'Parked', which the crawler's status vocabulary cannot express (CR-B06); crawler said 'Crawled' (None) |
| T0667 | Under construction / default | http://www.kingdom.com.sa/ | Under Construction | Crawled | SITE-CHANGED | expected Under Construction, crawler said Crawled:  |
| T0737 | HTTP errors | http://www.krupp-krankenhaus.de/en/home/ | Failed | Crawled | SITE-CHANGED | expected Failed, crawler said Crawled:  |
| T0769 | Redirect behaviour | http://www.pastel.co.za/ | Redirected | Crawled | MISMATCH | expected 'Redirected', which the crawler's status vocabulary cannot express (CR-B06); crawler said 'Crawled' (None) |
| T0805 | Bot-protected / WAF | http://www.firstmidwest.com/ | Blocked | Unreachable | SITE-CHANGED | expected Blocked, crawler said Unreachable: timeout fetching http://firstmidwest.com |
| T0834 | robots.txt | https://www.genealogicalinstitute.ca/ | Blocked | Crawled | MISMATCH | homepage was fetched (2 page requests) although robots.txt answers 5xx |
| T0901 | Input handling | http://94.140.14.14 | Redirected | import:added/crawl:Blocked | MISMATCH | import ok but crawl status Blocked, expected Redirected |
| T0958 | Thin / empty / error-only pa | http://www.psygroup.com | Requires Review | Under Construction | MISMATCH | expected 'Requires Review', which the crawler's status vocabulary cannot express (CR-B06); crawler said 'Under Construction' (no usable text |
| T0967 | Thin / empty / error-only pa | http://127.0.0.1:8826/ | Requires Review | Under Construction | MISMATCH | expected 'Requires Review', which the crawler's status vocabulary cannot express (CR-B06); crawler said 'Under Construction' (no usable text |
