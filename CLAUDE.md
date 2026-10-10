# CLAUDE.md — Website Intelligence Crawler (group project)

## What this project is
Internal platform that turns 60,000+ company website URLs into structured business data:
`Import URLs → Crawl & Clean → AI Classification → Review → Export`.
Stack today: Python, FastAPI, SQLAlchemy + SQLite (`data/websites.db`), httpx, BeautifulSoup,
optional Playwright, optional local LLM (Ollama). One server-rendered page in `templates/index.html`.

## Current focus (read this first)
We are working ONLY on the **crawling pipeline** (URL ingestion → validation → discovery → fetching →
extraction/cleaning → crawl persistence). AI classification and UI are out of scope until Phase 3,
and Phase 3 is a written review only (no code).

Work is organised in three phases. Do **not** start the next phase until the user says so.
Full details, deliverables and exit criteria: `docs/phase-plan.md`.

1. Phase 1 — Field-test the EXISTING crawler, unchanged, on a large real-like URL dataset.
2. Phase 2 — Build a production-ready crawler that meets every crawling requirement, then loop
   test → fix → retest on the same dataset until clean; compare against Phase 1.
3. Phase 3 — Write `suggested_improvements.md` for the AI module and UI vs. the requirements.

("Phase" always means these three. The master prompt's own phases are written MP-Phase n.)

## Source of truth (read before acting)
- `docs/crawler-requirements.md` — numbered crawling requirements (CR-IDs). Every PASS/FAIL you
  report must cite CR-IDs.
- `docs/phase-plan.md` — what each phase must produce, report format, severity scale, exit criteria.
- `docs/known-findings.md` — leads from a manual code review. They are HYPOTHESES to confirm or
  refute with evidence, never facts, and must not shape which URLs go into the dataset.
- `docs/source/` — the original requirement documents (requirements proposal, master prompt,
  local-LLM guide). If a CR-ID and a source document ever disagree, the source document wins; tell me.

## Commands (README is authoritative; Windows users use `.venv\Scripts\` instead of `.venv/bin/`)
```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m app.crawler_cli --limit 20        # crawl pending rows
.venv/bin/python -m app.ops report                    # counts of saved rows
.venv/bin/pytest -q                                   # unit tests (all HTTP mocked)
.venv/bin/uvicorn app.main:app --reload               # web UI, http://127.0.0.1:8000
```
Playwright browsers are not installed by default: `.venv/bin/playwright install chromium`.

## Working rules
- Inspect before modifying. Reuse working code. Never edit `.env` secrets into the repo.
- **Phase 1: do not modify anything under `app/`, `templates/`, `tests/`, `scripts/`.** New files go
  only under `crawl_eval/`. Observe the crawler by wrapping/monitoring, never by editing it.
- Report only what you actually ran. Never claim a test or URL passed unless you executed it and
  saw the result. If something could not be tested, mark it NOT TESTED and say why.
- Be polite to real websites: respect robots.txt, one request at a time per domain, modest overall
  concurrency, no login attempts, no CAPTCHA/anti-bot bypass, no vulnerability probing, nothing adult
  or illegal. Start every new dataset with the 100-URL smoke subset.
- Before any material stack change in Phase 2 (PostgreSQL, Redis/Celery, new dependencies), present
  the proposal and wait for approval.
- Stop at every "GATE" in `docs/phase-plan.md` and show me a short summary before continuing.
- Write clearly for non-experts: plain English, short sentences, tables over long prose.
  I write in a mix of English and Roman Urdu; reply in simple English.
