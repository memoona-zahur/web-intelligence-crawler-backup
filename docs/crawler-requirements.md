# Crawler Requirements Checklist (CR-IDs)

One numbered list of **every crawling-related requirement** from the project documents, so each can be
tested, scored and traced. Nothing here is new: each row cites where it came from.

**Source tags**
- `RD §n` — Requirements & Proposal document (`docs/source/requirements-proposal.extracted.md`)
- `MP §n` — Master Implementation Prompt (`docs/source/master-prompt.md`)
- `LG §n` — Local LLM guide (`docs/source/local-llm-guide.md`), only where it touches crawling

**Priority:** `M` Must (stated as must / required / MVP "Yes") · `S` Should (recommended / "where possible")
· `O` Optional or later phase.

**Scope:** ingestion, validation, discovery, fetching, extraction/cleaning, crawl persistence, safety,
reliability, scale, crawl testing. AI classification, taxonomy, confidence, dashboard and review UI are
**not** listed (Phase 3 covers them), except that the crawler must hand clean, source-traceable content
to them (E08, E09).

**Rule:** if you find a crawling requirement in the source documents that is missing here, add it as
`CR-X##`, tell the user, and score it like the others.

---

## A. URL ingestion & management

| ID | Pri | Requirement | Source |
|---|---|---|---|
| CR-A01 | M | Bulk import from CSV/Excel with optional external-ID or source/reference fields | RD §4 |
| CR-A02 | M | Incremental ingestion: new URLs can be added later without re-importing the whole dataset | RD §4 |
| CR-A03 | S | Load URLs from an existing database / staging table | RD §4 |
| CR-A04 | M | Manual entry of one or more URLs for testing or reprocessing | RD §4, MP §5 |
| CR-A05 | O | API submission, single and bulk (later phase) | RD §4, MP §5 |
| CR-A06 | M | Normalize protocol, `www`, trailing slash and obvious alternate forms; remove duplicates | RD §3, §4; MP §5 |
| CR-A07 | M | Keep the original URL exactly as received, plus source file/batch and source record ID when available | RD §4, §13.1 |
| CR-A08 | M | Domain extraction, invalid-URL handling, existing-record detection | MP §5 |
| CR-A09 | S | Optional recrawl of previously processed websites | MP §5 |
| CR-A10 | M | Batch import summary (added / duplicate / invalid) that can be reviewed | MP §5, §11 |
| CR-A11 | M | Ingest and queue at least 60,000 records without manual batching | RD §19 |
| CR-A12 | M | Persistent job records with retry handling, failure reasons, status and progress tracking | MP §5 |
| CR-A13 | M | Explicit lifecycle states (pending → queued → crawling → extracting → … → completed) plus failed / retry / cancelled / insufficient-evidence; transitions observable and recoverable after a worker restart; never rely only on in-memory state | MP §5, §16 |

## B. URL validation & website status

| ID | Pri | Requirement | Source |
|---|---|---|---|
| CR-B01 | M | Check: URL format validity, DNS/domain resolution, HTTP/HTTPS availability, redirect destination, SSL/TLS error, HTTP status code, timeout/connection failure | RD §5 |
| CR-B02 | M | Detect parked / for-sale domains | RD §5 |
| CR-B03 | M | Detect under-construction or empty websites | RD §5 |
| CR-B04 | M | Detect blocked / access-denied sites | RD §5 |
| CR-B05 | M | Detect duplicate domain or canonical equivalent | RD §5 |
| CR-B06 | M | Status vocabulary covers: Pending, Active, Invalid, Unreachable, Redirected, Blocked, Parked, Under Construction, Crawled, Failed, Requires Review | RD §5 |
| CR-B07 | M | Crawl status values usable in export: Completed, Partial, Failed, Blocked, etc.; a partial crawl still keeps its useful evidence | RD §13.1, MP §10 |
| CR-B08 | M | Crawl status stored separately from AI classification status (a site can crawl fine and stay unclassified) | MP §10 |
| CR-B09 | M | URL validation and safe-target checks happen before a job is created/queued | MP §3F |
| CR-B10 | M | Validate the URL **and every redirect target** against SSRF; block localhost, private, link-local and restricted networks unless explicitly authorised | MP §6 |

## C. Page discovery & focused crawling

| ID | Pri | Requirement | Source |
|---|---|---|---|
| CR-C01 | M | Do not crawl whole sites; focus on pages that reveal what the business does | RD §6.1, MP §3A |
| CR-C02 | M | Homepage is always fetched first | RD §6.1, MP §3A |
| CR-C03 | M | Priority signals — High: About / About Us / Company / Who We Are / Our Story; Services / Solutions / Capabilities / Expertise / What We Do; Products / Platform / Software / Features. Medium: Industries / Markets / Sectors / Solutions by Industry; Customers / Case Studies / Portfolio / Pricing / Partners / Contact | RD §6.1 |
| CR-C04 | S | Order of preference: Homepage, About, Products/Product Categories, Services/Solutions, Industries/Markets/Who We Serve, Contact/Locations (when useful for geography), other pages only when evidence is insufficient | MP §3A |
| CR-C05 | M | Discovery uses more than URL patterns: navigation text, anchor text, page title, headings, sitemap data and heuristics, so About/Services/Product/Industry pages are found even on non-standard paths | RD §6.2, MP §3B |
| CR-C06 | M | Do not spend budget on blog archives, tags, author pages, legal policies, careers, search results, login/account pages, carts, checkout, irrelevant blog posts, duplicate URLs or unrelated resources — unless needed for a specific classification | RD §6.3, MP §3A |
| CR-C07 | M | Configurable page budget of about 5–10 useful pages per site; adjustable; stop earlier when evidence is sufficient | RD §6.3, MP §3A |
| CR-C08 | M | Sitemap-assisted discovery: read sitemap references in robots.txt; try common sitemap locations; parse sitemap indexes and sitemaps; fall back to internal links when sitemap data is missing/incomplete; rank candidates by URL path, titles, link text and relevance; deduplicate canonical/equivalent URLs; never crawl a whole sitemap blindly | MP §3B |
| CR-C09 | M | Prevent crawl loops, duplicate fetches and unbounded link discovery | MP §6 |
| CR-C10 | M | Canonical-URL handling | MP §7 |

## D. Fetching (HTTP-first, conditional browser)

| ID | Pri | Requirement | Source |
|---|---|---|---|
| CR-D01 | M | Async HTTP client (httpx or aiohttp) is the first attempt for every page | MP §3C, RD §11–12 |
| CR-D02 | M | Handle redirects, response codes, content types, timeouts and character encodings | MP §3C |
| CR-D03 | M | From each response extract HTML text, metadata, headings, links and structured data | MP §3C |
| CR-D04 | M | Content-quality check: HTTP 200 does not mean useful content. Consider text length, title, headings, paragraphs, business-related terms, and rendered content vs. an empty application shell; thresholds configurable | MP §3C |
| CR-D05 | M | Browser fallback only when HTTP content is a JS shell / too thin / fails quality checks AND rendering is likely to help; off by default until that condition; never "Playwright for every page" | MP §3C–D, RD §12, §16 |
| CR-D06 | M | Browser limits: timeouts and resource limits; skip unnecessary images, media, ads and third-party resources where feasible; same per-domain rate limits and policies as HTTP; downloaded site code runs only inside the browser sandbox | MP §3D, RD §17 |
| CR-D07 | M | Record per page whether it was retrieved by HTTP or browser; record browser failures and continue under the retry/recovery policy | MP §3D |
| CR-D08 | M | The majority of active, publicly accessible sites must be crawlable without full browser rendering | RD §19 |
| CR-D09 | M | Limit response size, content types, decompression, redirect depth and browser resource usage | MP §6 |
| CR-D10 | M | Persist per site: HTTP status, final/redirect URL, pages attempted and pages crawled; per page: URL, page type, title, HTTP status, crawl status, content length, error, crawled-at | RD §13.1–13.2, §14 |

## E. Content extraction, cleaning & evidence-ready output

| ID | Pri | Requirement | Source |
|---|---|---|---|
| CR-E01 | M | Never pass raw HTML downstream; extract and compress business-relevant content first | RD §7 |
| CR-E02 | M | Retain: title and meta description; H1/H2/H3; meaningful paragraphs and lists; product/service names; CTA and descriptive labels; structured data when useful | RD §7 |
| CR-E03 | M | Remove or de-prioritise: CSS/JS source; repeated navigation and footer text; cookie banners and popups; ads and tracking text; long legal boilerplate; duplicate text across pages | RD §7 |
| CR-E04 | M | Structured data: JSON-LD, Schema.org organization / local-business fields, title and meta description, Open Graph, canonical URL, relevant product/service data. Treat as supporting evidence, validate it, keep its source | MP §3E |
| CR-E05 | M | Boilerplate removal, navigation/footer noise reduction, duplicate-content detection, content hashing, extraction-quality checks | MP §7 |
| CR-E06 | M | Reprocess only when content changed (hash) or an explicit recrawl is requested | MP §7 |
| CR-E07 | M | Store cleaned content separately from crawl metadata; optionally keep raw HTML/text in controlled storage with configurable retention | MP §7 |
| CR-E08 | M | Output is cleaned, deduplicated, AI-ready content with source URLs and extraction metadata, per page | MP §14 (MP-Phase 2) |
| CR-E09 | M | Evidence-ready: every retained fact traces to a fetched page; crawler records source page URL, retrieval timestamp and extraction method; evidence comes only from retrieved site content | MP §7, LG §5 |
| CR-E10 | M | If cleaned content is truncated or cut for size, the truncation is recorded (what was cut) | LG §10 |
| CR-E11 | M | Sanitise/validate extracted website values before they are displayed or exported (including spreadsheet-formula characters `= + - @`) | RD §13.3, §17 |
| CR-E12 | O | Capture public contact/social signals (general email, phone, LinkedIn, other social URLs) and technology hints | RD §13.1, §18 |

## F. Responsible crawling & safety

| ID | Pri | Requirement | Source |
|---|---|---|---|
| CR-F01 | M | Respect applicable robots.txt directives and legal/contractual access restrictions; a documented robots policy exists | RD §17, MP §6 |
| CR-F02 | M | Descriptive, consistent User-Agent with a real contact/policy URL in production | RD §17, MP §6 |
| CR-F03 | M | Configurable per-domain request rate and concurrency limits | RD §12, §17; MP §6 |
| CR-F04 | M | Timeouts, **exponential** backoff and retry limits for transient failures | RD §12, §16; MP §6 |
| CR-F05 | M | Slow down or stop on repeated 429 / 403 / other blocking; record blocked/CAPTCHA sites; never bypass CAPTCHA, authentication, access controls or anti-bot protection; no aggressive IP rotation or evasion | RD §16–17, MP §6 |
| CR-F06 | M | Track domain health: latency, failures, last successful fetch | MP §6 |
| CR-F07 | M | Domain-level backoff and scheduling so one problematic site never blocks the batch | MP §6 |
| CR-F08 | M | Do not store unnecessary credentials, cookies or personal data | RD §17 |
| CR-F09 | M | Keep a detailed failure reason and retry count per site; manual requeue of failed websites; design for optional re-crawl after a configurable period | RD §16 |
| CR-F10 | S | Use stable, reputable outbound networking | MP §6 |

## G. Queue, reliability & scale

| ID | Pri | Requirement | Source |
|---|---|---|---|
| CR-G01 | M | Asynchronous, queue-based processing so failed sites do not block the batch (Redis+Celery or BullMQ recommended; any durable queue acceptable) | RD §11–12, MP §4 |
| CR-G02 | M | Bounded concurrency, queue backpressure, persistent scheduling, idempotent jobs, hash-based reprocessing, retry & recovery, batch-level progress | MP §12 |
| CR-G03 | M | Crawl workers independently scalable from AI workers | MP §12, LG §9 |
| CR-G04 | M | Metrics: success rate, latency, errors, throughput | MP §12 |
| CR-G05 | M | Structured logs, job tracking, error reporting; never silently swallow exceptions; actionable error messages | MP §4, §16 |
| CR-G06 | M | A failed website never interrupts the batch and always keeps an actionable failure reason | RD §19 |
| CR-G07 | M | Plan for ~60,000 sites ≈ 300,000 page fetches (planning estimate only); do not assume worker count or runtime without measuring | RD §12, MP §12 |
| CR-G08 | M | Benchmark on a pilot before raising concurrency; scale gradually while watching target-site responses and system resources | MP §12, §15 |
| CR-G09 | M | Full processing runs with monitoring, retries and export checkpoints | RD §20 |

## H. Crawl data persistence

| ID | Pri | Requirement | Source |
|---|---|---|---|
| CR-H01 | M | PostgreSQL (recommended store) with migrations (Alembic or equivalent), normalized schema and sensible indexes; if the project stays on SQLite, that decision is documented and justified | RD header, MP §4, §10 |
| CR-H02 | M | Entities for crawling: Websites (original URL, normalized domain, redirect URL, availability, HTTP status, crawl status, last crawl), crawl jobs, discovered pages, page fetch attempts, extracted content (or references), website pages, errors and retry history | RD §14, MP §10 |
| CR-H03 | M | Timestamps, content hashes and processing metadata; Last Crawled At | MP §10, RD §13.1 |
| CR-H04 | M | Data to support the crawl-related export columns: Record ID, Source/Batch, Original URL, Normalized Website, Final/Redirect URL, Website Status, HTTP Status, Pages Crawled Count, Pages Attempted Count, Crawl Status, Crawl Error/Notes, Last Crawled At | RD §13.1 |
| CR-H05 | M | Data to support the "Crawled Pages" sheet and the "Errors / Failed URLs" sheet (error category, message, retry count, last attempt date) | RD §13.2 |

## I. Rollout, pilot & acceptance (crawler side)

| ID | Pri | Requirement | Source |
|---|---|---|---|
| CR-I01 | M | Pilot is representative: different countries, industries, site technologies, small and large sites, product- and service-based companies; start ≈100 sites, expand to 500–1,000 only after validation, then controlled stages | RD §20, MP §15 |
| CR-I02 | M | Measure: crawl success rate, useful-content retrieval rate, relevant-page discovery quality, browser-fallback frequency, processing latency, retry and failure rates, resource usage, throughput | MP §15 |
| CR-I03 | M | No claim of "production-ready" or "can process 60,000 in X time" until benchmarks support it | MP §15 |
| CR-I04 | M | Pilot validates page discovery, blocking rates, content extraction and runtime; scale test validates throughput | RD §20 |

## J. Testing

| ID | Pri | Requirement | Source |
|---|---|---|---|
| CR-J01 | M | Automated tests for: URL normalization & dedup; URL validation & redirect safety; sitemap parsing; internal-link discovery; focused page ranking; HTTP-first retrieval; insufficient/JS-dependent content detection; Playwright fallback decisions; HTML extraction & cleaning; structured-data extraction; content hashing & duplicate detection; domain throttling & backoff; retry & failure states; DB persistence & job recovery | MP §13 |
| CR-J02 | M | Controlled fixtures for normal HTML, redirects, errors, empty responses, duplicate pages, sitemap files, structured data and JS-rendered content | MP §13 |
| CR-J03 | M | Automated tests must not depend on aggressively crawling real sites (mock the network). The user's field test is a separate, polite, explicitly requested activity | MP §13 |
| CR-J04 | M | Run relevant tests after each phase and report actual results; never claim a pass that was not executed | MP §13, §16 |

## K. Coding rules (apply to all code written in Phase 2)

| ID | Pri | Requirement | Source |
|---|---|---|---|
| CR-K01 | M | Inspect before modifying; reuse working code; follow existing conventions; do not replace working architecture without a clear reason | MP §1, §16 |
| CR-K02 | M | Modular, typed, maintainable code; crawler, AI, API and frontend responsibilities kept separate | MP §4, §16 |
| CR-K03 | M | Configuration outside source code; never commit credentials or secrets | MP §16 |
| CR-K04 | M | Migrations for every schema change; avoid unnecessary dependencies; explain material stack changes before making them | MP §4, §16 |
| CR-K05 | M | Jobs idempotent and recoverable; meaningful logs | MP §16 |
| CR-K06 | M | Do not invent implementation, test or benchmark results | MP §16 |
| CR-K07 | M | Each phase reviewable and runnable before the next one starts | MP §16 |

---

## Roadmap items that are NOT crawler requirements today
Technology detection, lead scoring / sales intelligence, CRM integration and periodic re-crawl **automation**
are "Phase 2" in the requirements document (RD §18). Only the *design for* re-crawling (CR-F09) is required now.
