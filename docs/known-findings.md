# Known Findings — leads from a manual code review

Source: a line-by-line reading of all 63 files in the repository zip (`Web-intelliegence-main`) by Claude
in the chat interface. **Nothing was run** (no dependencies and no network in that environment), except two
offline checks marked ✔ below. `pytest` was not executed.

**How to use this file**
- Every item is a **hypothesis**. Confirm it with evidence, refute it, or mark it "not testable".
  Say which in the issue log and in the report.
- Do **not** design the URL dataset around these items. Build the dataset from the requirements
  (`docs/phase-plan.md` §1.3), then see whether these leads show up. Also look for problems not listed here.
- Part 1 is for Phases 1–2 (crawling). Part 2 is for Phase 3 only; ignore it until then.

---

## Part 1 — Crawler leads (Phases 1 and 2)

| Lead | What was seen in the code | Where | How to verify | CR-IDs |
|---|---|---|---|---|
| L-01 ✔ | **Page ranking can score real business pages 0.** The skip-word check uses substring matching and runs before the priority-word check. Running the real `_score` offline gave 0 for `/services/accounting` ("account"), `/services/legal-advice` ("legal"), `/research` ("search"), `/products/compressors` ("press"), `/express-delivery` ("press"), `/products/cartridges` ("cart"), `/services/administration` ("admin"); `/services` and `/about` scored 3 | `app/crawler/discover.py::_score`, `SKIP` | Gold-set sites whose key pages contain these words: were they crawled? | C03, C05, C06 |
| L-02 | Ranking uses only URL path and anchor text — not page titles, headings or navigation structure | `discover.py::_score`, `discover_pages` | Gold set with non-standard paths (e.g. `/what-we-do`, `/en/solutions`, non-English paths) | C05 |
| L-03 | Early stop at 12,000 characters of cleaned text (`SUFFICIENT_TEXT_CHARS`) and 8-page cap may end the crawl before Products/Services/Industries pages are fetched if the homepage is long | `config.py`, `pipeline.py::crawl_one` | Compare pages crawled vs. gold-set key pages on large enterprise sites | C07 |
| L-04 | **Browser fallback validates only the first URL.** `render_page` calls `assert_public_url(url)` once, then `page.goto` follows redirects and loads sub-resources unchecked (HTTP path validates every hop; browser path does not). Also launches a new browser per render and blocks only image/media/font | `app/crawler/browser.py::render_page` | Scenario server: JS-shell page that redirects to a private address | B10, D05, D06 |
| L-05 | Fallback is triggered only when text is short **and** shell-like (`looks_like_shell`); heavy SPAs that render some text may never use the browser. Chromium is not installed by default | `quality.py`, `pipeline.py::_maybe_render` | JS-heavy SPA category: compare HTTP text vs. rendered text | D04, D05 |
| L-06 | Final URL and HTTP status are captured in `CrawlResult.final_url` but not stored on the website row; no per-page table; no pages-attempted count; no per-fetch attempt/error history | `pipeline.py::CrawlResult`, `profile.py::apply_crawl_result`, `models.py` | Inspect DB after the run | D10, H02, H04, H05 |
| L-07 | Status vocabulary differs from the requirement: no Parked, Under Construction, Redirected, Active, Requires Review; parked/for-sale or default-server pages may be stored as `crawled` with junk text; soft-404s likely the same | `config.py` STATUS_*, `quality.py` | Parked / under-construction / soft-404 categories | B02, B03, B06 |
| L-08 | Separate `crawl_status` and `classification_status` columns exist, but the legacy combined `status` is still what the runner claims on and the UI filters on; after a failed re-crawl the combined status can show the failure while old `clean_text` is retained | `profile.py::apply_crawl_result`, `runner.py::_claim` | Re-crawl a site that now fails; inspect both columns | B07, B08 |
| L-09 | Source tracking is never populated: `import_urls(..., source_batch)` exists but the web layer calls it without a batch; no source record ID | `app/main.py` (~line 237), `importer.py::import_urls` | Import a CSV with an ID column and a file name | A07 |
| L-10 | Import size limit: `MAX_IMPORT_CHARS` default 2,000,000 characters; a 60,000-URL list is roughly 1.8–2.5 MB of text | `app/limits.py` | Generate a synthetic 60,000-URL file (import only — do **not** crawl it) | A11 |
| L-11 | Import creates a job that stays `queued`; lifecycle states differ from the required set; `recover` handles only crawl/classify jobs | `importer.py`, `runner.py`, `recovery.py` | Inspect `jobs` table after imports and runs | A12, A13 |
| L-12 | `.env` is loaded only when `app/classifier.py` is imported (`load_dotenv`); the crawler CLI and `app.ops` do not import it, so `.env` values may be ignored there | `classifier.py`, `crawler_cli.py`, `limits.py` | Set a value in `.env` only, run the CLI, check effect | F03, K03 |
| L-13 | Two different bot names: default `WebIntelligenceCrawler/1.0 (+internal research)`; with a contact URL `WebsiteIntelligenceBot/1.0 (+…)`. No contact URL by default. Robots matching depends on the name | `config.py::user_agent` | Log the User-Agent actually sent; test a robots.txt that targets each name | F01, F02 |
| L-14 | robots.txt is fail-open: errors/unavailable robots = allow everything; no documented policy; 401/403/5xx on robots.txt handled the same way as "missing" | `fetcher.py::load_robots` | robots category (5xx, 403, malformed, timeout) | F01 |
| L-15 | Retries: `RETRIES=1`, **linear** backoff (1.5 s × attempt), only for network errors and 5xx; 429 is treated as blocked at once with no `Retry-After` handling, no exponential backoff | `fetcher.py::fetch_page`, `_one_attempt` | Endpoints returning 429/503 with `Retry-After`; measure timing | F04, F05 |
| L-16 | Domain health (`domain_stats`) is written but never read to slow down or skip; per-domain politeness is only a 0.2 s sleep between non-home pages and a delay increase after 403/429; no per-domain scheduler | `profile.py::record_domain`, `pipeline.py`, `config.py` | Look for repeated hits to a blocking domain; read request timing | F03, F06, F07 |
| L-17 | Response is fully downloaded before the size check (only a declared `Content-Length` rejects early); `.gz` sitemaps are decompressed with no output cap; XML parsed with `ElementTree` | `fetcher.py::_one_attempt`, `sitemap.py::parse_sitemap` | Scenario server: huge body, slow-drip body, gzip bomb, entity-expansion sitemap; watch memory/time | D09 |
| L-18 | Extraction drops whole `<header>`, `<nav>`, `<footer>`, `<aside>`, `<form>` and any element whose class/id contains hints such as `modal`, `popup`, `sidebar`, `newsletter`, `subscription` (could remove real content, e.g. a pricing section id `subscription-plans`, or hero text inside `<header>`); only `h1–h3, p, li, dd` are kept (tables, `h4–h6`, plain `div` text lost unless a fallback applies) | `extract.py` | Gold set + manual review of extracted text | E02, E03 |
| L-19 | Structured data lines are appended into the page text and cannot be told apart from page text afterwards; no canonical-URL handling for dedup; no near-duplicate detection beyond exact line dedup | `structured.py`, `pipeline.py::_with_structure`, `extract.py` | Pages with JSON-LD; duplicate/near-duplicate pages | C10, E04, E05 |
| L-20 | Scale design: all pending rows are claimed and turned into asyncio tasks at once (bounded by a semaphore); one process; SQLite; sites crawled sequentially inside; no durable queue (no Redis/Celery); no per-page persistence | `runner.py::_claim`, `_run_inside`; `database.py` | Observe memory/time at 100 and 1,000 URLs. **Report measured numbers only — do not extrapolate to 60,000** | G01, G02, G07 |
| L-21 | Cancel exists in CLI/API only; cancellation is checked between completions, not mid-site | `runner.py::_is_cancelled`, `ops.py` | Start a run and cancel it | A13, G02 |
| L-22 | README says "108 passed, 100% statement coverage". A static count found 143 test functions (~154 parametrized cases) in 14 files. Neither figure was run | `README.md`, `tests/` | Run pytest with coverage and record the real numbers | J04 |
| L-23 | Homepage tries `https://` first and `http://` only after a network error; redirect to a different domain is followed and recorded only as the final URL (no "Redirected" status) | `pipeline.py::_fetch_homepage` | Redirect category: cross-domain, http-only sites | B01, B06 |

---

## Part 2 — AI module and UI leads (Phase 3 only — do not act on these before then)

| Lead | What was seen | Where |
|---|---|---|
| M-01 | `Website.services` is never written; services are merged into `products`, so the Services field/column is always empty | `app/ai/pipeline.py`, `app/classifier.py`, `app/exporters.py` |
| M-02 | B2B/B2C is stored only inside `classification_meta` (`customer_type`) and never shown or exported; `business_model` holds free text from the model | `app/ai/pipeline.py`, `app/records.py`, UI |
| M-03 | The model sees only the first 12,000 characters (`MAX_TEXT_CHARS`, default 12000) while the crawler stores up to 60,000; later pages can be cut off and the cut-off is not recorded | `app/ai/pipeline.py::_clip` |
| M-04 | Export has 20 columns vs ~45 in the requirements; no supporting sheets; values written as text (confidence, dates); no formula-injection escaping; XLSX is built fully in memory before streaming | `app/exporters.py` |
| M-05 | UI gaps: no cancel button, jobs view, bulk retry or "classify all"; status filter cannot select blocked/failed/unreachable; Accept shown only for `needs_review`; no edit of a classification; page size max 20; no industry distribution / record detail view | `templates/index.html`, `app/main.py`, `app/records.py` |
| M-06 | No `last_analyzed_at`, no prompt version, no token/latency/cost metrics stored; `confidence_version` hard-coded in meta | `app/models.py`, `app/ai/pipeline.py` |
| M-07 | A failed classification leaves `classification_status` blank (only `status` changes) | `app/classifier.py` |
| M-08 | Gemini (cloud) provider is still wired in, conflicting with the local-only guide; its default model name `gemini-3.8-flash` could not be verified | `app/ai/provider.py`, `.env.example`, `requirements.txt` |
| M-09 | Default Ollama model is `qwen2.5:7b-instruct`; the guide asks to benchmark Qwen3-8B/14B (and optionally 30B-A3B); `benchmark.py` times search/export only, not the LLM | `app/ai/provider.py`, `app/benchmark.py` |
| M-10 | Confidence thresholds hard-coded at 80 / 50 (requirements: 90 / 70, and "configurable"); taxonomy is a small flat list (15 industries, 8 business types) with no sub-industry/niche taxonomy | `app/ai/confidence.py`, `app/taxonomy.py` |
| M-11 | LLM retries have no backoff; classification is sequential with no AI worker pool/queue | `app/ai/pipeline.py`, `app/classifier.py` |
| M-12 | No authentication or CSRF protection (acceptable only for localhost use); `seed_dummy.py` writes an older `[PAGE: …]` text format that breaks evidence source-URL lookup | `app/main.py`, `scripts/seed_dummy.py` |
