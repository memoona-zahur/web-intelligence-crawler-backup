# AI-Powered Website Intelligence & Business Classification System

Group project: turn a raw list of 60,000+ company website URLs into structured,
searchable business intelligence (company type, products, services, industry,
target market) with Excel-ready export.

**Pipeline:** `Import URLs → Crawl & Clean → AI Classification → Review → Export`

| Stage | Module | Status |
|---|---|---|
| 1. Save the URL list | `app/importer.py`, `app/main.py` | done |
| 2. Crawl sites → `clean_text` | `app/crawler/` + `app/crawler_cli.py` | done |
| 3. AI classification | `app/classifier.py`, `app/ai/` | done |
| 4. Search, review, export | `app/records.py`, `app/exporters.py` | done |
| 5. Hardening | `app/ops.py`, `app/recovery.py`, `app/report.py` | done — see below |

---

## Quickstart

Requires **Python 3.10+**.

```bash
git clone https://github.com/M-Ali-devv/Web-intelliegence.git
cd Web-intelliegence
git checkout feature/crawler      # this PR's branch (not needed after merge)
# already cloned? run: git fetch && git checkout feature/crawler

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload       # web UI at http://127.0.0.1:8000
```

Open **http://127.0.0.1:8000** and import your URLs (rows start as `pending`):

- **Paste box** — one URL per line (or CSV content pasted directly)
- **CSV upload** — header row containing one of `url`, `original_url`,
  `website`, `website_url`, `link` (case-insensitive)

Before the first crawl, tell the crawler who it is (a real policy page or `mailto:` address in `.env`; see `.env.example`). Production mode refuses to start without it:

```bash
CRAWLER_CONTACT_URL=https://your-company.example/crawler     # required in production
CRAWLER_MODE=production        # production (default) | dev | test  (dev/test: local test servers only)
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/websites   # optional; without it the local SQLite file is used
```

Then crawl — UI button or CLI:

```bash
.venv/bin/python -m app.crawler_cli            # crawl all pending rows
.venv/bin/python -m app.crawler_cli --limit 20 # first 20 pending
.venv/bin/python -m app.crawler_cli --id 3 --id 7 --force   # re-crawl specific rows
.venv/bin/python -m app.crawler.worker --workers 5          # a crawl worker process (start several; they share the queue)
.venv/bin/python -m app.ops import urls.csv                 # bulk import without the web page (CSV / XLSX / lines)
```

Or click **Crawl pending websites** / per-row **Re-crawl** in the web UI.
The UI run is a background task: wait ~10 seconds, refresh, and watch the
*Status* / *Clean text* columns update (hover the status badge for errors).

---

## Module 2 — Crawler contract (read this before writing the AI step)

### What the crawler writes

For every imported website the crawler fetches the homepage plus ranked
business pages (About / Services / Products / Industries — max **8 pages**,
configurable in `app/crawler/config.py`), strips boilerplate, and stores one
consolidated profile in the `clean_text` column of the `websites` table.

**`clean_text` format** — pages separated by a machine-readable header:

```
=== PAGE: homepage | https://stripe.com
<title line>
<cleaned body text, one line per heading/paragraph/list item>

=== PAGE: about | https://stripe.com/about
...
```

Rules the AI step can rely on:

- Headers are always `=== PAGE: <label> | <absolute URL>` — use the URL as
  the `evidence` source for any classification.
- Line breaks are real `\n`; repeated boilerplate across pages is removed
  (first occurrence kept).
- Hard cap: **60,000 characters** per site; if cut, the profile ends with
  `...[truncated]`.
- `clean_text IS NULL` means "no usable text" (never crawled, empty site,
  unreachable, blocked, …) — **skip those rows**.

### Rows to process (SQL)

The database is `data/websites.db` (SQLite, created on first run).

```bash
sqlite3 data/websites.db "
SELECT id, normalized_website, clean_text
FROM websites
WHERE status = 'crawled' AND clean_text IS NOT NULL;"
```

After classifying, fill only the AI-owned columns (all exist already, nullable):
`company_name`, `description`, `business_type`, `industry`, `niche`,
`products`, `services`, `confidence` (0–100), `evidence`.

### Status vocabulary (`websites.status`)

| Status | Meaning |
|---|---|
| `pending` | imported, waiting to be crawled |
| `crawling` | claimed by a run (stuck rows are auto-reset by the next run) |
| `queued` / `extracting` | waiting in the crawl queue / pages are being read |
| `crawled` | ✅ `clean_text` filled — **the AI step processes these** |
| `redirected` | the site redirected to another company's domain; the target was crawled (`final_url`) — `clean_text` filled |
| `parked` | for-sale / parked domain (no `clean_text`) |
| `under_construction` | "coming soon" or a default server page (no `clean_text`) |
| `requires_review` | login wall, error page served with HTTP 200, or no usable text (no `clean_text`) |
| `unreachable` | DNS / timeout / connection / TLS failure |
| `blocked` | HTTP 401 / 403 / 429, or an anti-bot / CAPTCHA page (never bypassed) |
| `robots_blocked` | disallowed by robots.txt, or robots.txt could not be read (5xx/429) and the site waits for a retry |
| `invalid` | rejected by the SSRF guard (private/internal address) |
| `failed` | other HTTP/redirect/content errors — reason in `crawl_error` |
| `empty` | old status of Phase 1 rows; no longer written |

Bookkeeping columns written by the crawler: `crawl_error`, `crawl_error_category`, `pages_crawled`, `pages_attempted`,
`final_url`, `http_status`, `website_status`, `crawl_outcome` (Completed / Partial / Failed / Blocked), `last_crawled_at`,
`content_is_stale`, `truncation_note`, `retry_count`, `next_retry_at`. Pages, cleaned page text, every fetch attempt and every error
are in their own tables (`pages`, `page_contents`, `fetch_attempts`, `crawl_errors`). It never touches the AI-owned columns.

### Reliability guarantees

- One failed site never stops the batch; every failure keeps an actionable
  reason in `crawl_error`.
- Work is kept in a durable queue (table `crawl_tasks`): a task has a lease, a worker that dies loses nothing, and a
  transient failure is retried later (15 min, 30 min, 1 h). Only `pending` rows are queued (unless `--force`).
- Polite & safe: robots.txt respected (RFC 9309, see `docs/robots-policy.md`), one request at a time per domain,
  at least 1 s apart, exponential back-off, Retry-After honoured, private/metadata addresses blocked (SSRF guard on every
  redirect and every browser request), no cookies kept, anti-bot pages are recorded and never bypassed.
- Open policy questions for the supervisor, with the defaults used: `docs/open-questions-for-sir.md`.

---

## Run and look after it

The web site is one process. Crawl workers can be several processes (`python -m app.crawler.worker`). The database is `data/websites.db` (SQLite) unless `DATABASE_URL` points at PostgreSQL. Bind the site to this machine:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`http://127.0.0.1:8000/health` reports whether the database can be read.

```powershell
.\.venv\Scripts\python.exe -m app.ops report
.\.venv\Scripts\python.exe -m app.ops backup
.\.venv\Scripts\python.exe -m app.ops recover
.\.venv\Scripts\python.exe -m app.ops benchmark
.\.venv\Scripts\python.exe -m app.ops metrics            # success rate, latency, errors, throughput of the saved rows
.\.venv\Scripts\python.exe -m app.ops queue-status
.\.venv\Scripts\python.exe -m app.ops requeue --status failed --status unreachable
.\.venv\Scripts\python.exe -m app.ops export-crawl crawl.xlsx   # crawl columns + Crawled Pages + Errors sheets
```

- **report** counts the rows already saved (crawl success, useful text, review rate, browser fallback). It names the next scale stage. It does not claim the system is ready for 60,000 websites.
- **backup** copies the database into `data/backups/` and keeps the newest copies (`BACKUP_KEEP`, default 7).
- **recover** puts interrupted `crawling` rows back to `pending` and marks interrupted crawl or classify jobs failed.
- **benchmark** times search and export shaping on a temporary database. It does not crawl the network.

A crawl claim with no timestamp, or one older than `CRAWL_STUCK_MINUTES` (default 30), is returned to the queue by the next crawl. Uploads larger than `MAX_UPLOAD_BYTES` (default 25 MB, enough for a 60,000-line list) are refused. Limits can be set in `.env`; see `.env.example`.

Stay on about 100 representative websites until crawl quality and a manual check of the classifications look right. Then move toward 500–1,000, and only then raise the batch size. Do not raise concurrency just because the report printed.

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q                                    # unit and fixture tests (network mocked; 9 PostgreSQL tests are skipped without TEST_DATABASE_URL)
.venv/bin/pytest -q --cov=app.crawler --cov=app.importer --cov=app.normalize --cov=app.domains --cov=app.settings --cov=app.profile
# the exact numbers of the last run are in docs/phase2-progress.md (the Phase 1 README figures "108 passed / 100%" were wrong)
```

Set `TEST_DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/crawl_test` (an EMPTY test database) to run the PostgreSQL tests too.
The browser tests use a real Chromium against two local servers and skip when Chromium is not installed (`playwright install chromium`).

All HTTP is mocked or local — tests run offline and are CI-friendly. Coverage spans
happy paths (multi-page crawl, profile building, queue flow) and error paths
(SSRF, redirect loops/attacks, timeouts, 4xx/5xx retries, robots rules,
oversize/non-HTML content, malformed & non-Latin HTML, crash recovery,
double-run lock, CLI failures). 11 tests cover the web layer too
(`/import`, `/crawl`, `/crawl/{id}`, page rendering and
a full UI click → background run → refreshed page flow via FastAPI
`TestClient`).

## Troubleshooting

| Problem | Fix |
|---|---|
| `ERROR: [Errno 98] Address already in use` | An old server is on port 8000: `fuser -k 8000/tcp`, or run on another port: `.venv/bin/uvicorn app.main:app --reload --port 8001` |
| Crawl button clicked, nothing changed | UI runs in background — wait ~10s and refresh the page |
| Status stays `pending` after crawl | No internet, or row is `crawling` (stuck rows auto-reset on next run) |
| Status `blocked` / `robots_blocked` | Normal — that site's bot protection or robots.txt refused us; `clean_text` stays empty |
| Windows users | Use `.venv\Scripts\` instead of `.venv/bin/` in every command |
| `pytest` not found | Install dev deps first: `.venv/bin/pip install -r requirements-dev.txt` |

## Known limits

- JavaScript-only pages use Playwright when it is installed (browser requests go through the same SSRF guard and politeness as HTTP). The Chromium browser is not installed by default: `playwright install chromium`.
- No PDF extraction. Re-crawl is manual (`ops recrawl --older-than N`); there is no automatic schedule.
- PostgreSQL is the intended production database; it is not installed on every machine and its tests need `TEST_DATABASE_URL`. SQLite works for one machine.
- Contact details (e-mail, phone, social links) and technology hints are not collected (CR-E12 deferred).
- The pilot report describes the rows you have saved. It is not a measured runtime for 60,000 websites.
