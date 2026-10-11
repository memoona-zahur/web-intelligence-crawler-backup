"""Find candidate pages from robots.txt and sitemap files (CR-C08).

The sitemap is not crawled page by page. It only supplies URLs, which the focused ranker then accepts or rejects.
Safety: a sitemap is untrusted. Compressed files are expanded with a hard size limit (a gzip bomb is rejected, not expanded), and any file with a
DOCTYPE or entity declaration is refused, so entity-expansion ("billion laughs") files never reach the XML parser.
"""

from __future__ import annotations

import re
import zlib
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx

from app.crawler import config
from app.crawler.fetcher import FetchError, RobotsRules, fetch_page
from app.crawler.guard import GuardError
from app.domains import registrable_domain

COMMON_LOCATIONS = ("/sitemap.xml", "/sitemap_index.xml", "/sitemap.xml.gz", "/wp-sitemap.xml", "/sitemap/sitemap.xml")
MAX_LOCS_PER_FILE = 60_000
_DANGEROUS = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.I)


def _same_site(url: str, base_host: str) -> bool:
    return registrable_domain(url) == registrable_domain(base_host)


def _gunzip_bounded(content: bytes) -> bytes | None:
    """Expand gzip data, at most SITEMAP_MAX_BYTES. None = too big (a bomb) or damaged."""
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        out = decompressor.decompress(content, config.SITEMAP_MAX_BYTES + 1)
    except zlib.error:
        return None
    if len(out) > config.SITEMAP_MAX_BYTES or decompressor.unconsumed_tail:
        return None
    return out


def parse_sitemap(content: bytes) -> tuple[str, list[str]]:
    """Return ('index'|'urlset'|'invalid', locations)."""
    if content[:2] == b"\x1f\x8b":
        expanded = _gunzip_bounded(content)
        if expanded is None:
            return "invalid", []
        content = expanded
    if len(content) > config.SITEMAP_MAX_BYTES or _DANGEROUS.search(content[:20_000]):
        return "invalid", []
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError:
        return "invalid", []

    tag = root.tag.rsplit("}", 1)[-1].lower()
    locs: list[str] = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1].lower() == "loc" and node.text:
            locs.append(node.text.strip())
            if len(locs) >= MAX_LOCS_PER_FILE:
                break
    if tag == "sitemapindex":
        return "index", locs
    if tag == "urlset":
        return "urlset", locs
    return "invalid", []


async def sitemap_urls(
    client: httpx.AsyncClient,
    robots: RobotsRules,
    origin: str,
    base_host: str,
) -> list[str]:
    """Collect same-site page URLs from a bounded number of sitemap files."""
    seeds = [s for s in robots.site_maps() if _same_site(s, base_host)]
    explicit = bool(seeds)
    if not seeds:
        seeds = [f"{origin}{path}" for path in COMMON_LOCATIONS]

    queue = list(seeds)
    seen_files: set[str] = set()
    found: list[str] = []
    seen_pages: set[str] = set()
    fetched = 0

    while queue and fetched < config.MAX_SITEMAPS and len(found) < config.MAX_SITEMAP_URLS * 25:
        sitemap = queue.pop(0)
        if sitemap in seen_files or not robots.allowed(sitemap):
            continue
        seen_files.add(sitemap)
        fetched += 1
        try:
            result = await fetch_page(client, sitemap, expect_html=False)
        except (FetchError, GuardError):
            continue
        kind, locs = parse_sitemap(result.content)
        if kind == "index":
            for loc in locs:
                if loc not in seen_files and _same_site(loc, base_host):
                    queue.append(loc)
            continue
        if kind != "urlset":
            continue
        for loc in locs:
            if not _same_site(loc, base_host) or loc in seen_pages:
                continue
            seen_pages.add(loc)  # robots rules are applied to the pages that are actually chosen, not to every sitemap entry
            found.append(loc)
        if found and not explicit:
            break  # a common location worked: no need to probe the others
    return found
