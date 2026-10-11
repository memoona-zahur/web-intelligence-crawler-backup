"""Confirm JS-heavy candidates: tiny text over plain HTTP, real text after browser rendering.

Independent of app/ code. One page load per site, images/media/fonts blocked, 3 sites at a time.
    python spa_check.py <hosts_file.json>     (list of {"host":..., "url":...})
Output: C:/crawl_eval_data/scratch/spa_check.jsonl (resumable)
"""
import asyncio
import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "C:/crawl_eval_data/browsers")
from playwright.async_api import async_playwright  # noqa: E402

OUT = Path("C:/crawl_eval_data/scratch/spa_check.jsonl")
UA = "WebsiteIntelligenceEval/1.0 (academic crawler field test; Lahore)"


async def check(browser, sem, item):
    async with sem:
        rec = {"host": item["host"], "url": item["url"]}
        try:
            ctx = await browser.new_context(user_agent=UA)
            page = await ctx.new_page()

            async def route(r):
                if r.request.resource_type in ("image", "media", "font"):
                    await r.abort()
                else:
                    await r.continue_()

            await page.route("**/*", route)
            await page.goto(item["url"], wait_until="domcontentloaded", timeout=20000)
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            text = await page.evaluate("document.body ? document.body.innerText : ''")
            rec["rendered_text_len"] = len(re.sub(r"\s+", " ", text).strip())
            rec["rendered_title"] = (await page.title())[:120]
            rec["final_url"] = page.url
            rec["rendered_sample"] = re.sub(r"\s+", " ", text).strip()[:200]
            await ctx.close()
        except Exception as exc:
            rec["error"] = f"{type(exc).__name__}: {str(exc)[:150]}"
        return rec


async def main(path):
    items = json.loads(Path(path).read_text(encoding="utf-8"))
    done = set()
    if OUT.exists():
        done = {json.loads(l)["host"] for l in OUT.read_text(encoding="utf-8").split("\n") if l.strip()}
    todo = [i for i in items if i["host"] not in done]
    print(f"{len(todo)} to render", flush=True)
    sem = asyncio.Semaphore(3)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        tasks = [asyncio.create_task(check(browser, sem, i)) for i in todo]
        with OUT.open("a", encoding="utf-8") as fh:
            for n, coro in enumerate(asyncio.as_completed(tasks), 1):
                rec = await coro
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                if n % 20 == 0:
                    print(f"  {n}/{len(todo)}", flush=True)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
