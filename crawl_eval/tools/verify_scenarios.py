"""Check that every scenario-server site behaves as designed (verification evidence for local-scenario rows).

Reads only the first bytes where bodies are huge. Writes C:/crawl_eval_data/scratch/scenario_verification.json
"""
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scenario_server as S  # noqa: E402

out = {}
for n, (desc, _fn) in S.SCENARIOS.items():
    port = S.BASE + n
    url = f"http://127.0.0.1:{port}/"
    rec = {"desc": desc, "url": url}
    t0 = time.time()
    try:
        with httpx.Client(timeout=httpx.Timeout(6, connect=3)) as c:
            with c.stream("GET", url, follow_redirects=False, headers={"Accept-Encoding": "identity"} if n in (5,) else {}) as r:
                rec["status"] = r.status_code
                rec["headers"] = {k.lower(): v for k, v in r.headers.items() if k.lower() in ("content-type", "content-length", "content-encoding", "location", "retry-after", "refresh")}
                body = b""
                for chunk in r.iter_raw():
                    body += chunk
                    if len(body) > 200_000:
                        rec["read_capped_at"] = len(body)
                        break
                rec["bytes_read"] = len(body)
                rec["sample"] = body[:90].decode("utf-8", errors="replace")
    except httpx.TimeoutException as exc:
        rec["result"] = f"timeout after {round(time.time() - t0, 1)}s ({type(exc).__name__})"
    except Exception as exc:
        rec["result"] = f"error {type(exc).__name__}: {exc}"
    rec["elapsed_s"] = round(time.time() - t0, 1)
    # extra evidence for robots / sitemap scenarios
    if n in (7, 8, 15, 16, 17, 18, 19, 20, 21, 22, 23):
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/robots.txt", timeout=5)
            rec["robots_status"], rec["robots_sample"] = r.status_code, r.text[:80]
        except Exception as exc:
            rec["robots_status"] = f"error {type(exc).__name__}"
    out[port] = rec
    print(port, rec.get("status", rec.get("result")), rec["elapsed_s"], desc[:60])
Path("C:/crawl_eval_data/scratch/scenario_verification.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
