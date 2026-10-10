# Phase Plan — Crawler Field Test, Production Crawler, Improvement Review

"Phase 1/2/3" below are **our** phases. The master prompt's own phases are always written `MP-Phase n`.
Requirement IDs (`CR-xxx`) are defined in `docs/crawler-requirements.md`.

## 0. Rules that apply to every phase

1. **Crawling only.** AI classification and UI are not run, not changed and not scored until Phase 3.
2. **Evidence or it did not happen.** Every PASS / FAIL cites a CR-ID plus evidence (URL, log line,
   DB row, test output). Anything not run is `NOT TESTED` with the reason. Never round up.
3. **Be polite to real sites** (CLAUDE.md rules). Each real domain is visited at most once per run;
   never re-run the full set repeatedly; start every new dataset with the 100-URL smoke subset.
4. **Gates.** At each GATE, stop and show me a short summary. I approve before you continue.
5. **Same yardstick in Phase 1 and Phase 2.** Same dataset file, same harness, same report format, so
   the two runs can be compared line by line.
6. **Real internet changes.** A failure caused by a site changing is not a code bug. Re-verify every
   failing URL independently (curl / DNS lookup / browser) before blaming the code, and label it
   `SITE-CHANGED` if the expectation no longer holds.

### Suggested model / mode per task (suggestion — change if results disappoint)
| Task | Suggested |
|---|---|
| Phase 1 planning, requirement-to-code review, Phase 2 architecture, Phase 3 analysis | `opusplan` (or `opus` for the Phase 3 comparison) in Plan Mode |
| Building the dataset, harness, report generator, fixing bugs | `sonnet` |
| Mechanical edits, formatting, renaming | `haiku` |
Use `/clear` between unrelated tasks and `/context` to watch usage.

---

## 1. Phase 1 — Field-test the EXISTING crawler (code stays unchanged)

### 1.1 Hard constraints
- Do **not** edit anything under `app/`, `templates/`, `tests/`, `scripts/`. New files go only in `crawl_eval/`.
- Observe the crawler by wrapping and monitoring from the harness. Wrappers must be pass-through
  (same inputs, same outputs, same exceptions) and every wrapper must be listed in the report.
- Run the baseline from an isolated copy or isolated DB so `data/websites.db` is never touched.
- Prove the code is unmodified: record `git rev-parse HEAD`, tag it `crawler-baseline-v1`, and store a
  SHA-256 manifest of every file under `app/` in `run_manifest.json`.
- Environment must be recorded: OS, Python version, library versions, whether Playwright Chromium is
  installed (install it for this test so the browser fallback is exercised), network location.

### 1.2 Steps and gates
| Step | What | Output |
|---|---|---|
| 0 | Baseline lock (tag, SHA manifest, environment record). Run `pytest` with coverage and record the real numbers (README claims 108 passed / 100% crawler coverage — verify, do not repeat) | `crawl_eval/baseline/` |
| 1 | Read the requirements and known findings. Build a **traceability matrix**: for every CR-ID, where the existing code handles it (file::function) or "not implemented". This is a *static* verdict, to be confirmed by running tests | `crawl_eval/traceability_matrix.csv` |
| 2 | Design and build `testing_URLs.csv` (see 1.3) | file + `dataset_summary.md` |
| **GATE 1** | Show me: traceability summary, dataset summary (counts per category), sources used, how URLs were verified, the harness design | wait for approval |
| 3 | Build the harness (see 1.4) and run the **100-URL smoke subset**. Fix harness bugs only (never app code) | `results/<run_id>_smoke/` |
| **GATE 2** | Show me smoke results and any harness problems | wait for approval |
| 4 | Full run on all URLs (resumable) | `results/<run_id>/` |
| 5 | Analysis: report, issue log, sir note (see 1.5–1.7) | files below |
| **GATE 3** | Hand over report + sir note | done when 1.8 is satisfied |

### 1.3 `testing_URLs.csv` — dataset specification
**Size:** 1,000 rows (600 happy-path + 400 error/edge-path). `smoke=Y` marks a 100-row subset that
mirrors the category mix. Do not pad: if a category cannot reach its count with *verified* URLs, report
the shortfall at GATE 1.

**Columns:** `id, url, category, subcategory, source_type, expected_outcome, expected_status,
expected_pages_note, tags, smoke, country, language, tech_stack_hint, why_included, source_of_url,
verified_at, verification_method, notes`
- `url` is exactly as a user might import it (include messy forms for the input-handling rows).
- `expected_outcome` is the **oracle**: what a correct crawler should do, decided *independently of the
  existing code* (from the requirements and from checking the site yourself with curl/dig/browser).
  Use the requirement vocabulary: Pending, Active, Invalid, Unreachable, Redirected, Blocked, Parked,
  Under Construction, Crawled, Failed, Requires Review (CR-B06).
- `source_type`: `real` (live public site), `public-test-endpoint` (httpbin, badssl, `.invalid`
  domains, etc. — designed for testing), or `local-scenario` (your own scenario server, 1.4).
- `verified_at` + `verification_method` are mandatory. **Never invent URLs from memory.** Find them
  through web search / public directories / lists, then check each one resolves or fails the way the
  row says. Record where each came from (`source_of_url`).

**Category quotas (1,000 total)**

*Happy paths — 600*
| Category | Rows |
|---|---|
| Corporate / B2B services (agencies, IT, consulting, legal, accounting) | 70 |
| Manufacturers, industrial, distributors, wholesalers | 60 |
| E-commerce and retail (large and small, custom and platform-built) | 60 |
| SaaS / software / platforms | 60 |
| Healthcare, education, finance, real estate, non-profit, government | 80 |
| Small local businesses on site builders (WordPress, Wix, Squarespace, Shopify, Webflow) | 60 |
| Large multinational enterprises (heavy sites, mega-menus, cookie walls) | 30 |
| Non-English / international (European, Arabic/RTL, CJK, South-Asian incl. Pakistan, Latin-American) | 80 |
| JavaScript-heavy SPAs that need browser rendering (React, Vue, Angular, Next.js) | 50 |
| Minimal / one-page / static sites | 30 |
| Sitemap variants (sitemap index, `.gz`, none, broken, huge) and non-standard nav paths | 20 |

*Error and edge paths — 400*
| Category | Rows |
|---|---|
| Dead domains (NXDOMAIN) — use `.invalid` and verified-dead real domains | 30 |
| Parked / for-sale / expired-registration domains | 30 |
| Under-construction, "coming soon", default server pages (nginx/Apache/cPanel) | 25 |
| Timeouts, connection refused, very slow responses | 25 |
| SSL/TLS problems (expired, self-signed, wrong host, bad chain) | 20 |
| HTTP errors: 401, 403, 404, 410, 429, 500, 502, 503 | 30 |
| Redirect behaviour: http→https, www↔apex, cross-domain, long chains, loops, meta-refresh, JS redirects, redirect to login | 40 |
| Bot-protected / WAF / CAPTCHA / "checking your browser" sites | 25 |
| robots.txt: disallow-all, partial disallow, crawl-delay, malformed, missing, 5xx robots | 20 |
| Non-HTML and heavy content (PDF, XML, JSON, images, downloads, very large pages, giant sitemaps) | 15 |
| Login-walled / members-only landing pages | 10 |
| Encoding oddities (non-UTF-8, wrong/missing charset, BOM, mixed encodings) | 15 |
| Input handling: malformed URLs, no scheme, uppercase, trailing dots, ports, paths/queries/fragments, IDN/punycode, very long URLs, duplicates (www/trailing slash/http-vs-https), IP literals, `localhost`, private-range and link-local targets, URLs that redirect to private addresses | 80 |
| Thin, empty or error-only pages that look "successful" | 15 |
| Crawl traps (infinite calendars, session-ID URLs, faceted navigation, deep link graphs) | 20 |

**Gold set:** at least 100 of the happy-path sites carry manually verified key-page URLs
(About / Services / Products / Industries, whichever exist) in `expected_pages_note`, so "relevant-page
discovery quality" (CR-I02) can be measured. Manually review extracted text for at least 30 more sites.

**Safety of the dataset:** no adult, illegal or sensitive content; no sites that explicitly forbid
automated access in their terms for this kind of use; SSRF-style rows are only *inputs the crawler must
refuse* — never probe anyone else's internal network.

### 1.4 Harness (`crawl_eval/`)
- `run_eval.py` — one command I can run: loads `testing_URLs.csv`, imports through the real importer,
  runs the real crawler runner, collects results, writes everything in 1.5.
  Options: `--urls`, `--smoke`, `--limit`, `--concurrency`, `--label` (e.g. `existing-code`), `--resume`.
- **Resumable and checkpointed**: a crash, Ctrl-C or network drop must not lose finished work.
- **Independent probe** (the oracle's second opinion): for each URL, a light check done by the harness
  itself (DNS, one HEAD/GET) to separate "site is down" from "crawler failed".
- **Telemetry by wrapping** (pass-through): per page — URL, HTTP status, final URL, bytes, elapsed
  time, method (HTTP/browser), retries, robots decision, guard decision, error kind; per site —
  pages attempted vs crawled, text size, truncation, timing, memory.
- **Local scenario server** (`crawl_eval/scenario_server.py`) for cases the live internet cannot
  provide reliably: huge body, slow-drip body, gzip bomb, redirect loop, redirect to a private IP,
  endless link graph, charset oddities, malformed sitemap. Because the crawler *rightly* blocks
  localhost, the harness may relax the SSRF guard **only for the scenario server's own host:port**,
  must say so in the report, and must still test the guard against real private/localhost inputs
  with the guard fully on.
- Do not hide problems: harness errors are reported separately from crawler errors.

### 1.5 Progress report (the main deliverable)
Output folder: `crawl_eval/results/<run_id>/`

| File | Purpose |
|---|---|
| `report.html` | **The report I read.** Single self-contained file, no internet needed |
| `summary.md` | One-page plain-English version of the same findings |
| `results.csv` | One row per URL: expected vs actual, verdict, timings, pages, error |
| `requirements_scorecard.csv` | One row per CR-ID: PASS / PARTIAL / FAIL / NOT TESTED + evidence |
| `issues.csv` + `issues.md` | Every issue found (see 1.6) |
| `metrics.json` | All numbers behind the report (reused by Phase 2 comparison) |
| `run_manifest.json` | Commit, file hashes, environment, wrappers used, dataset hash |
| `run.log`, `per_site.jsonl` | Raw evidence |

`report.html` sections, in this order (a reader should know the state of the code in 5 minutes):
1. **Verdict banner** — requirement coverage %, MUST-requirements passing %, issues by severity,
   URL expectation-match rate, and one sentence: "ready / not ready, because…".
2. **Requirements scorecard** — grouped A–K, colour-coded, each row expandable to evidence.
   Coverage % = (PASS + 0.5 × PARTIAL) ÷ applicable, weighted M=3, S=2, O=1; also show MUST-only %.
3. **Where the code is weak** — table of modules (importer, guard, fetcher, discover, extract,
   browser, runner, profile, persistence) × issue counts by severity, plus the worst offenders.
4. **Results by category** — for each dataset category: expected vs actual outcomes, match rate,
   example URLs. Happy-path and error-path shown separately.
5. **Quality & performance metrics** — crawl success rate; useful-content rate; relevant-page
   discovery (gold set precision/recall); browser-fallback rate and whether it helped; latency
   p50/p95; retries and failure reasons; blocked rate; pages per site; text size; throughput
   (sites/hour) and memory — each stated for *this* run only, no extrapolation to 60,000 (CR-I03).
6. **Top issues** — ranked list with severity, CR-IDs violated, repro URL, code location, root cause,
   and a suggested fix direction (described, **not implemented** in Phase 1).
7. **Appendix** — filterable per-URL table, wrapper list, environment, limitations of this test.

### 1.6 Issues: what to record and how to rate them
Record **everything**, including cosmetic ones. Fields: `ID, severity, title, CR-IDs, module,
file::function, repro URL(s), expected, actual, evidence, suspected root cause, suggested fix direction,
status (confirmed / unconfirmed / site-changed)`. Link each issue to the leads in `known-findings.md`
it confirms or refutes.

| Severity | Meaning |
|---|---|
| Critical | Security issue, data loss/corruption, batch-stopping crash, or silently wrong results at scale |
| Major | A MUST requirement fails or a whole class of sites is mishandled |
| Minor | Wrong or poor behaviour on a narrow case; a SHOULD requirement fails |
| Cosmetic | Naming, messages, logging quality, documentation mismatches |

### 1.7 Note for my sir
`SIR_UPDATE_phase1.md`: **at most 10 bullet points**, plain English, each one short. Must cover: what was
tested and how big; overall requirement coverage; what works well; the most serious problems; error-path
behaviour; performance/reliability; honest limits of the test; and what happens next (Phase 2).

### 1.8 Phase 1 is done when
- the dataset, harness, full-run results, report, issue log and sir note all exist;
- every CR-ID has a verdict with evidence or an explained `NOT TESTED`;
- every lead in `known-findings.md` is marked confirmed / refuted / not testable;
- app code is proven unchanged (hash manifest matches the baseline tag).

---

## 2. Phase 2 — Production-ready crawler, then test → fix → retest

Starts only when I say so.

### 2.1 Plan first (GATE 4)
Work on a branch `crawler-v2`; keep tag `crawler-baseline-v1` untouched. Before writing code, present:
- a CR-ID by CR-ID plan (every M and S requirement; O requirements either planned or explicitly deferred
  with a reason);
- proposed architecture and **every material stack change** (PostgreSQL + migrations, a durable queue
  such as Redis/Celery, new dependencies) with trade-offs — if SQLite is kept, justify it against CR-H01/CR-G01;
- how `known-findings.md` issues and all Phase 1 issues are covered;
- test plan (unit/fixture tests per CR-J01 plus the field test).
I approve before implementation.

### 2.2 Build
Meet **every** requirement in `docs/crawler-requirements.md` — no minor point skipped. Reuse working
code from the baseline where it is correct. Add automated tests (mocked network, controlled fixtures) for
every item in CR-J01/J02 and run them.

### 2.3 Test → fix → retest loop
```
build → unit/fixture tests → field test on the SAME testing_URLs.csv (smoke first, then full)
      → report + issues → fix → retest → … until the exit criteria hold
```
- Re-run the full set after every fix batch that touches fetching, discovery or extraction; re-run
  only affected URLs for small fixes, then confirm with a full run before closing.
- Every issue closes with evidence (before/after result for the repro URL). A fixed issue that
  reappears is a regression and is reported as such.
- If 5 loop iterations pass without improvement, stop and report where you are stuck.
- Never "fix" a failure by changing the expected outcome unless the oracle was wrong — and then say so.

### 2.4 Exit criteria (Phase 2 ends when ALL hold)
1. Every M requirement = PASS, every S requirement = PASS or justified; any deferred O requirement is listed.
2. Zero open Critical or Major issues; any open Minor/Cosmetic issues listed with reasons.
3. Unit/fixture tests pass (actual output attached); no skipped tests unexplained.
4. Two consecutive full runs on the dataset with no Critical/Major issue and no regression (results may
   differ only where sites genuinely changed, each such case re-verified).
5. Expectation-match rate and metrics are reported honestly, with remaining mismatches explained.
6. No production-readiness or "60,000 sites in X hours" claim beyond what the measured runs support.

### 2.5 Comparison deliverables
`crawl_eval/compare_runs.py` builds, from the two `metrics.json` files:
- `comparison.html` and `comparison.md` — a table I can show my sir:

| Area | Existing code (Phase 1) | New code (Phase 2) | Change |
|---|---|---|---|
| Requirement coverage % (all / MUST only) | | | |
| Requirements PASS / PARTIAL / FAIL / NOT TESTED | | | |
| Issues by severity (open) | | | |
| URL expectation-match rate — happy / error / overall | | | |
| Crawl success, useful-content rate, gold-set page discovery | | | |
| Browser-fallback rate and benefit | | | |
| Latency p50/p95, throughput, memory | | | |
| Error handling: classes of failure correctly identified | | | |

plus a per-CR-ID side-by-side and a per-category side-by-side. `SIR_UPDATE_phase2.md` (≤10 bullets)
summarises the improvement.

---

## 3. Phase 3 — `suggested_improvements.md` (writing only, no code changes)

Starts only when Phase 2 is finished and I say so.

**Scope:** the AI module (`app/ai/`, `app/classifier.py`, taxonomy, confidence) and the UI / review /
search / export layer (`templates/index.html`, `app/main.py`, `app/records.py`, `app/exporters.py`),
compared against the requirement documents in `docs/source/`. Crawling is already covered.
Do not change any code.

**Method:** read every file in scope; compare against the original documents (not against my
summaries); verify each leads item in the "AI / UI leads" part of `known-findings.md` and look for more.

**Format (easy to read, not long — a teammate who never saw the code should understand it in one sitting):**
1. Short summary (≤ 10 lines): what is in good shape, what is not.
2. **Comparison table** — `# | Area | What the requirements say (with doc/section) | What the existing
   code does | Gap | Severity | Suggested improvement | Effort (S/M/L)`.
3. Prioritised improvement list (Must-fix / Should-fix / Nice-to-have).
4. **Model recommendations** for our use case, with reasons and trade-offs: (a) which local LLM(s) to
   benchmark first and which runtime, given the local-only requirement and a realistic dev machine;
   (b) which Claude Code model/mode to use for each kind of implementation task later.
5. Open questions for the team (unclear or conflicting requirements).

Rules: nothing skipped, nothing invented, every row traceable to a document section and a file.
