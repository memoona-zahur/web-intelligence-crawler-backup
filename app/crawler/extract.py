"""Turn raw HTML into the clean text stored per page and in Websites.clean_text (CR-D03, E01-E05, E10).

Fixes against Phase 1:
- a class name such as 'has-sidebar' or 'cookie-notice-visible' on <body>/<html>/a page wrapper no longer deletes the whole page (ISS-05):
  name hints match whole words, never apply to html/body/main/article, and never to a container that holds most of the page text;
  if the result is still tiny while the page clearly has text, the page is re-read without name hints
- <form> wrappers around a whole page (ASP.NET) are unwrapped, not deleted; <header> is kept when it holds the page headline
- tables, h4-h6, definition lists and plain <div> text blocks are kept
- the character set is detected from the bytes when the header lies (ISS-26)
"""

from __future__ import annotations

import codecs
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag
from charset_normalizer import from_bytes

# Boilerplate that never helps classify a business. (header and form get special handling below.)
DROP_TAGS = [
    "script", "style", "noscript", "svg", "canvas", "iframe", "frame",
    "form", "button", "input", "select", "textarea", "nav", "header",
    "footer", "aside", "template", "dialog", "object", "embed",
]
_ALWAYS_DROP = ("script", "style", "noscript", "svg", "canvas", "iframe", "frame", "button", "input", "select", "textarea",
                "nav", "footer", "aside", "template", "dialog", "object", "embed", "head")

# Names of overlays and site chrome. Matched against whole words of class and id (see _tokens).
DROP_NAME_HINTS = (
    "cookie", "consent", "gdpr", "popup", "modal", "newsletter",
    "subscription", "sidebar", "breadcrumb", "skip-link",
)
_NOISE_WORDS = {
    "cookie", "cookies", "cookiebar", "cookiebanner", "cookienotice", "cookieconsent", "consent", "gdpr", "ccpa", "cmp", "onetrust",
    "popup", "popups", "modal", "modals", "lightbox", "overlay", "newsletter", "subscribe", "subscription", "sidebar", "sidebars",
    "breadcrumb", "breadcrumbs", "skiplink", "skip", "usercentrics", "cookielaw", "ot-sdk-container",
}
_PROTECTED_TAGS = {"html", "body", "main", "article"}

# Structural elements worth keeping, in document order.
KEEP_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "dd", "dt", "td", "th", "blockquote", "figcaption", "summary", "address", "pre")
KEEP_SELECTOR = ", ".join(KEEP_TAGS)
_BLOCK_TAGS = {"div", "p", "ul", "ol", "table", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6", "li", "dl", "form", "main", "blockquote"}

_WS = re.compile(r"\s+")
_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")
_META_CHARSET = re.compile(rb"<meta[^>]+charset\s*=\s*[\"']?\s*([\w\-:.]+)", re.I)
_XML_ENCODING = re.compile(rb"^\s*<\?xml[^>]*encoding=[\"']([\w\-]+)", re.I)
_HEADER_CHARSET = re.compile(r"charset\s*=\s*[\"']?([\w\-:.]+)", re.I)
_BOMS = (
    (codecs.BOM_UTF32_LE, "utf-32"), (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"), (codecs.BOM_UTF16_LE, "utf-16"), (codecs.BOM_UTF16_BE, "utf-16"),
)


@dataclass
class Extracted:
    title: str
    text: str
    visible_chars: int = 0          # characters of visible text on the page before cleaning
    kept_chars: int = 0
    encoding: str = ""
    method: str = "html-text"
    used_fallback: bool = False
    meta_description: str = ""
    headings: list[str] = field(default_factory=list)
    canonical: str = ""
    lang: str = ""

    @property
    def dropped_chars(self) -> int:
        return max(0, self.visible_chars - self.kept_chars)


def _clean_line(text: str) -> str:
    return _WS.sub(" ", text).strip()


def decode_html(data: bytes, content_type: str | None = None) -> tuple[str, str]:
    """Bytes -> (text, encoding). BOM, then valid UTF-8, then the declared charset, then detection from the bytes (ISS-26)."""
    for bom, encoding in _BOMS:
        if data.startswith(bom):
            return data.decode(encoding, errors="replace"), encoding
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    declared: list[str] = []
    if content_type:
        m = _HEADER_CHARSET.search(content_type)
        if m:
            declared.append(m.group(1))
    head = data[:4096]
    for pattern in (_META_CHARSET, _XML_ENCODING):
        m = pattern.search(head)
        if m:
            declared.append(m.group(1).decode("ascii", errors="ignore"))
    for name in declared:
        try:
            return data.decode(name), name.lower()
        except (UnicodeDecodeError, LookupError):
            continue
    best = from_bytes(data[:300_000]).best()
    if best is not None:
        try:
            return data.decode(best.encoding, errors="replace"), best.encoding
        except (UnicodeDecodeError, LookupError):
            pass
    return data.decode("utf-8", errors="replace"), "utf-8-replace"


def _tokens(node: Tag) -> set[str]:
    """Whole words of class and id: 'has-sidebar cookie_notice' -> {has, sidebar, cookie, notice, cookienotice, has-sidebar...}."""
    value = node.get("class")
    classes = [value] if isinstance(value, str) else [str(item) for item in (value or [])]
    words: set[str] = set()
    for name in classes + [str(node.get("id") or "")]:
        low = name.lower()
        parts = [p for p in _TOKEN_SPLIT.split(low) if p]
        words.update(parts)
        words.add("".join(parts))                              # cookie-notice -> cookienotice
        words.update("".join(parts[i:i + 2]) for i in range(len(parts) - 1))   # adjacent pairs: cookie+banner
    return words


def _looks_like_content(node: Tag) -> bool:
    return bool(node.find(["h1", "h2", "h3"])) or len(node.find_all("p")) >= 2 or len(node.find_all("li")) >= 3 or len(node.find_all(["div", "section", "article", "main"])) >= 2


def _visible_len(node: Tag) -> int:
    return len(_clean_line(node.get_text(" ", strip=True)))


def _drop_noise(soup: BeautifulSoup, use_name_hints: bool = True) -> None:
    for tag_name in _ALWAYS_DROP:
        for node in soup.find_all(tag_name):
            node.decompose()

    # <header> holds site chrome, but some themes put the page headline in it: keep it when it contains an <h1>.
    for node in soup.find_all("header"):
        if not node.find("h1"):
            node.decompose()
    # <form>: a small form (inputs, little text) is noise; a form that wraps the page (ASP.NET) is unwrapped.
    for node in soup.find_all("form"):
        if node.attrs is None:
            continue
        if _visible_len(node) < 1500 and node.find(["input", "textarea", "select"]):
            node.decompose()
        else:
            node.unwrap()

    if not use_name_hints:
        return
    total = _visible_len(soup.body) if soup.body else _visible_len(soup)
    # Collect first, then remove. Decomposing while iterating can leave half-removed nodes whose attrs are None.
    to_drop: list[Tag] = []
    for node in soup.find_all(True):
        if not isinstance(node, Tag) or node.attrs is None or node.name in _PROTECTED_TAGS:
            continue
        if node.get("role") == "main":
            continue
        if not (_tokens(node) & _NOISE_WORDS):
            continue
        # a wrapper that holds most of the page text AND looks like content (headings, several paragraphs or list items) is the page,
        # not a banner (ISS-05). A banner is typically one short paragraph.
        if _visible_len(node) > 0.5 * total and _looks_like_content(node):
            continue
        to_drop.append(node)
    for node in to_drop:
        if node.attrs is not None:
            node.decompose()


def _row_text(row: Tag) -> str:
    cells = [_clean_line(c.get_text(" ", strip=True)) for c in row.find_all(["td", "th"], recursive=False)]
    return " | ".join(c for c in cells if c)


def _collect_lines(soup: BeautifulSoup) -> list[str]:
    parts: list[str] = []
    seen: set[str] = set()

    def add(line: str) -> None:
        if len(line) < 3:
            return
        key = line.lower()
        if key in seen:
            return
        seen.add(key)
        parts.append(line)

    keep_tags = set(KEEP_TAGS) - {"td", "th"}
    for node in soup.select(KEEP_SELECTOR + ", tr, div, span"):
        if not isinstance(node, Tag) or node.attrs is None:
            continue
        if node.name == "tr":
            if not node.find_parent("tr"):
                add(_row_text(node))
            continue
        if node.name in ("td", "th"):
            continue  # handled through their row
        if node.name in ("div", "span"):
            # a plain text block: only leaf blocks that are not already inside a kept element
            if len(node.get_text(strip=True)) < 40 or node.find(list(_BLOCK_TAGS)) or node.find_parent(list(keep_tags | {"tr"})):
                continue
        add(_clean_line(node.get_text(" ", strip=True)))
    return parts


def extract_detailed(html: bytes | str, url: str = "", content_type: str | None = None) -> Extracted:
    if isinstance(html, bytes):
        markup, encoding = decode_html(html, content_type)
    else:
        markup, encoding = html, "str"
    soup = BeautifulSoup(markup, "lxml")

    title = _clean_line(soup.title.get_text(" ", strip=True)) if soup.title else ""
    meta = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    meta_description = _clean_line(str(meta.get("content", ""))) if isinstance(meta, Tag) else ""
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if not title and isinstance(og_title, Tag):
        title = _clean_line(str(og_title.get("content", "")))
    canonical_tag = soup.find("link", attrs={"rel": re.compile("canonical", re.I)})
    canonical = str(canonical_tag.get("href", "")).strip() if isinstance(canonical_tag, Tag) else ""
    html_tag = soup.find("html")
    lang = str(html_tag.get("lang", "")).strip() if isinstance(html_tag, Tag) else ""

    for node in soup(["script", "style", "noscript", "template", "svg", "canvas"]):
        node.decompose()
    visible = _visible_len(soup.body) if soup.body else _visible_len(soup)
    snapshot = str(soup)  # untouched copy: the second reading (without name hints) must start from the full page

    def run(use_hints: bool) -> list[str]:
        local = soup if use_hints else BeautifulSoup(snapshot, "lxml")
        _drop_noise(local, use_name_hints=use_hints)
        return _collect_lines(local)

    parts = run(True)
    text_len = sum(len(p) for p in parts)
    used_fallback = False
    if text_len < 200 and visible >= max(400, 3 * text_len):
        # The cleaning removed nearly everything from a page that clearly has text: read it again without name hints.
        retry = run(False)
        if sum(len(p) for p in retry) > text_len:
            parts, used_fallback = retry, True

    lines = []
    if meta_description:
        lines.append(meta_description)
    lines.extend(p for p in parts if p.lower() != meta_description.lower())
    text = "\n".join(lines)

    if len(text) < 80:
        # Layout-heavy page: fall back to the whole body text.
        body = soup.body or soup
        fallback = "\n".join(line for line in (_clean_line(x) for x in body.get_text("\n").splitlines()) if line)
        if len(fallback) > len(text):
            text, used_fallback = fallback, True

    try:
        headings = [_clean_line(h.get_text(" ", strip=True)) for h in soup.find_all(["h1", "h2"])][:12]
    except Exception:  # noqa: BLE001 - headings are a bonus, never a reason to fail a page
        headings = []
    return Extracted(
        title=title, text=text, visible_chars=visible, kept_chars=len(text), encoding=encoding,
        method="html-text-fallback" if used_fallback else "html-text", used_fallback=used_fallback,
        meta_description=meta_description, headings=[h for h in headings if h], canonical=canonical, lang=lang,
    )


def extract_page(html: bytes | str, url: str = "", content_type: str | None = None) -> tuple[str, str]:
    """Return (title, clean_text) for one page.

    Keeps the page title, meta description and the heading/paragraph/list/table text; drops scripts, navigation, footers and cookie banners.
    Lines that repeat on the page are removed.
    """
    result = extract_detailed(html, url, content_type)
    return result.title, result.text
