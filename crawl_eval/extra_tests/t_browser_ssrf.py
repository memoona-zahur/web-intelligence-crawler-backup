"""B10 / D05 / D06 / L-04: the HTTP path validates every redirect hop; does the BROWSER path? A JavaScript shell on an allowed scenario host sends Chromium to
http://127.0.0.2:8810/secret (this machine only; 127.0.0.2 is NOT on the harness allow-list). Needs the scenario server (port 8861 = this test page)."""
import asyncio

from common import save, setup

database, tel = setup("browser_ssrf")
from app.crawler import runner
from app.models import Website
from sqlalchemy import select

URL = "http://127.0.0.1:8861/"


async def main():
    with database.get_session() as s:
        s.add(Website(original_url=URL, normalized_website=URL, status="pending", source_batch="l04"))
        s.commit()
        wid = s.scalar(select(Website.id))
    await runner.run(site_ids=[wid], concurrency=1, log=lambda m: None)
    with database.get_session() as s:
        w = s.get(Website, wid)
        text = w.clean_text or ""
        res = {"status": w.status, "error": w.crawl_error, "secret_token_in_stored_text": "SECRET-TOKEN-4711" in text, "stored_text_sample": text[:300]}
    res["guard_events_for_site"] = [g for g in tel.guard if g.get("site") == URL]
    res["browser_calls"] = [{k: v for k, v in b.items() if k in ("url", "ms", "returned_bytes", "diag_error")} for b in tel.browser]
    res["http_requests_to_127.0.0.2_seen_by_python"] = [q["url"] for q in tel.requests if "127.0.0.2" in q["url"]]
    res["reading"] = ("If the secret token is stored, the browser followed a redirect to a host that the crawler's guard never checked "
                      "(guard.assert_public_url is called once, before page.goto). Lead L-04 confirmed. The target here is this machine only.")
    save("t_browser_ssrf", res)

asyncio.run(main())
