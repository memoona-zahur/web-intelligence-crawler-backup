"""Finding #4 root cause, with evidence.
Part A (59 sites): the plain HTTP page already had text, yet the crawler extracted < 80 characters. WHICH element does the crawler's rule delete?
  One GET per site (harness User-Agent), then the crawler's own constants (extract.DROP_NAME_HINTS) are applied and the deleted elements are listed.
Part B (9 sites): the browser fallback ran but the page had < 80 visible characters at the moment the crawler read it.
  Same page loaded once; text measured (1) right after DOMContentLoaded (what browser.py reads) and (2) after the network is idle.
"""
import asyncio
import json
import re
import sys
from pathlib import Path

from common import save

import httpx
from bs4 import BeautifulSoup
import app.crawler.extract as ex

cand = json.loads(Path("C:/crawl_eval_data/scratch/rootcause_candidates.json").read_text(encoding="utf-8"))
UA = "WebsiteIntelligenceEval/1.0 (academic crawler field test; Lahore)"


def chars(node) -> int:
    return len(re.sub(r"\s+", " ", node.get_text(" ", strip=True)))


def part_a(url: str) -> dict:
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=20, follow_redirects=True)
    except Exception as exc:
        return {"url": url, "error": type(exc).__name__}
    soup = BeautifulSoup(r.content, "lxml")
    for t in soup(["script", "style", "noscript", "template", "svg"]):
        t.decompose()
    total = chars(soup)
    hits = []
    for node in soup.find_all(True):
        if getattr(node, "attrs", None) is None:
            continue
        cls = node.get("class")
        names = " ".join(([cls] if isinstance(cls, str) else list(cls or [])) + [str(node.get("id") or "")]).lower()
        hint = next((h for h in ex.DROP_NAME_HINTS if h in names), None)
        if hint:
            hits.append({"tag": node.name, "hint": hint, "class_or_id": names[:90], "chars_inside": chars(node), "share_of_page_text": round(chars(node) / total, 2) if total else 0})
    hits.sort(key=lambda h: -h["chars_inside"])
    big = [h for h in hits if h["share_of_page_text"] >= 0.5]
    return {"url": str(r.url), "page_visible_chars": total, "crawler_extracted_chars": len(ex.extract_page(r.content, str(r.url))[1]), "elements_matching_name_hints": len(hits),
            "largest_matches": hits[:3], "matches_holding_50pct_or_more_of_the_page_text": len(big), "root_cause": (
                f"a <{big[0]['tag']}> whose class/id contains '{big[0]['hint']}' holds {int(big[0]['share_of_page_text']*100)}% of the text and is deleted with everything inside it" if big else "no single element; several rules together")}


async def part_b(items):
    from playwright.async_api import async_playwright
    out = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        for rid, (url, _h, _r, _b) in items:
            page = await browser.new_page()
            rec = {"row": rid, "url": url}
            try:
                async def route(r):
                    if r.request.resource_type in ("image", "media", "font"):
                        await r.abort()
                    else:
                        await r.continue_()
                await page.route("**/*", route)  # same blocking as the crawler's browser.py
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                html0 = (await page.content()).encode()  # exactly what browser.py returns
                rec["at_domcontentloaded"] = {"html_bytes": len(html0), "crawler_extracted_chars": len(ex.extract_page(html0, url)[1])}
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    rec["networkidle"] = "not reached in 10 s"
                html1 = (await page.content()).encode()
                rec["after_network_idle"] = {"html_bytes": len(html1), "crawler_extracted_chars": len(ex.extract_page(html1, url)[1])}
            except Exception as exc:
                rec["error"] = f"{type(exc).__name__}: {str(exc)[:80]}"
            await page.close()
            out.append(rec)
        await browser.close()
    return out


res = {"part_A_static_text_deleted_by_name_hint_rule": [], "part_B_render_timing": []}
for rid, (site, vis, ext, url) in cand["A"][:14]:
    r = part_a(url)
    r["row"] = rid
    res["part_A_static_text_deleted_by_name_hint_rule"].append(r)
res["part_B_render_timing"] = asyncio.run(part_b(cand["B"]))
a = [x for x in res["part_A_static_text_deleted_by_name_hint_rule"] if x.get("matches_holding_50pct_or_more_of_the_page_text")]
res["summary"] = {"part_A_sites_tested": len(res["part_A_static_text_deleted_by_name_hint_rule"]), "part_A_sites_where_one_matching_element_holds_50pct_or_more_of_the_text": len(a),
                  "part_B_sites_tested": len(res["part_B_render_timing"]),
                  "part_B_sites_where_waiting_for_network_idle_gives_80_plus_chars": sum(1 for x in res["part_B_render_timing"] if x.get("after_network_idle", {}).get("crawler_extracted_chars", 0) >= 80 and x.get("at_domcontentloaded", {}).get("crawler_extracted_chars", 0) < 80)}
save("t_extraction_rootcause", res)
