# Phase 1 result in plain English – existing crawler, unchanged

**Verdict: NOT READY.** Four Critical problems, only 48.7% of the MUST requirements covered, and the crawler finds only 34% of the key pages (About / Services / Products / Industries) on the sites tested.

## What was tested
* 988 URLs (600 normal sites, 388 difficult cases) checked against the requirements. 804 real sites, 123 public test endpoints, 61 local scenarios. Crawled once, at concurrency 5 (the code's own default is 10); rows that did not match got one extra independent check.
* The code was not changed (56 files, SHA-256 checked before and after). Extra tests: 60,000-URL import, 1,000-site scale test, cancel and crash recovery, decompression bombs, browser redirect, `.env` handling.

## The numbers (this run only)
| Measure | Result |
|---|---|
| Rows where the crawler did what the requirements say | 752 of 988 (81.4% of the 924 rows that can be judged against the crawler) |
| Normal sites | 93.8% match (565 judged); 530 of 600 crawled, 498 with at least 500 characters of text |
| Difficult cases (errors, edge cases, traps, bad input) | 61.8% match (359 judged) |
| Rows not counted against the crawler | 27 ENV-DEPENDENT (my network / ISP DNS), 36 SITE-CHANGED, 1 ORACLE-LIMITATION |
| Requirement coverage | 48.0% (weighted), 48.7% MUST-only; 12.7% of MUST requirements fully PASS |
| Key pages found (gold set, 156 sites) | 133 of 397 = 33.5% |
| Time per site | median 7.44 s, 95th percentile 55.96 s |

## What works well
* Plain sites: most normal websites are crawled correctly, never more than 8 pages, homepage first, junk pages avoided.
* Safe by default: private addresses in redirects are refused on the HTTP path; blocked sites, HTTP errors, TLS errors and robots.txt "disallow all" are handled; crawl traps did not trap it (19 of 20).
* Reliability: no failing website stopped the crawl; a killed run recovered with 0 rows lost; memory stayed small (297 MB peak in the full run).

## The most serious problems
1. **Browser fallback can be sent to internal addresses** (Critical): a JavaScript redirect to 127.0.0.2 was followed and the internal page was stored.
2. **A decompression bomb can exhaust memory** (Critical): +205 MB for 150 MB, +941 MB for 600 MB, no cap.
3. **The safety check misses 100.64.0.0/10**, which includes a cloud metadata address (Critical).
4. **One malformed URL crashes the whole import** (Critical).
5. **Text extraction deletes whole pages**: 59 sites where the page had text but the crawler kept almost none, because a CSS class like "sidebar" or "cookie" sits on the page body.
6. **Key pages are missed**: ranking gives score 0 to 28 of 36 real business paths; non-English paths are not understood.
7. **Parked, placeholder and login pages are saved as normal results**; DNS failure is reported as "invalid"; the status list lacks Parked / Redirected / Under Construction.

## Not counted as bugs
* **User-Agent blocked** (11 of 21 blocked happy-path sites accept another User-Agent): a design decision, because the requirements demand an honest User-Agent and forbid bypassing protection.
* **robots.txt answering 5xx is treated as allowed**: a policy question for the project owner (the RFC says to treat it as disallow).
* **T0901**: ORACLE-LIMITATION (the dataset verified `http://`, the importer always uses `https://`).

## Limits of this test
* Wikidata favours large and old organisations; "small local business" rows are site-builder sites of limited size, not proven small or local.
* Tested from Lahore: 27 rows are ENV-DEPENDENT and some SITE-CHANGED rows may also be geo-blocking or rate limits.
* One run on one day; sites change. Not a statistical sample, and nothing here is a forecast for 60,000 sites.
* **Close-out check of the labels (two rounds):** every one of the 72 rows labelled SITE-CHANGED or ENV-DEPENDENT (69 at the end of the run, plus 3 moved by a rule refinement) got one fresh independent probe; evidence in `label_review.csv`. The label holds for 57 rows and not for 15. Counts before round 2: {'MATCH': 752, 'MISMATCH': 164, 'ENV-DEPENDENT': 29, 'SITE-CHANGED': 39, 'PARTIAL': 3, 'ORACLE-LIMITATION': 1}; after: {'MATCH': 752, 'MISMATCH': 169, 'ENV-DEPENDENT': 27, 'SITE-CHANGED': 36, 'PARTIAL': 3, 'ORACLE-LIMITATION': 1}. Reclassified: T0118 to MISMATCH, T0133 to MISMATCH, T0288 to MISMATCH, T0304 to MISMATCH, T0437 to MISMATCH, T0454 to SITE-CHANGED, T0456 to SITE-CHANGED, T0494 to SITE-CHANGED, T0507 to MISMATCH, T0575 to MISMATCH, T0722 to ENV-DEPENDENT, T0731 to ENV-DEPENDENT, T0777 to MISMATCH, T0805 to ENV-DEPENDENT, T0899 to MISMATCH. Sites that alternate between 403 and 200 (T0118, T0575) cannot be called "changed"; a few DNS answers were inconsistent between checks.
* The Chromium child process memory was not measured. Excel upload, the web paste box and 200-status challenge pages were not tested.
