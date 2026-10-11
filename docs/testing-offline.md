# Tests run offline — and the suite proves it (CR-J03)

The unit, fixture and scenario tests must never reach a real website. Since 2026-10-11 this is enforced, not just intended.

**What enforces it.** `tests/conftest.py` installs a socket guard (`tests/netguard/sitecustomize.py`) in the pytest process and puts its folder on
`PYTHONPATH`, so every Python child process that a test starts loads it too. Anything that is not local — a connection to a non-loopback
address, or a DNS lookup of a real name — raises `NetworkLeak` **and** is written to a log file, so the attempt is recorded even if the code under
test catches the exception. Allowed: `127.0.0.0/8`, `::1`, `localhost`, Unix sockets. At the end of the run the terminal shows
`socket guard on: N non-local network attempt(s) blocked`, and a non-empty log turns an otherwise green run into a failed one.

**The command** (nothing extra to do — the guard is part of the normal run):

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = "C:/crawl_eval_data/browsers"        # only needed for the real-Chromium tests (local servers)
C:\crawl_eval_data\venv2\Scripts\python.exe -B -m pytest -q          # prints "socket guard on: 0 non-local network attempt(s) blocked"
```

Log file: `%TEMP%\crawler_netguard.log` (override with `NETGUARD_LOG`). Switch the guard off only for a deliberate experiment: `NETGUARD=off`
(the summary then says OFF). A PostgreSQL test database on this machine (`localhost`) is allowed; a remote database would be blocked on purpose.

**What the guard does not see.** The Chromium process of the browser tests makes its own connections. Those tests use two local servers and start
Chromium with a dead proxy, and every request is routed through our guarded client, but there is no operating-system level proof.

**Why it exists.** The first guarded run of the Phase 2 suite found two DNS lookups: one in an original Phase 1 test that reached the real browser
path, and one in the harness-contract tool. Both were fixed (the pipeline's browser is now disabled for every test unless a test patches it).

## Mapping of the original tests (integrity check)
`tests/` was compared with tag `crawler-baseline-v1`: 154 original tests = 147 unchanged + 3 modified + 4 renamed. Running the ORIGINAL `tests/`
folder (its own conftest and helpers) against the new code gives 147 passed and exactly 7 failed — the 3 modified and 4 renamed tests. The list with
reasons and replacements is in `docs/phase2-progress.md`.
