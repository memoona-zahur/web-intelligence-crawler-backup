"""Small helpers to describe a whole mocked website (pages, robots, sitemaps, redirects) for end-to-end crawler tests. No network is used."""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import httpx

from app.crawler.pipeline import CrawlResult, crawl_one


def prose(tag: str, sentences: int = 12) -> str:
    """Distinct sentences (the extractor removes repeated lines, so tests must not repeat them)."""
    return "".join(f"<p>{tag} sentence {i}: the company delivers {tag} work for customers in region {i} with documented quality.</p>" for i in range(sentences))


def page(title: str, tag: str | None = None, sentences: int = 12, nav: str = "", extra: str = "") -> str:
    tag = tag or title
    return f"<html><head><title>{title}</title></head><body>{nav}<h1>{title}</h1>{prose(tag, sentences)}{extra}</body></html>"


NAV = ('<nav><a href="/about">About us</a><a href="/services">Our services</a><a href="/products">Products</a>'
       '<a href="/industries">Industries</a><a href="/contact">Contact</a><a href="/blog">Blog</a><a href="/careers">Careers</a></nav>')


class Site:
    """Routes by path (any host) or by 'host/path'. Every request is logged as (host, path)."""

    def __init__(self, robots: str | int | None = None):
        self.routes: dict[str, object] = {}
        self.log: list[tuple[str, str]] = []
        if isinstance(robots, str):
            self.add("/robots.txt", robots)
        elif isinstance(robots, int):
            self.add("/robots.txt", (robots, {}, ""))

    def add(self, path: str, body, status: int = 200, headers: dict | None = None):
        self.routes[path] = body if isinstance(body, tuple) or callable(body) else (status, headers or {}, body)
        return self

    def html(self, path: str, html: str):
        return self.add(path, html, headers={"content-type": "text/html; charset=utf-8"})

    def redirect(self, path: str, location: str, status: int = 302):
        return self.add(path, "", status=status, headers={"location": location})

    @property
    def paths(self) -> list[str]:
        return [p for _h, p in self.log]

    def fetched(self) -> list[str]:
        return [p for p in self.paths if p not in ("/robots.txt",) and not p.endswith(".xml") and not p.endswith(".gz")]

    def handler(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        self.log.append((host, path))
        route = self.routes.get(f"{host}{path}") or self.routes.get(path)
        if callable(route):
            return route(request)
        if route is None:
            return httpx.Response(404, text="not found", request=request)
        status, headers, body = route
        headers = dict(headers)
        if isinstance(body, str) and "content-type" not in {k.lower() for k in headers}:
            headers["content-type"] = "text/html; charset=utf-8" if body.lstrip().startswith("<") else "text/plain"
        return httpx.Response(status, headers=headers, content=body.encode() if isinstance(body, str) else body, request=request)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


def crawl(site: Site, url: str = "https://acme.com", cache: dict | None = None) -> CrawlResult:
    async def go():
        async with site.client() as client:
            return await crawl_one(client, url, {} if cache is None else cache)

    return asyncio.run(go())


def standard_site(robots: str | int | None = None, sentences: int = 12) -> Site:
    """Home + About + Services + Products + Industries + Contact + Blog + Careers."""
    site = Site(robots)
    site.html("/", page("Acme Robotics", nav=NAV, sentences=sentences))
    site.html("/about", page("About Acme", sentences=sentences))
    site.html("/services", page("Acme Services", sentences=sentences))
    site.html("/products", page("Acme Products", sentences=sentences))
    site.html("/industries", page("Industries We Serve", sentences=sentences))
    site.html("/contact", page("Contact Acme", sentences=sentences))
    site.html("/blog", page("Acme Blog", sentences=sentences))
    site.html("/careers", page("Acme Careers", sentences=sentences))
    return site
