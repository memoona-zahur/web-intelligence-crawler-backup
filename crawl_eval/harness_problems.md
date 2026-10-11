# Harness problems found while building and smoke-testing (Step 3)

These are mistakes in **my tooling**, not crawler results. They are listed separately on purpose (phase plan §1.4). None changed `app/` code.

| # | Problem | How it was found | Fix | Effect on smoke results |
|---|---|---|---|---|
| H1 | Memory sampler always read 0 MB (64-bit handle truncated in a `ctypes` call) | Self-test showed `peak_rss_mb = 0.0` | Declared handle/argument types | Smoke peak memory is now real (141 MB, Python process only; Chromium not included) |
| H2 | Run-time probe used a **HEAD** request to `https://host` only. Parked pages that only serve `http://`, or answer HEAD differently, were read as "unreachable" → 8 rows wrongly labelled SITE-CHANGED | Smoke results: the crawler reached the same sites with GET and `http://` fallback | Probe replaced by a GET-based, human-style reading (https then http, robots.txt respected), run **after** the crawl and only for rows that did not MATCH (19 rows) | Wrong labels removed; all smoke labels below were produced by the fixed probe |
| H3 | Check "no request to 127.0.0.2" matched the text `127.0.0.2` inside httpbin's *query string* | T0785 failed a check although nothing was sent to that host | Check now compares the request **hostname** | T0785 → MATCH |
| H4 | Probe was compared with JavaScript rows (plain GET cannot see rendered text) → false SITE-CHANGED | T0539 | Probe makes no claim for the JavaScript category | T0539 stays a crawler MISMATCH |
| H5 | SITE-CHANGED was applied even when the crawler's **own telemetry** reproduced the row's premise (robots.txt really answered 500) | T0834 | Overlay skipped when the premise is seen in telemetry (non-200 statuses and robots-5xx only) | T0834 → MISMATCH (crawler fetched the homepage despite robots 5xx) |
| H6 | The real importer **raises** on one malformed line (`http://[invalid`) and imports nothing | First full-dataset import aborted | Harness catches the crash, records it (it is a crawler finding), drops that line, imports the rest | Recorded: batch of 988 rows lost in that attempt |
| H7 | Tooling readers split JSON lines with `str.splitlines()`, which also splits on Unicode separators inside page titles | Probe files looked "damaged" during dataset building (before Step 3) | Readers split on `\n` only | None on smoke |
| H8 | My own UA experiment (run with `-I`) wrote `__pycache__` folders into `app/` | Directory check after the run | Folders deleted; code hashes re-verified (56/56 match) | None (bytecode only) |

## Things that are not bugs but you should know
* **The importer cannot represent ports or paths.** `normalize_website` keeps only `https://host`. The scenario server (`127.0.0.1:88xx`) and httpbin endpoint rows are therefore inserted **directly** into the isolated DB (12 of 94 crawled rows in smoke); the real importer's verdict on the same URLs is still recorded.
* **Safety net:** 0 requests were blocked by the harness safety net in the smoke run (the crawler's own guard stopped every private target). A guard failure would show as `SAFETY_NET_BLOCKED` in `requests.jsonl`.
* **Guard relaxed** only for `127.0.0.1` ports 8800–8860 and 8899.
* The existing test suite had already created an empty `data/` folder in the repo root during Step 0; the harness never opens `data/websites.db`.
* Two **self-test runs** (`harness-selftest_*`, 68 scenario/test-endpoint rows, no real websites) were done before the smoke run. httpbin.org and badssl.com were hit by them, so those two shared test services were visited 3 times in total.
