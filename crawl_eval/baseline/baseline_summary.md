# Baseline summary (Step 0)

All numbers below come from commands I actually ran on 2026-10-10.

| Item | Result |
|---|---|
| Git commit (local repo, created by me) | `24818a603f2fba198ee9447e027c0cdab06c475a` |
| Git tag | `crawler-baseline-v1` |
| Code hash manifest | 56 files (app, templates, tests, scripts), combined SHA-256 `59e787ea…deafb1` |
| Hash check after running all tests | OK – 56 files match |
| `git status` after tests | only `crawl_eval/` is new; no code changed |
| Python | 3.14.6 (all requirements installed; Python 3.12 fallback not needed) |
| Playwright Chromium | installed (Chrome for Testing 153.0.8010.12) |
| Network location | Lahore, Pakistan (stated by user) |

## Tests: README claim vs. reality (lead L-22, CR-J04)

| Claim | README says | Measured |
|---|---|---|
| Tests passed | 108 | **154 passed, 0 failed, 0 skipped** |
| Crawler statement coverage (`app.crawler` + `app.crawler_cli`) | 100% | **91%** (775 statements, 70 missed) |
| Whole `app/` coverage | not claimed | 88% (2009 statements, 246 missed) |

Least covered crawler files: `browser.py` 50% (the real Playwright path is never run by tests),
`structured.py` 79%, `sitemap.py` 83%, `runner.py` 87%. `app/ops.py` is 0% covered.
README's "108 passed / 100% coverage" is therefore **wrong on both counts** (cosmetic documentation issue).
The test run shows ~150 `ResourceWarning: unclosed database` warnings (SQLite connections not closed) – to be logged as a minor issue.

## Notes
- Git was created by me (`git init`); the folder was not a repo before. Commit contains the original files only.
  Git reports LF→CRLF line-ending warnings; this affects only how git stores text, the working files were not changed.
- Venv, run databases, browsers and coverage files live in `C:\crawl_eval_data\` (outside OneDrive), as requested.
- Raw output: `pytest_output.txt`, `coverage_crawler.txt`, `coverage_app.txt`, `pip_freeze.txt`, `environment.json`.
