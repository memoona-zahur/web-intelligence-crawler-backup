# Verdict on every lead in docs/known-findings.md (Part 1)

Leads were hypotheses. Each one below was tested by running something.

| Lead | Verdict | Evidence | Issue |
|---|---|---|---|
| L-01 | CONFIRMED | 28 of 36 genuine business paths score 0 (12 English: /services/accounting, /products/compressors, /research ...). 120 gold pages never requested for this reason. | ISS-07 |
| L-02 | CONFIRMED | Ranking uses path + anchor text only: 16 of 17 non-English paths score 0; /who-we-serve not recognised (T0850). | ISS-07 |
| L-03 | CONFIRMED | 89 gold pages missed because of the page cap / 12,000-character stop; 194 of 530 sites reached the threshold. | ISS-08 |
| L-04 | CONFIRMED | Browser followed a JavaScript redirect to 127.0.0.2 and the internal page was stored. A new Chromium is launched for each of the 284 renders. | ISS-01 |
| L-05 | CONFIRMED (partly) | Render is read at DOMContentLoaded: only 53 of 248 renders gave more text. The narrow trigger condition (short AND shell-like) was not isolated separately. | ISS-06 |
| L-06 | CONFIRMED | No final URL, HTTP status, pages-attempted, retry or per-page storage (database_fields). | ISS-13 |
| L-07 | CONFIRMED | Parked 0 of 30 recognised; placeholders / soft-404 / login pages stored as crawled or empty; no Redirected / Under Construction / Requires Review status. | ISS-09, ISS-10, ISS-12 |
| L-08 | CONFIRMED (partly) | After a failed re-crawl status = 'failed' but the old clean_text and hash remain (t_recrawl). Both status columns agreed in the test; the claim that the runner claims on the legacy column was not isolated. | ISS-27 |
| L-09 | CONFIRMED | source_batch is empty on every row; main.py:237 calls import_urls without a batch. | ISS-20 |
| L-10 | CONFIRMED (default setting) | Web upload refuses 60,000-line lists (2.10-2.61 MB vs 2,000,000 characters). The importer function itself handles them (49.9 s). | ISS-17 |
| L-11 | CONFIRMED | The import job stays 'queued'; crawl jobs go running -> completed; lifecycle states differ from CR-A13; recovery covers crawl/classify jobs only (static). | ISS-13 |
| L-12 | CONFIRMED | A .env value is ignored by crawler_cli / ops until app.classifier is imported (t_env_copy). | ISS-21 |
| L-13 | CONFIRMED | Two bot names; no contact URL by default (t_env_copy). The blocked-by-User-Agent effect is a design decision. | ISS-29, ISS-31 |
| L-14 | CONFIRMED | robots.txt 5xx = allow (5 of 5 rows); 404/401/403 also allow (consistent with RFC 9309 for 4xx). No policy written. Policy question for the project owner. | ISS-14 |
| L-15 | CONFIRMED | Linear 1.5 s back-off, one retry, Retry-After ignored (T0387, T0749). | ISS-15 |
| L-16 | CONFIRMED | domain_stats is written (758 rows) and never read (static). | ISS-22 |
| L-17 | CONFIRMED (pages) / NOT DEMONSTRATED (sitemaps) | Whole body decompressed before the size check (+205 / +941 MB); slow-drip 265 s. The gzip sitemap bomb (T0846) and entity-expansion sitemap (T0847) were handled in under 4 s; their memory effect was not separable from the page-bomb run. | ISS-02, ISS-16 |
| L-18 | CONFIRMED | Whole bodies deleted by class-name hints (11 of 14 sites; 59 sites in the run). Tables / h4-h6 / div text lost (static + unit evidence). | ISS-05 |
| L-19 | CONFIRMED | Structured lines are appended as plain text; canonical is not used for dedupe (T0984); only 1 identical-content group in the run, so near-duplicate handling was not stressed on real sites. | ISS-28 |
| L-20 | CONFIRMED (design); no failure at this size | 1,000 sites in one call created 992 asyncio tasks and marked 990 rows 'crawling' at once; peak memory 88 MB (local test sites only, concurrency 5). Nothing is extrapolated to 60,000. | ISS-13 |
| L-21 | CONFIRMED | Cancel took 20.9 s to return; cancelled run leaves an un-awaited coroutine warning. | ISS-23 |
| L-22 | CONFIRMED | 154 tests passed (README: 108); crawler coverage 91% (README: 100%). | ISS-30 |
| L-23 | CONFIRMED | https first, http only after a network error; 7 of 7 real cross-domain redirect rows ended 'crawled' with no Redirected status and no stored final URL. | ISS-12 |
