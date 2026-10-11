"""Pull machine-readable hints out of a page. These support the text; they are not trusted blindly (CR-E04).

Every value is validated (type, length, no markup, no control characters) and keeps its source: the page URL and the kind of markup it came from.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

_INTERESTING = {
    "organization", "localbusiness", "corporation", "store", "product", "service", "offer",
    "professionalservice", "onlinebusiness", "ngo", "educationalorganization", "governmentorganization", "medicalorganization",
    "softwareapplication", "website", "restaurant", "hotel", "financialservice", "legalservice", "realestateagent",
}
_MAX_LINES = 14
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MARKUP = re.compile(r"<[^>]{1,200}>")


def _clean(value: object, limit: int = 300) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = _MARKUP.sub(" ", _CONTROL.sub("", value))
        return " ".join(text.split())[:limit]
    if isinstance(value, dict):
        if "name" in value and isinstance(value.get("name"), str):
            return _clean(value["name"], limit)
        parts = [_clean(value.get(key), 80) for key in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry")]
        return ", ".join(part for part in parts if part)[:limit]
    if isinstance(value, list):
        return ", ".join(c for c in (_clean(item, 80) for item in value) if c)[:limit]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def _types(node: dict) -> list[str]:
    raw = node.get("@type", "")
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if raw:
        return [str(raw)]
    return []


def _valid_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _jsonld_nodes(soup: BeautifulSoup) -> list[dict]:
    nodes: list[dict] = []
    for script in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        raw = script.string or script.get_text() or ""
        if len(raw) > 500_000:
            continue
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, RecursionError):
            continue
        for node in payload if isinstance(payload, list) else [payload]:
            if not isinstance(node, dict):
                continue
            graph = node.get("@graph")
            if isinstance(graph, list):
                nodes.extend(item for item in graph if isinstance(item, dict))
            else:
                nodes.append(node)
    return nodes


def structured_data(html: bytes | str, source_url: str = "") -> list[dict]:
    """Validated items: {kind, type, field, value, source_url}. 'kind' = jsonld | opengraph | meta | canonical."""
    soup = BeautifulSoup(html, "lxml")
    items: list[dict] = []

    def add(kind: str, type_: str, field: str, value: str) -> None:
        if value and len(items) < _MAX_LINES * 2:
            items.append({"kind": kind, "type": type_, "field": field, "value": value, "source_url": source_url})

    for node in _jsonld_nodes(soup):
        types = _types(node)
        if not any(item.lower() in _INTERESTING for item in types):
            continue
        label = types[0]
        for field in ("name", "legalName", "description", "address", "areaServed", "serviceType", "category"):
            value = _clean(node.get(field))
            if field in ("name", "legalName") and len(value) < 2:
                continue
            add("jsonld", label, field, value)
    for prop in ("og:title", "og:description", "og:site_name", "og:type"):
        tag = soup.find("meta", attrs={"property": prop})
        if isinstance(tag, Tag):
            add("opengraph", "", prop, _clean(tag.get("content")))
    desc = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    if isinstance(desc, Tag):
        add("meta", "", "description", _clean(desc.get("content")))
    canonical = soup.find("link", attrs={"rel": re.compile("canonical", re.I)})
    if isinstance(canonical, Tag) and canonical.get("href"):
        href = _clean(canonical.get("href"), 500)
        if _valid_url(href):
            add("canonical", "", "canonical", href)
    return items


def structured_lines(html: bytes | str, source_url: str = "") -> list[str]:
    """Short evidence lines from JSON-LD, Open Graph and the canonical URL (appended to the page text)."""
    lines: list[str] = []
    for item in structured_data(html, source_url):
        if item["kind"] == "jsonld":
            lines.append(f"Structured data ({item['type']}): {item['field']}: {item['value']}")
        elif item["kind"] == "opengraph" and item["field"] in ("og:title", "og:description"):
            lines.append(f"Open Graph {item['field']}: {item['value']}")
        elif item["kind"] == "canonical":
            lines.append(f"Canonical: {item['value']}")
    return lines[:_MAX_LINES]
