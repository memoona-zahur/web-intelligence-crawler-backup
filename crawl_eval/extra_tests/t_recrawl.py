"""L-08 / B07-B08 / E06: crawl a site successfully, then re-crawl it when it now fails. What do `status`, `crawl_status` and the old `clean_text` look like? Local sites only."""
import asyncio

from common import save, setup

database, tel = setup("recrawl")
from app.crawler import runner
from app.models import Website
from sqlalchemy import select

GOOD, BAD = "http://127.0.0.1:8855/recrawl-test", "http://127.0.0.1:8843/"  # 8843 answers HTTP 500


def snap(wid):
    with database.get_session() as s:
        w = s.get(Website, wid)
        return {"status": w.status, "crawl_status": w.crawl_status, "crawl_error": w.crawl_error, "pages_crawled": w.pages_crawled, "clean_text_chars": len(w.clean_text or ""),
                "content_hash": (w.content_hash or "")[:12], "last_crawled_at": str(w.last_crawled_at)}


async def main():
    with database.get_session() as s:
        s.add(Website(original_url=GOOD, normalized_website=GOOD, status="pending"))
        s.commit()
        wid = s.scalar(select(Website.id))
    out = {"what": "first crawl OK, then the same row is re-crawled after the site starts failing (simulated by pointing the row at an HTTP 500 page)"}
    await runner.run(site_ids=[wid], concurrency=1, log=lambda m: None)
    out["after_first_crawl"] = snap(wid)
    with database.get_session() as s:
        s.get(Website, wid).normalized_website = BAD
        s.commit()
    await runner.run(site_ids=[wid], concurrency=1, force=True, log=lambda m: None)
    out["after_failed_recrawl"] = snap(wid)
    out["reading"] = ("If status says 'failed' while clean_text_chars is unchanged, the row mixes a current failure with old content, "
                      "and the exported crawl status depends on which column a reader looks at (lead L-08).")
    save("t_recrawl", out)

asyncio.run(main())
