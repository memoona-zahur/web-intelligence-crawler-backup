# Issue log – existing crawler (Phase 1)

Run `existing-code_full_20261011` · code `24818a60` (tag `crawler-baseline-v1`) · 30 defects: 4 Critical, 13 Major, 11 Minor, 2 Cosmetic · 1 design decision · 1 policy question.

Severity scale (phase-plan 1.6): Critical = security issue, data loss, batch-stopping crash or silently wrong results at scale; Major = a MUST requirement fails or a whole class of sites is mishandled; Minor = narrow case or a SHOULD fails; Cosmetic = naming, messages, documentation.
A design decision and a policy question are NOT counted as defects. No fix is implemented in Phase 1.

| ID | Severity | Type | Title | CR-IDs | Module | Leads | Status |
|---|---|---|---|---|---|---|---|
| ISS-01 | Critical | defect | Browser fallback follows redirects to addresses the SSRF guard never checked | CR-B10, CR-D06 | browser | L-04 | confirmed |
| ISS-02 | Critical | defect | Decompression bomb: memory is bounded only by what the server sends | CR-D09 | fetcher | L-17 | confirmed |
| ISS-03 | Critical | defect | SSRF guard lets 100.64.0.0/10 through (includes the Alibaba cloud metadata address 100.100.100.200) | CR-B09, CR-B10 | guard | new | confirmed |
| ISS-04 | Critical | defect | One malformed URL aborts the whole import (batch lost) | CR-A08, CR-G06, CR-A10 | importer | new | confirmed |
| ISS-05 | Major | defect | Text extraction deletes the whole page when a class name on <body>/<html> contains 'sidebar', 'cookie', 'popup', 'modal' or 'newsletter' | CR-E02, CR-E03, CR-D03 | extract | L-18 | confirmed |
| ISS-06 | Major | defect | Browser fallback reads the page too early and rarely helps | CR-D05, CR-D04 | browser | L-05 | confirmed |
| ISS-07 | Major | defect | Page ranking skips real business pages and cannot find non-English or non-standard ones | CR-C03, CR-C05, CR-C06, CR-C04, CR-C08 | discover | L-01, L-02 | confirmed |
| ISS-08 | Major | defect | Early stop at 12,000 characters / 8 pages ends the crawl before key pages | CR-C07, CR-E10 | pipeline | L-03 | confirmed |
| ISS-09 | Major | defect | Parked / for-sale domains are stored as 'crawled' | CR-B02 | quality/pipeline | L-07 | confirmed |
| ISS-10 | Major | defect | Placeholder, default-server, soft-404, thin and login pages are stored as crawled / empty | CR-B03, CR-D04 | quality/pipeline | L-07 | confirmed |
| ISS-11 | Major | defect | DNS failure is reported as 'invalid', not 'unreachable' | CR-B01, CR-B06 | guard/pipeline | new | confirmed |
| ISS-12 | Major | defect | Status vocabulary cannot express Redirected, Parked, Under Construction, Requires Review or Active | CR-B06 | config/profile | L-07, L-23 | confirmed |
| ISS-13 | Major | defect | Database cannot hold the crawl facts the requirements ask for | CR-D10, CR-H02, CR-H03, CR-H04, CR-H05, CR-E07, CR-E08, CR-D07, CR-F09, CR-A12 | models/profile | L-06 | confirmed |
| ISS-15 | Major | defect | Retry / back-off is linear with one retry; Retry-After and Crawl-delay are ignored | CR-F04, CR-F05, CR-F01 | fetcher | L-15 | confirmed |
| ISS-16 | Major | defect | No total time limit per request: a slow-drip server holds a worker for minutes | CR-D09, CR-F07 | fetcher | L-17 | confirmed |
| ISS-17 | Major | defect | Default web upload limit rejects a typical 60,000-URL list | CR-A11 | limits/main | L-10 | confirmed |
| ISS-22 | Major | defect | Domain health is recorded but never used; no domain-level back-off or scheduling | CR-F06, CR-F07, CR-F03 | profile/runner | L-16 | confirmed |
| ISS-14 | Minor | policy-question | robots.txt answering 5xx is treated as 'allowed' and no robots policy is written down | CR-F01 | fetcher | L-14 | confirmed |
| ISS-18 | Minor | defect | Normalisation misses some duplicate spellings and drops ports / paths | CR-A06, CR-B05 | normalize | new | confirmed |
| ISS-19 | Minor | defect | Import accepts inputs that are not valid or not public | CR-A08, CR-B09 | importer/guard | new | confirmed |
| ISS-20 | Minor | defect | Source / batch / record ID are never stored | CR-A07, CR-H04, CR-A01 | importer/main | L-09 | confirmed |
| ISS-21 | Minor | defect | .env settings are ignored by the crawler CLI and app.ops | CR-F03, CR-K03 | classifier/limits | L-12 | confirmed |
| ISS-23 | Minor | defect | Cancel takes effect only between finished sites; cancelled runs leave an un-awaited coroutine | CR-A13, CR-G05 | runner | L-21 | confirmed |
| ISS-24 | Minor | defect | Only 5 redirects are followed | CR-D02 | config/fetcher | L-23 | confirmed |
| ISS-25 | Minor | defect | Meta-refresh redirects are not followed | CR-D02, CR-D04 | pipeline | new | confirmed |
| ISS-26 | Minor | defect | Wrong charset header gives no text; legitimate pages over 2 MB fail | CR-D02 | extract/fetcher | new | confirmed |
| ISS-27 | Minor | defect | A failed re-crawl keeps the old text; there is no 'Partial' status | CR-B07, CR-B08, CR-E06 | profile | L-08 | confirmed |
| ISS-28 | Minor | defect | Canonical URL not used: case / slash / index.html duplicates are fetched more than once | CR-C09, CR-C10, CR-E04 | discover | L-19 | confirmed |
| ISS-29 | Minor | design-decision | Some sites block the crawler's honest User-Agent | CR-F02, CR-F05 | config | L-13 | design decision |
| ISS-31 | Minor | defect | No contact URL by default and two different bot names | CR-F02 | config | L-13 | confirmed |
| ISS-30 | Cosmetic | defect | README test figures are wrong (108 passed / 100% coverage) | CR-J04 | docs/tests | L-22 | confirmed |
| ISS-36 | Cosmetic | defect | Unhelpful error text for malformed hosts | CR-G05 | pipeline | new | confirmed |

## ISS-01 – Browser fallback follows redirects to addresses the SSRF guard never checked

* **Severity:** Critical · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-B10, CR-D06 · **Leads:** L-04
* **Code location:** `app/crawler/browser.py::render_page`
* **Repro:** http://127.0.0.1:8861/ (test page; extra_tests/t_browser_ssrf.py)
* **Expected:** Every address the browser visits is checked (like the HTTP path checks every hop).
* **Actual:** A JavaScript redirect sent Chromium to http://127.0.0.2:8810/secret; the page text 'SECRET-TOKEN-4711' was stored in clean_text (status crawled).
* **Evidence:** extra_tests/t_browser_ssrf.json: secret_token_in_stored_text = true; guard log shows one check (the first URL) only. HTTP path control: T0785, T0791 refused 127.0.0.2.
* **Suspected root cause:** assert_public_url(url) is called once before page.goto; page.goto follows redirects and loads sub-resources unchecked.
* **Fix direction (not implemented):** Route every browser request through the guard (page.route), re-check final URL, block private ranges inside the browser.

## ISS-02 – Decompression bomb: memory is bounded only by what the server sends

* **Severity:** Critical · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-D09 · **Leads:** L-17
* **Code location:** `app/crawler/fetcher.py::_one_attempt (size check after response.content)`
* **Repro:** http://127.0.0.1:8805/ (150 MB), http://127.0.0.1:8862/ (600 MB, test only)
* **Expected:** Response size and decompressed size are capped while reading (CR-D09).
* **Actual:** Page failed with 'larger than 2000000 bytes' only after the whole body was decompressed in memory.
* **Evidence:** t_bomb_150mb.json: +205 MB; t_bomb_600mb.json: +941 MB (peak 1,011 MB) in 1.4 s; 4x input = 4.6x memory. Memory returned after the run. Full run T0844: process RSS 152 -> 296 MB after one 150 MB bomb.
* **Suspected root cause:** httpx decodes Content-Encoding fully before len(response.content) is compared with MAX_BYTES_PER_PAGE; only a declared Content-Length rejects early.
* **Fix direction (not implemented):** Stream the response, stop at a byte cap on decoded bytes, cap decompression ratio.

## ISS-03 – SSRF guard lets 100.64.0.0/10 through (includes the Alibaba cloud metadata address 100.100.100.200)

* **Severity:** Critical · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-B09, CR-B10 · **Leads:** new
* **Code location:** `app/crawler/guard.py::_is_public, is_safe_import_target`
* **Repro:** http://100.100.100.200/latest/meta-data/ (T0920)
* **Expected:** Non-public targets are refused at import and at fetch.
* **Actual:** Import accepted it; the fetch-time guard said 'allowed'; the crawler tried https://, then http://.
* **Evidence:** requests.jsonl: 6 SAFETY_NET_BLOCKED events for 100.100.100.200 (requests the harness refused to send). Python: ip.is_private = False, ip.is_global = False for 100.100.100.200.
* **Suspected root cause:** _is_public tests is_private/loopback/link-local/multicast/reserved/unspecified but not 'not is_global' (shared address space 100.64/10 passes).
* **Fix direction (not implemented):** Use `ip.is_global` as the single rule and add explicit tests for 100.64.0.0/10.

## ISS-04 – One malformed URL aborts the whole import (batch lost)

* **Severity:** Critical · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-A08, CR-G06, CR-A10 · **Leads:** new
* **Code location:** `app/normalize.py::normalize_website -> urlparse (called from app/importer.py::import_urls)`
* **Repro:** http://[invalid (T0944)
* **Expected:** Bad lines are reported as invalid; the rest is imported.
* **Actual:** ValueError: Invalid IPv6 URL; nothing from the 988-row batch was imported.
* **Evidence:** run.log line 5: 'IMPORTER CRASH on row T0944 ... (batch of 988 rows lost)'. The harness had to remove the line and retry.
* **Suspected root cause:** No try/except around urlparse; one exception propagates out of the import loop and the transaction is rolled back.
* **Fix direction (not implemented):** Wrap per-line parsing, count the line as invalid, continue.

## ISS-05 – Text extraction deletes the whole page when a class name on <body>/<html> contains 'sidebar', 'cookie', 'popup', 'modal' or 'newsletter'

* **Severity:** Major · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-E02, CR-E03, CR-D03 · **Leads:** L-18
* **Code location:** `app/crawler/extract.py::_drop_noise, DROP_NAME_HINTS`
* **Repro:** https://www.dandelionstrategies.com/contact/, https://excelpr.com, https://millermartin.com/about/accolades, https://www.davidsa.com/ (T0003, T0035, T0057, T0077)
* **Expected:** Boilerplate removed, business text kept.
* **Actual:** Page had 877-8,474 visible characters; the crawler kept 0-76.
* **Evidence:** t_extraction_rootcause.json: in 11 of 14 sites one <body> or <html> whose class/id contains the hint holds 94-100% of the page text and is decomposed. analysis.json: 59 sites where visible text >= 500 but extracted < 80. Result: 44 sites 'empty'.
* **Suspected root cause:** Substring match of class/id on every element, including <body>/<html> and page wrappers (e.g. WordPress 'has-sidebar', 'cookie-notice-visible').
* **Fix direction (not implemented):** Apply hints only to small leaf-level containers or require a word match; never remove <html>/<body>/main wrappers; keep a fallback when result is tiny.

## ISS-06 – Browser fallback reads the page too early and rarely helps

* **Severity:** Major · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-D05, CR-D04 · **Leads:** L-05
* **Code location:** `app/crawler/browser.py::render_page (wait_until='domcontentloaded', then content())`
* **Repro:** https://atbank.de (T0529), https://digitalleague.ru (T0532), https://mysteriousbookshop.com (T0528), https://picoxr.com (T0523)
* **Expected:** JavaScript sites yield their rendered text.
* **Actual:** 248 successful renders: only 53 gave more text than HTTP; 36 renders returned nothing.
* **Evidence:** t_extraction_rootcause.json part B: after network idle the crawler's own extraction gives 61,543 / 2,559 / 1,587 / 148 characters instead of 0 / 0 / 14 / 0.
* **Suspected root cause:** The HTML is captured immediately after DOMContentLoaded, before client-side rendering finishes.
* **Fix direction (not implemented):** Wait for network idle or a content selector with a timeout; record the wait.

## ISS-07 – Page ranking skips real business pages and cannot find non-English or non-standard ones

* **Severity:** Major · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-C03, CR-C05, CR-C06, CR-C04, CR-C08 · **Leads:** L-01, L-02
* **Code location:** `app/crawler/discover.py::_score, SKIP, HIGH_VALUE`
* **Repro:** e.g. /services/accounting, /products/compressors, /research, /leistungen, /ueber-uns, /who-we-serve (T0850)
* **Expected:** Gold key pages (About / Services / Products / Industries) are found.
* **Actual:** Gold-set recall 33.5% (133/397); Services 27%, Products 18%, Industries 5%, About 61%.
* **Evidence:** analysis.json gold_set: 120 gold pages never requested because the score was 0. t_score.json: 28 of 36 genuine business paths score 0 (12 English with skip-substrings 'press', 'account', 'legal', 'search', 'cart', 'admin', 'tag'; 16 non-English).
* **Suspected root cause:** Substring skip-words run before the priority words; ranking uses URL path and anchor text in English only.
* **Fix direction (not implemented):** Whole-word skip rules, multilingual keyword lists, use page titles/headings/nav structure, order candidates by preference not alphabet.

## ISS-08 – Early stop at 12,000 characters / 8 pages ends the crawl before key pages

* **Severity:** Major · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-C07, CR-E10 · **Leads:** L-03
* **Code location:** `app/crawler/pipeline.py::crawl_one; app/crawler/config.py::SUFFICIENT_TEXT_CHARS, MAX_PAGES`
* **Repro:** large enterprise sites (see analysis.json gold_set.examples)
* **Expected:** Stop early only when evidence is sufficient; record what was skipped.
* **Actual:** 89 gold pages were never requested because the page cap or the text threshold had been reached; 194 of 530 crawled happy-path sites reached 12,000 characters.
* **Evidence:** analysis.json gold_set.why_missing and text.
* **Suspected root cause:** Sufficiency is measured in characters of whatever the homepage gave, not in which page types were seen.
* **Fix direction (not implemented):** Stop on page-type coverage (About + Services/Products + Industries) rather than on length.

## ISS-09 – Parked / for-sale domains are stored as 'crawled'

* **Severity:** Major · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-B02 · **Leads:** L-07
* **Code location:** `app/crawler/quality.py (no parked detection)`
* **Repro:** http://www.energi-mp.com/, http://www.dantek.dk/, http://marine5-shimizuya.com/ (T0637, T0644, T0647)
* **Expected:** Parked
* **Actual:** crawled, with the parking page text as 'company text'.
* **Evidence:** 0 of 30 judged parked rows MATCH (29 MISMATCH).
* **Suspected root cause:** No detection exists; HugeDomains / Afternic / parking-NS pages have enough text to pass the 80-character test.
* **Fix direction (not implemented):** Detect parking wording, parking-provider names and NS records; add a Parked status.

## ISS-10 – Placeholder, default-server, soft-404, thin and login pages are stored as crawled / empty

* **Severity:** Major · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-B03, CR-D04 · **Leads:** L-07
* **Code location:** `app/crawler/quality.py::page_is_useful; pipeline.py (MIN_TEXT_CHARS)`
* **Repro:** T0669 (nginx welcome), T0675, T0676, T0852-T0855 (password walls), T0967 (soft-404)
* **Expected:** Under Construction / Requires Review
* **Actual:** crawled (nginx welcome page, 'Coming soon', password-protected stores) or empty (login form, soft-404).
* **Evidence:** Under-construction rows: 5 of 13 judged MATCH; thin rows: 2 of 12; login rows: 2 of 7.
* **Suspected root cause:** Only length and script-shell words are examined.
* **Fix direction (not implemented):** Detect default-page and 'coming soon' wording, soft-404 titles, password forms.

## ISS-11 – DNS failure is reported as 'invalid', not 'unreachable'

* **Severity:** Major · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-B01, CR-B06 · **Leads:** new
* **Code location:** `app/crawler/guard.py::assert_public_url (GuardError for gaierror) -> pipeline.py::crawl_one (STATUS_INVALID)`
* **Repro:** http://crawl-eval-dead-2.invalid/ (T0622), http://www.necotrans.com (T0620)
* **Expected:** Unreachable (domain does not resolve)
* **Actual:** invalid ('cannot resolve host ...')
* **Evidence:** 26 of 30 dead-domain rows ended 'invalid'; same cause in 5 'timeout/refused' rows (T0681, T0683, T0688, T0692, T0694).
* **Suspected root cause:** A DNS error is raised as GuardError, and every GuardError means 'invalid'.
* **Fix direction (not implemented):** Separate 'unsafe target' from 'does not resolve'.

## ISS-12 – Status vocabulary cannot express Redirected, Parked, Under Construction, Requires Review or Active

* **Severity:** Major · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-B06 · **Leads:** L-07, L-23
* **Code location:** `app/crawler/config.py STATUS_*`
* **Repro:** 7 real cross-domain redirect rows (T0763-T0770), 3 httpbin redirects (T0778-T0780), password walls (T0852-T0855)
* **Expected:** Requirement vocabulary (CR-B06).
* **Actual:** Cross-domain redirects end 'crawled'; nothing records that the site redirected.
* **Evidence:** 59 rows judged MISMATCH only because of the missing word.
* **Suspected root cause:** Nine fixed status strings.
* **Fix direction (not implemented):** Add the states and store the final URL.

## ISS-13 – Database cannot hold the crawl facts the requirements ask for

* **Severity:** Major · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-D10, CR-H02, CR-H03, CR-H04, CR-H05, CR-E07, CR-E08, CR-D07, CR-F09, CR-A12 · **Leads:** L-06
* **Code location:** `app/models.py::Website; app/profile.py::apply_crawl_result`
* **Repro:** inspect the websites table after any run
* **Expected:** Final URL, HTTP status, pages attempted, per-page rows, fetch attempts, error/retry history, raw content store.
* **Actual:** Only status, crawl_error, pages_crawled, last_crawled_at, content_hash, clean_text.
* **Evidence:** analysis.json database_fields: no final-url, http-status, pages-attempted or retry column; tables = jobs, websites, evidence_records, domain_stats.
* **Suspected root cause:** Crawl results are flattened into one row; CrawlResult.final_url is computed and dropped.
* **Fix direction (not implemented):** Add page / attempt / error tables and migrations.

## ISS-15 – Retry / back-off is linear with one retry; Retry-After and Crawl-delay are ignored

* **Severity:** Major · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-F04, CR-F05, CR-F01 · **Leads:** L-15
* **Code location:** `app/crawler/fetcher.py::fetch_page; app/crawler/config.py (RETRIES=1, RETRY_BACKOFF=1.5, DOMAIN_DELAY=0.2)`
* **Repro:** http://127.0.0.1:8825/ (T0749), http://127.0.0.1:8820/ (T0820), https://www.guardianangeldevices.com (T0387)
* **Expected:** Exponential back-off; honour Retry-After and Crawl-delay.
* **Actual:** 503 with Retry-After: 3600 was re-requested after 0.05-1.6 s; Crawl-delay: 10 ignored (pages 0.3 s apart).
* **Evidence:** analysis.json politeness; results.csv checks 'honours Retry-After 5s' = FAIL, 'gap>=9.5 s' = FAIL.
* **Suspected root cause:** Constants; response headers are not read.
* **Fix direction (not implemented):** Read Retry-After / Crawl-delay; exponential back-off with jitter; per-domain slow-down.

## ISS-16 – No total time limit per request: a slow-drip server holds a worker for minutes

* **Severity:** Major · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-D09, CR-F07 · **Leads:** L-17
* **Code location:** `app/crawler/fetcher.py::_one_attempt (httpx per-read timeout only)`
* **Repro:** http://127.0.0.1:8801/ (T0698), http://127.0.0.1:8804/ (T0843), https://httpbin.org/drip?duration=30 (T0697)
* **Expected:** Bounded total time per page.
* **Actual:** Slow-drip page: 265 s for one site (2 attempts); 60 MB body: 27.5 s; 30 s drip was read to the end (29 s).
* **Evidence:** heavy_memory.json seconds; results.csv.
* **Suspected root cause:** httpx timeouts apply to each read, not to the whole response.
* **Fix direction (not implemented):** Add an overall deadline per request and per site.

## ISS-17 – Default web upload limit rejects a typical 60,000-URL list

* **Severity:** Major · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-A11 · **Leads:** L-10
* **Code location:** `app/limits.py::max_import_chars (2,000,000); app/main.py::import_list`
* **Repro:** 60,000 lines (extra_tests/t_import_60k.py)
* **Expected:** Ingest 60,000+ records without manual batching.
* **Actual:** POST /import redirected to ?notice=upload for 2.10 MB (domain-only) and 2.61 MB (with paths) lists.
* **Evidence:** t_import_60k.json: ~57,145 domain-only or ~46,049 with-path lines fit; the importer function itself took 49.9 s for 60,000.
* **Suspected root cause:** Fixed default limit; configurable via MAX_IMPORT_CHARS.
* **Fix direction (not implemented):** Raise the default or stream the upload.

## ISS-22 – Domain health is recorded but never used; no domain-level back-off or scheduling

* **Severity:** Major · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-F06, CR-F07, CR-F03 · **Leads:** L-16
* **Code location:** `app/profile.py::record_domain (write only); app/crawler/runner.py`
* **Repro:** static check + analysis.json
* **Expected:** Slow down or skip failing domains.
* **Actual:** 758 domain_stats rows written, none read; 562 of 673 multi-page sites had two requests < 1 s apart.
* **Evidence:** grep: DomainStat is only written (profile.py:92-111).
* **Suspected root cause:** No reader.
* **Fix direction (not implemented):** Use the stats to back off and to schedule per domain.

## ISS-14 – robots.txt answering 5xx is treated as 'allowed' and no robots policy is written down

* **Severity:** Minor · **Type:** policy-question · **Status:** confirmed
* **Requirements:** CR-F01 · **Leads:** L-14
* **Code location:** `app/crawler/fetcher.py::load_robots`
* **Repro:** https://oakpont.com, https://www.genealogicalinstitute.ca/, https://www.synnexcorp.com/, https://ciina-ciina.com/marudai-niigata/ (T0833-T0836), http://127.0.0.1:8822/
* **Expected:** Decided by policy. RFC 9309 s2.3.1.4 says treat persistent 5xx as 'disallow'; 404/401/403 mean 'no rules'.
* **Actual:** Fail-open on every error: 5 of 5 5xx rows crawled the homepage.
* **Evidence:** results.csv rows T0822, T0833-T0836; robots 4xx rows behaved per RFC (crawled).
* **Suspected root cause:** `rules.missing = True` for all errors.
* **Fix direction (not implemented):** Write the policy (for the project owner), then implement it; retry 5xx before deciding.

## ISS-18 – Normalisation misses some duplicate spellings and drops ports / paths

* **Severity:** Minor · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-A06, CR-B05 · **Leads:** new
* **Code location:** `app/normalize.py::normalize_website`
* **Repro:** https://example.com. (T0887), xn--mnchen-3ya.de (T0898), //example.com (T0889), full-width (T0890)
* **Expected:** Duplicates detected.
* **Actual:** Trailing dot and punycode form added as new sites; scheme-relative and full-width inputs rejected.
* **Evidence:** 4 of 23 duplicate rows MISMATCH.
* **Suspected root cause:** No IDNA / trailing-dot / scheme-relative handling; always rewrites to https://host (so a site on another port cannot be represented).
* **Fix direction (not implemented):** Normalise via IDNA, strip trailing dot, accept '//host'.

## ISS-19 – Import accepts inputs that are not valid or not public

* **Severity:** Minor · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-A08, CR-B09 · **Leads:** new
* **Code location:** `app/crawler/guard.py::is_safe_import_target; app/normalize.py`
* **Repro:** T0908, T0911, T0920, T0924, T0925, T0934, T0935, T0937, T0939, T0940, T0943, T0944, T0945, T0946
* **Expected:** Invalid at import.
* **Actual:** Added (then 'invalid' or 'failed' at fetch) or merged as a duplicate of another site (ftp://example.com, mailto:info@example.com).
* **Evidence:** 14 of 47 rows.
* **Suspected root cause:** Scheme and syntax are not validated; the scheme is discarded.
* **Fix direction (not implemented):** Validate scheme, label lengths, port range and name syntax before normalising.

## ISS-20 – Source / batch / record ID are never stored

* **Severity:** Minor · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-A07, CR-H04, CR-A01 · **Leads:** L-09
* **Code location:** `app/main.py::import_list (line 237 calls import_urls without a batch)`
* **Repro:** any import
* **Expected:** Source file / batch / record ID kept.
* **Actual:** source_batch is empty on every row; no ID column.
* **Evidence:** analysis.json database_fields.source_batch_non_null_rows = 0.
* **Suspected root cause:** Parameter exists but is never passed.
* **Fix direction (not implemented):** Pass file name; add source_record_id.

## ISS-21 – .env settings are ignored by the crawler CLI and app.ops

* **Severity:** Minor · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-F03, CR-K03 · **Leads:** L-12
* **Code location:** `app/classifier.py (load_dotenv at import)`
* **Repro:** extra_tests/t_env_copy.py
* **Expected:** Configuration from .env applies to the crawler.
* **Actual:** CRAWL_CONCURRENCY=3 and a contact URL in .env had no effect until app.classifier was imported.
* **Evidence:** t_env_copy.json: 10 / default User-Agent after importing crawler_cli and ops; 3 / custom User-Agent only after importing classifier.
* **Suspected root cause:** load_dotenv is called only in classifier.py.
* **Fix direction (not implemented):** Load .env in one shared config module.

## ISS-23 – Cancel takes effect only between finished sites; cancelled runs leave an un-awaited coroutine

* **Severity:** Minor · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-A13, CR-G05 · **Leads:** L-21
* **Code location:** `app/crawler/runner.py::_run_inside (as_completed loop)`
* **Repro:** extra_tests/t_cancel_recover.py
* **Expected:** Prompt, clean cancel.
* **Actual:** Cancel at 5 s took 20.9 s to return (sites answer after 20 s); RuntimeWarning: coroutine '_AsCompletedIterator._wait_for_one' was never awaited.
* **Evidence:** t_cancel_recover.json; console warning at runner.py:151.
* **Suspected root cause:** Cancellation flag is read only after a task completes.
* **Fix direction (not implemented):** Cancel tasks as soon as the flag is set; await them.

## ISS-24 – Only 5 redirects are followed

* **Severity:** Minor · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-D02 · **Leads:** L-23
* **Code location:** `app/crawler/config.py::MAX_REDIRECTS`
* **Repro:** T0783 (7 hops), T0787 (9 hops)
* **Expected:** Chains up to 10 hops followed.
* **Actual:** Failed: more than 5 redirects.
* **Evidence:** results.csv.
* **Suspected root cause:** Constant 5.
* **Fix direction (not implemented):** Raise to 10-20.

## ISS-25 – Meta-refresh redirects are not followed

* **Severity:** Minor · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-D02, CR-D04 · **Leads:** new
* **Code location:** `app/crawler/pipeline.py::crawl_one`
* **Repro:** http://www.realschule-kreuztal.de/, https://glambecksee.de, http://127.0.0.1:8837/ (T0774, T0775, T0788)
* **Expected:** Content of the target page.
* **Actual:** Stub text (124-173 characters) or 'empty'.
* **Evidence:** oracle_rule MISMATCH on 3 rows.
* **Suspected root cause:** Only HTTP redirects are followed; the browser fallback is not used for stubs that are not script shells.
* **Fix direction (not implemented):** Parse <meta http-equiv=refresh>.

## ISS-26 – Wrong charset header gives no text; legitimate pages over 2 MB fail

* **Severity:** Minor · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-D02 · **Leads:** new
* **Code location:** `app/crawler/extract.py::extract_page; fetcher.py::MAX_BYTES_PER_PAGE`
* **Repro:** http://127.0.0.1:8834/ (T0871), http://www.nlc.com.pk (T0868)
* **Expected:** Readable text.
* **Actual:** Shift_JIS page declared UTF-8: 0 characters (empty); 2 MB limit on a real site.
* **Evidence:** results.csv.
* **Suspected root cause:** Bytes handed to the parser without charset detection; fixed byte limit.
* **Fix direction (not implemented):** Detect charset from content; allow bigger pages with streaming cap.

## ISS-27 – A failed re-crawl keeps the old text; there is no 'Partial' status

* **Severity:** Minor · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-B07, CR-B08, CR-E06 · **Leads:** L-08
* **Code location:** `app/profile.py::apply_crawl_result`
* **Repro:** extra_tests/t_recrawl.py
* **Expected:** Current failure clearly separated from old evidence.
* **Actual:** status 'failed' while clean_text (1,115 chars) and hash stay from the old crawl.
* **Evidence:** t_recrawl.json.
* **Suspected root cause:** clean_text only overwritten when new text exists.
* **Fix direction (not implemented):** Version the content or flag it as stale.

## ISS-28 – Canonical URL not used: case / slash / index.html duplicates are fetched more than once

* **Severity:** Minor · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-C09, CR-C10, CR-E04 · **Leads:** L-19
* **Code location:** `app/crawler/discover.py::_normalize`
* **Repro:** http://127.0.0.1:8856/ (T0984)
* **Expected:** /About, /about/, /ABOUT/, /about/index.html fetched once.
* **Actual:** More than one variant of /about and /services fetched.
* **Evidence:** results.csv checks '/about variants fetched<=1' = FAIL.
* **Suspected root cause:** Only host, slash, query and fragment are normalised; rel=canonical ignored.
* **Fix direction (not implemented):** Lower-case paths where safe, strip index files, honour rel=canonical.

## ISS-29 – Some sites block the crawler's honest User-Agent

* **Severity:** Minor · **Type:** design-decision · **Status:** design decision
* **Requirements:** CR-F02, CR-F05 · **Leads:** L-13
* **Code location:** `app/crawler/config.py::user_agent`
* **Repro:** https://www.gemcar.com, https://matthewsaurora.com and 9 more (extra_tests/t_ua_blocked.json)
* **Expected:** Honest, descriptive User-Agent; no bypass of anti-bot protection (requirements).
* **Actual:** 11 of 21 'blocked' happy-path sites answer 200 to another User-Agent; 10 refuse every bot.
* **Evidence:** t_ua_blocked.json.
* **Suspected root cause:** The requirements demand an honest User-Agent and forbid bypassing protection, so this is NOT a defect; the loss is a known cost. A real contact URL (CR-F02) may reduce it.
* **Fix direction (not implemented):** None to bypass. Publish a crawler policy page and add a contact URL; decide as a policy matter.

## ISS-31 – No contact URL by default and two different bot names

* **Severity:** Minor · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-F02 · **Leads:** L-13
* **Code location:** `app/crawler/config.py::user_agent`
* **Repro:** extra_tests/t_env_copy.py
* **Expected:** One descriptive name with a real contact / policy URL.
* **Actual:** 'WebIntelligenceCrawler/1.0 (+internal research)' by default; 'WebsiteIntelligenceBot/1.0 (+url)' once a contact URL is set.
* **Evidence:** t_env_copy.json.
* **Suspected root cause:** Two strings.
* **Fix direction (not implemented):** One name; make the contact URL mandatory in production.

## ISS-30 – README test figures are wrong (108 passed / 100% coverage)

* **Severity:** Cosmetic · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-J04 · **Leads:** L-22
* **Code location:** `README.md`
* **Repro:** pytest --cov=app.crawler
* **Expected:** Real figures.
* **Actual:** 154 passed; crawler coverage 91%; ~150 ResourceWarnings ('unclosed database').
* **Evidence:** crawl_eval/baseline/baseline_summary.md.
* **Suspected root cause:** Out of date.
* **Fix direction (not implemented):** Update; close SQLite connections in tests.

## ISS-36 – Unhelpful error text for malformed hosts

* **Severity:** Cosmetic · **Type:** defect · **Status:** confirmed
* **Requirements:** CR-G05 · **Leads:** new
* **Code location:** `app/crawler/pipeline.py (catch-all 'unexpected error')`
* **Repro:** http://example..com (T0940), 64-character label (T0945)
* **Expected:** 'invalid host name'.
* **Actual:** 'unexpected error: 'idna' codec can't encode character ...'.
* **Evidence:** results.csv.
* **Suspected root cause:** Exception text passed through.
* **Fix direction (not implemented):** Validate the host first.
