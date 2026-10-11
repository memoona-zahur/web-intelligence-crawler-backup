"""Local scenario server: behaviours the live internet cannot give us reliably or safely.

Each scenario is its own "site" on its own port (robots.txt is per origin), bound to 127.0.0.1 ONLY.
Start:   python crawl_eval/scenario_server.py            (runs until Ctrl-C)
List:    python crawl_eval/scenario_server.py --list

Safety: the only "private target" used is 127.0.0.1/127.0.0.2 on this machine, never anyone's network.
Sizes are capped (bombs are 60-150 MB when expanded) so a crawler with no limits hurts only this PC briefly.
"""
from __future__ import annotations

import gzip
import io
import random
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE = 8800  # scenario ports are BASE + n
LOREM = ("We design and build industrial pumps and compressors for water treatment, mining and food processing "
         "customers across Europe and Asia. Our engineers provide installation, maintenance and training services. ")


def page(title: str, body: str, links: list[tuple[str, str]] | None = None, head: str = "") -> bytes:
    nav = "".join(f'<li><a href="{h}">{t}</a></li>' for h, t in (links or []))
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{title}</title>{head}</head>"
            f"<body><nav><ul>{nav}</ul></nav><main><h1>{title}</h1><p>{body}</p></main></body></html>").encode()


def business_site(prefix: str = "") -> dict[str, bytes]:
    nav = [(f"{prefix}/about", "About us"), (f"{prefix}/services", "Services"), (f"{prefix}/products", "Products")]
    return {
        "/": page("Acme Pumps", LOREM * 2, nav),
        "/about": page("About Acme Pumps", "Acme Pumps was founded in 1990. " + LOREM * 2, nav),
        "/services": page("Services", "Installation and maintenance. " + LOREM * 2, nav),
        "/products": page("Products", "Centrifugal pumps and screw compressors. " + LOREM * 2, nav),
    }


# ---- scenario handlers: fn(h, path, query) -> None (must write the response itself) -------------------------
def send(h, status=200, body=b"", ctype="text/html; charset=utf-8", headers=None):
    h.send_response(status)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(body)))
    for k, v in (headers or {}).items():
        h.send_header(k, v)
    h.end_headers()
    if h.command != "HEAD":
        h.wfile.write(body)


def serve_pages(pages):
    def fn(h, path, q):
        if path == "/robots.txt":
            return send(h, 404, b"no robots", "text/plain")
        body = pages.get(path.rstrip("/") or "/")
        return send(h, 200, body) if body else send(h, 404, page("Not found", "No such page here for this site."))
    return fn


def robots_site(robots_body: str | int, pages=None):
    pages = pages or business_site()

    def fn(h, path, q):
        if path == "/robots.txt":
            if isinstance(robots_body, int):
                return send(h, robots_body, b"server error", "text/plain")
            return send(h, 200, robots_body.encode(), "text/plain" if not robots_body.startswith("<") else "text/html")
        body = pages.get(path.rstrip("/") or "/")
        return send(h, 200, body) if body else send(h, 404, page("Not found", "No such page for this site."))
    return fn


def slow_drip(h, path, q):
    if path == "/robots.txt":
        return send(h, 404, b"", "text/plain")
    h.send_response(200)
    h.send_header("Content-Type", "text/html")
    h.end_headers()
    try:
        h.wfile.write(b"<html><body><p>")
        for _ in range(240):  # 2 minutes, one byte per half second
            h.wfile.write(b"x")
            h.wfile.flush()
            time.sleep(0.5)
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass


def hang(h, path, q):
    if path == "/robots.txt":
        return send(h, 404, b"", "text/plain")
    time.sleep(60)  # accept the request, never answer within any sane timeout


def slow_headers(h, path, q):
    if path == "/robots.txt":
        return send(h, 404, b"", "text/plain")
    time.sleep(20)
    send(h, 200, business_site()["/"])


def huge_body(h, path, q):
    if path == "/robots.txt":
        return send(h, 404, b"", "text/plain")
    h.send_response(200)
    h.send_header("Content-Type", "text/html")
    h.end_headers()  # no Content-Length: size is only known by reading
    chunk = b"<p>" + b"filler text for a very large page " * 30 + b"</p>\n"
    try:
        h.wfile.write(b"<html><head><title>Huge</title></head><body>")
        for _ in range(60_000_000 // len(chunk)):
            h.wfile.write(chunk)
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass


def gzip_bomb_big(h, path, q):
    """TEST ONLY: 600 MB when expanded (4x the dataset bomb) to show how memory scales with the input."""
    if path == "/robots.txt":
        return send(h, 404, b"", "text/plain")
    raw = io.BytesIO()
    with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=1) as z:
        z.write(b"<html><head><title>Bomb</title></head><body><p>")
        block = b"A" * 1_000_000
        for _ in range(600):
            z.write(block)
        z.write(b"</p></body></html>")
    send(h, 200, raw.getvalue(), headers={"Content-Encoding": "gzip"})


def gzip_bomb_page(h, path, q):
    if path == "/robots.txt":
        return send(h, 404, b"", "text/plain")
    raw = io.BytesIO()
    with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9) as z:
        z.write(b"<html><head><title>Bomb</title></head><body><p>")
        block = b"A" * 1_000_000
        for _ in range(150):
            z.write(block)
        z.write(b"</p></body></html>")
    send(h, 200, raw.getvalue(), headers={"Content-Encoding": "gzip"})


def sitemap_bomb(h, path, q):
    if path == "/robots.txt":
        return send(h, 200, f"User-agent: *\nAllow: /\nSitemap: http://127.0.0.1:{BASE + 7}/sitemap.xml.gz\n".encode(), "text/plain")
    if path == "/sitemap.xml.gz":
        raw = io.BytesIO()
        with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9) as z:
            z.write(b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
            line = b"<url><loc>http://127.0.0.1:%d/p/%s</loc></url>\n"
            for i in range(1_000_000):
                z.write(line % (BASE + 7, b"x" * 40 + str(i).encode()))
            z.write(b"</urlset>")
        return send(h, 200, raw.getvalue(), "application/gzip")
    pages = business_site()
    body = pages.get(path.rstrip("/") or "/")
    send(h, 200, body) if body else send(h, 404, page("Not found", "No such page here."))


def entity_sitemap(h, path, q):
    if path == "/robots.txt":
        return send(h, 200, f"User-agent: *\nSitemap: http://127.0.0.1:{BASE + 8}/sitemap.xml\n".encode(), "text/plain")
    if path == "/sitemap.xml":
        xml = ('<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY a "aaaaaaaaaa">'
               '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;"><!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">'
               '<!ENTITY d "&c;&c;&c;&c;&c;&c;&c;&c;&c;&c;"><!ENTITY e "&d;&d;&d;&d;&d;&d;&d;&d;&d;&d;">]>'
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>http://127.0.0.1:%d/&e;</loc></url></urlset>' % (BASE + 8))
        return send(h, 200, xml.encode(), "application/xml")
    pages = business_site()
    body = pages.get(path.rstrip("/") or "/")
    send(h, 200, body) if body else send(h, 404, page("Not found", "No such page here."))


def redirect_loop(h, path, q):
    if path == "/robots.txt":
        return send(h, 404, b"", "text/plain")
    target = "/b" if path != "/b" else "/a"
    send(h, 302, b"", headers={"Location": target})


def redirect_chain(h, path, q):
    if path == "/robots.txt":
        return send(h, 404, b"", "text/plain")
    parts = path.strip("/").split("/")
    n = int(parts[1]) if len(parts) == 2 and parts[0] == "hop" and parts[1].isdigit() else 0
    if path == "/final":
        return send(h, 200, business_site()["/"])
    send(h, 301, b"", headers={"Location": f"/hop/{n + 1}" if n < 8 else "/final"})


def redirect_to_loopback(h, path, q):
    """Public-looking page that redirects to a 'secret' page on another loopback address (our own machine)."""
    if path == "/robots.txt":
        return send(h, 404, b"", "text/plain")
    if path == "/secret":
        return send(h, 200, page("INTERNAL SECRET", "This internal-only text must never appear in crawl output. SECRET-TOKEN-4711 " + LOREM))
    send(h, 302, b"", headers={"Location": f"http://127.0.0.2:{BASE + 10}/secret"})


def meta_refresh(h, path, q):
    if path == "/robots.txt":
        return send(h, 404, b"", "text/plain")
    if path == "/real":
        return send(h, 200, business_site()["/"])
    send(h, 200, b"<html><head><meta http-equiv='refresh' content='0; url=/real'><title>Redirecting</title></head><body>Redirecting...</body></html>")


def js_redirect(h, path, q):
    if path == "/robots.txt":
        return send(h, 404, b"", "text/plain")
    if path == "/real":
        return send(h, 200, business_site()["/"])
    send(h, 200, b"<html><head><title>Loading</title><script>window.location.href='/real';</script></head><body></body></html>")


def redirect_to_login(h, path, q):
    if path == "/robots.txt":
        return send(h, 404, b"", "text/plain")
    if path == "/login":
        return send(h, 200, b"<html><head><title>Sign in</title></head><body><h1>Sign in</h1><form><input name=u><input type=password name=p><button>Log in</button></form></body></html>")
    send(h, 302, b"", headers={"Location": "/login?next=/"})


def calendar_trap(h, path, q):
    if path == "/robots.txt":
        return send(h, 404, b"", "text/plain")
    parts = path.strip("/").split("/")
    if parts[0] == "cal" and len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
        y, m = int(parts[1]), int(parts[2])
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        py, pm = (y - 1, 12) if m == 1 else (y, m - 1)
        return send(h, 200, page(f"Events {y}-{m:02d}", "No events this month, but see the calendar. " + LOREM,
                                 [(f"/cal/{ny}/{nm:02d}", "Next month"), (f"/cal/{py}/{pm:02d}", "Previous month")]))
    send(h, 200, page("Acme Pumps", LOREM * 2, [("/cal/2024/01", "Events calendar"), ("/about", "About us")]))


def session_trap(h, path, q):
    if path == "/robots.txt":
        return send(h, 404, b"", "text/plain")
    sid = random.randint(10**8, 10**9)
    send(h, 200, page("Acme Pumps", LOREM * 2,
                      [(f"/about?sid={sid}", "About us"), (f"/services?sid={sid + 1}", "Services"), (f"/products?sid={sid + 2}", "Products")]))


def faceted_trap(h, path, q):
    if path == "/robots.txt":
        return send(h, 404, b"", "text/plain")
    colors = ["red", "blue", "green", "black", "white"]
    sizes = ["s", "m", "l", "xl"]
    links = [(f"/products?color={c}&size={s}&page={p}", f"{c} {s} {p}") for c in colors for s in sizes for p in (1, 2)]
    send(h, 200, page("Shop products", LOREM * 2, links + [("/about", "About us")]))


def deep_chain(h, path, q):
    if path == "/robots.txt":
        return send(h, 404, b"", "text/plain")
    n = int(path.strip("/").split("/")[-1]) if path.startswith("/depth/") and path.strip("/").split("/")[-1].isdigit() else 0
    send(h, 200, page(f"Level {n}", LOREM * 2, [(f"/depth/{n + 1}", f"Next level {n + 1}")]))


def charset_latin1(h, path, q):
    if path == "/robots.txt":
        return send(h, 404, b"", "text/plain")
    body = "<html><head><title>Café Müller - Über uns</title></head><body><h1>Café Müller</h1><p>Wir bieten frische Backwaren, Kaffee und Frühstück für Familien in München. Öffnungszeiten: täglich. Größere Bestellungen für Büros und Feste möglich.</p></body></html>"
    send(h, 200, body.encode("latin-1"), "text/html")  # no charset anywhere


def charset_sjis_wrong_header(h, path, q):
    if path == "/robots.txt":
        return send(h, 404, b"", "text/plain")
    body = "<html><head><title>株式会社テスト</title></head><body><h1>株式会社テスト</h1><p>私たちは産業用ポンプと圧縮機の設計、製造、保守を行っています。水処理、鉱業、食品加工のお客様に長年サービスを提供しています。</p></body></html>"
    send(h, 200, body.encode("shift_jis"), "text/html; charset=utf-8")  # header lies


def charset_bom(h, path, q):
    if path == "/robots.txt":
        return send(h, 404, b"", "text/plain")
    send(h, 200, b"\xef\xbb\xbf" + page("BOM page", LOREM * 2), "text/html")


def charset_utf16(h, path, q):
    if path == "/robots.txt":
        return send(h, 404, b"", "text/plain")
    send(h, 200, ("<html><head><title>UTF16</title></head><body><p>" + LOREM * 2 + "</p></body></html>").encode("utf-16"), "text/html")


def sitemap_malformed(h, path, q):
    if path == "/robots.txt":
        return send(h, 200, f"User-agent: *\nSitemap: http://127.0.0.1:{BASE + 15}/sitemap.xml\n".encode(), "text/plain")
    if path == "/sitemap.xml":
        return send(h, 200, b"<?xml version='1.0'?><urlset><url><loc>http://127.0.0.1/about</loc></url><url><loc>BROKEN", "application/xml")
    pages = business_site()
    body = pages.get(path.rstrip("/") or "/")
    send(h, 200, body) if body else send(h, 404, page("Not found", "No such page here."))


def sitemap_index_nonstandard(h, path, q):
    p = BASE + 16
    pages = {
        "/": page("Northwind Systems", "We help companies run their operations. " + LOREM, [("/careers", "Careers"), ("/blog", "Blog")]),
        "/what-we-do": page("What we do", "We deliver industrial automation and maintenance services. " + LOREM * 2),
        "/who-we-serve": page("Who we serve", "Water utilities, mines and food processors. " + LOREM * 2),
        "/blog": page("Blog", "Latest news. " + LOREM),
        "/careers": page("Careers", "Join our team. " + LOREM),
    }
    if path == "/robots.txt":
        return send(h, 200, f"User-agent: *\nAllow: /\nSitemap: http://127.0.0.1:{p}/sitemap_index.xml\n".encode(), "text/plain")
    if path == "/sitemap_index.xml":
        return send(h, 200, f'<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>http://127.0.0.1:{p}/sm-pages.xml.gz</loc></sitemap></sitemapindex>'.encode(), "application/xml")
    if path == "/sm-pages.xml.gz":
        xml = ('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(
            f"<url><loc>http://127.0.0.1:{p}{u}</loc></url>" for u in ("/what-we-do", "/who-we-serve", "/blog", "/careers")) + "</urlset>").encode()
        return send(h, 200, gzip.compress(xml), "application/gzip")
    body = pages.get(path.rstrip("/") or "/")
    send(h, 200, body) if body else send(h, 404, page("Not found", "No such page here."))


def sitemap_huge(h, path, q):
    p = BASE + 17
    if path == "/robots.txt":
        return send(h, 200, f"User-agent: *\nSitemap: http://127.0.0.1:{p}/sitemap.xml\n".encode(), "text/plain")
    if path == "/sitemap.xml":
        body = ('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(
            f"<url><loc>http://127.0.0.1:{p}/item/{i}</loc></url>" for i in range(50_000)) + "</urlset>").encode()
        return send(h, 200, body, "application/xml")
    if path.startswith("/item/"):
        return send(h, 200, page("Item", "A catalogue item page. " + LOREM))
    pages = business_site()
    body = pages.get(path.rstrip("/") or "/")
    send(h, 200, body) if body else send(h, 404, page("Not found", "No such page here."))


def status_site(code: int, retry_after: str | None = None):
    def fn(h, path, q):
        if path == "/robots.txt":
            return send(h, 404, b"", "text/plain")
        send(h, code, page(f"HTTP {code}", "This response carries an error status."), headers={"Retry-After": retry_after} if retry_after else None)
    return fn


def fixed(body: bytes, ctype="text/html; charset=utf-8", status=200, headers=None):
    def fn(h, path, q):
        if path == "/robots.txt":
            return send(h, 404, b"", "text/plain")
        send(h, status, body, ctype, headers)
    return fn


NGINX = b"<!DOCTYPE html><html><head><title>Welcome to nginx!</title></head><body><h1>Welcome to nginx!</h1><p>If you see this page, the nginx web server is successfully installed and working. Further configuration is required.</p><p>For online documentation and support please refer to nginx.org.</p></body></html>"
COMING = page("Coming soon", "Our new website is coming soon. We are working hard to launch. Please check back later for updates from the team.")
PARKED = page("example-domain.test", "This domain is for sale. Buy this domain today. Make an offer on this premium domain name. Related searches: loans, insurance, hosting.")
SOFT404 = page("Page not found", "404. Sorry, the page you are looking for could not be found.")
LOGIN = b"<html><head><title>Member login</title></head><body><h1>Member login</h1><p>Please sign in to continue.</p><form><input name=email><input type=password name=pw><button>Sign in</button></form></body></html>"
BOTPAGE = b"<html><head><title>Just a moment...</title></head><body><h1>Checking your browser before accessing the site</h1><p>Enable JavaScript and cookies to continue. Ray ID: 0000000000</p></body></html>"
JSONBODY = b'{"company":"Acme","products":["pump","compressor"],"note":"this is an API response, not a web page"}'

# ---- more crawl traps (added after GATE 1): every site also has /about /services /products so a good crawler still has real pages ----
BIZ_LINKS = [("/about", "About us"), ("/services", "Services"), ("/products", "Products")]


def trap(gen):
    """gen(path, query) -> None (serve normal business page / 404) or (status, body, headers)."""
    pages = business_site()

    def fn(h, path, q):
        res = gen(path, q)
        if path == "/robots.txt":  # only a generator that explicitly serves robots rules may answer it
            if not (res and res[0] == 200 and b"User-agent" in res[1]):
                return send(h, 404, b"", "text/plain")
        if res is None:
            body = pages.get(path.rstrip("/") or "/")
            return send(h, 200, body) if body else send(h, 404, page("Not found", "No such page here."))
        status, body, hdr = res
        hdr = dict(hdr or {})
        ctype = hdr.pop("Content-Type", "text/html; charset=utf-8")
        send(h, status, body, ctype, hdr)
    return fn


def home(extra):
    return (200, page("Acme Pumps", LOREM * 2, BIZ_LINKS + extra), None)


def _rid():
    return random.randint(10**7, 10**8)


def g_pagination(path, q):
    if path == "/":
        return home([("/list?page=1", "All items")])
    if path == "/list":
        n = int(q.get("page", ["1"])[0])
        return 200, page(f"Items page {n}", " ".join(f"Item {n * 10 + i} is a catalogue entry." for i in range(10)), [(f"/list?page={n + 1}", "Next"), (f"/list?page={max(1, n - 1)}", "Previous")]), None


def g_day_calendar(path, q):
    import datetime as dt
    if path == "/":
        return home([("/day/2024/01/01", "Daily events")])
    parts = path.strip("/").split("/")
    if parts[0] == "day" and len(parts) == 4:
        d = dt.date(int(parts[1]), int(parts[2]), int(parts[3]))
        nx, pv = d + dt.timedelta(days=1), d - dt.timedelta(days=1)
        return 200, page(f"Events {d}", "Nothing scheduled. " + LOREM, [(f"/day/{nx.year}/{nx.month:02d}/{nx.day:02d}", "Next day"), (f"/day/{pv.year}/{pv.month:02d}/{pv.day:02d}", "Previous day"),
                                                                       (f"/day/{d.year + 1}/{d.month:02d}/{d.day:02d}", "Next year")]), None


def g_sid_path(path, q):
    if path == "/":
        return 200, page("Acme Pumps", LOREM * 2, [(f"/s/{_rid()}{p}", t) for p, t in BIZ_LINKS]), None
    if path.startswith("/s/"):
        rest = "/" + "/".join(path.strip("/").split("/")[2:])
        return 200, page(f"Acme {rest}", LOREM * 2, [(f"/s/{_rid()}{p}", t) for p, t in BIZ_LINKS]), None


def g_sid_redirect(path, q):
    if "PHPSESSID" not in q:
        return 302, b"", {"Location": f"{path}?PHPSESSID={_rid()}", "Content-Type": "text/html"}
    base = business_site().get(path.rstrip("/") or "/")
    return (200, base, None) if base else (404, page("Not found", "No such page."), None)


def g_facets(path, q):
    if path == "/":
        links = [(f"/products?sort={s}&dir={d}&per_page={n}&view={v}", f"{s} {d} {n} {v}") for s in ("name", "price", "date", "rating") for d in ("asc", "desc")
                 for n in (10, 20, 50) for v in ("grid", "list")]
        return 200, page("Shop", LOREM * 2, [("/about", "About us"), ("/services", "Services")] + links), None


def g_growing_redirect(path, q):
    if path in ("/", "/r"):
        n = int(q.get("n", ["0"])[0])
        return 302, b"", {"Location": f"/r?n={n + 1}", "Content-Type": "text/html"}


def g_path_growth(path, q):
    if path == "/":
        return home([("/a", "Archive")])
    if path.startswith("/a"):
        return 200, page(f"Archive {path}", LOREM * 2, [(path.rstrip("/") + "/a", "Older"), ("/about", "About us")]), None


def g_breadth(path, q):
    if path == "/":
        return 200, page("Acme Pumps", LOREM * 2, BIZ_LINKS + [(f"/products/p{i}", f"Pump model {i}") for i in range(1, 31)]), None
    if path.startswith("/products/p"):
        k = int(path.rsplit("p", 1)[-1])
        return 200, page(f"Pump model {k}", LOREM * 2, [(f"/products/p{k * 30 + i}", f"Pump model {k * 30 + i}") for i in range(1, 31)]), None


def g_relative(path, q):
    if path == "/":
        return 200, b"<html><head><title>Acme</title></head><body><nav><a href='/about'>About us</a><a href='docs/'>Docs</a></nav><p>" + (LOREM * 2).encode() + b"</p></body></html>", None
    if "docs" in path:
        return 200, b"<html><head><title>Docs</title></head><body><a href='docs/'>More docs</a><p>" + (LOREM * 2).encode() + b"</p></body></html>", None


def g_soft404(path, q):
    if path == "/":
        return home([("/x-1", "Resources")])
    if path not in business_site() and path.rstrip("/") not in business_site():
        return 200, page("Resources", LOREM * 2, [(f"/x-{_rid()}", "More resources"), ("/about", "About us")]), None


def g_case_dupes(path, q):
    if path == "/":
        return home([("/About", "About"), ("/about/", "About us"), ("/ABOUT/", "ABOUT"), ("/about/index.html", "About index"), ("/about?utm_source=a", "About a"),
                     ("/about?utm_source=b", "About b"), ("/Services", "Services (caps)"), ("/services/", "Services slash")])
    norm = path.lower().rstrip("/")
    if norm.endswith("/index.html"):
        norm = norm[: -len("/index.html")]
    body = business_site().get(norm or "/")
    return (200, body, None) if body else None


def g_mirrors(path, q):
    if path == "/":
        return 200, page("Acme Pumps", LOREM * 2, BIZ_LINKS + [(f"/mirror/{i}", f"Mirror {i}") for i in range(1, 51)]), None
    if path.startswith("/mirror/"):
        return 200, page("Acme pumps overview", "Identical mirrored content. " + LOREM * 3), None


def g_sitemap_chain(path, q):
    if path == "/robots.txt":
        return 200, f"User-agent: *\nSitemap: http://127.0.0.1:{BASE + 58}/sm0.xml\n".encode(), {"Content-Type": "text/plain"}
    if path.startswith("/sm") and path.endswith(".xml"):
        k = int(path[3:-4])
        return 200, (f'<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>http://127.0.0.1:{BASE + 58}/sm{k + 1}.xml</loc></sitemap></sitemapindex>').encode(), {"Content-Type": "application/xml"}


def g_infinite_scroll(path, q):
    if path == "/":
        return home([("/feed?offset=0", "News feed")])
    if path == "/feed":
        n = int(q.get("offset", ["0"])[0])
        return 200, page(f"Feed {n}", " ".join(f"Post {n + i} about our pumps." for i in range(20)), [(f"/feed?offset={n + 20}", "Load more")]), None


def g_tags(path, q):
    if path == "/":
        return home([(f"/t/tag-{_rid()}", "Topics")])
    if path.startswith("/t/"):
        return 200, page("Topic", LOREM * 2, [(f"/t/tag-{_rid()}", "Related topic") for _ in range(20)] + [("/about", "About us")]), None


def cross_loop(partner_port):
    def fn(h, path, q):
        if path == "/robots.txt":
            return send(h, 404, b"", "text/plain")
        send(h, 302, b"", headers={"Location": f"http://127.0.0.1:{partner_port}/"})
    return fn


SCENARIOS: dict[int, tuple[str, object]] = {
    0: ("control: normal 4-page business site, no robots.txt", serve_pages(business_site())),
    1: ("slow-drip body (1 byte / 0.5 s for 2 min)", slow_drip),
    2: ("hang: accepts request, never answers (60 s)", hang),
    3: ("slow headers: 20 s before answering", slow_headers),
    4: ("huge body: ~60 MB streamed, no Content-Length", huge_body),
    5: ("gzip bomb page: 150 MB when expanded", gzip_bomb_page),
    6: ("PDF served as the homepage", fixed(b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF", "application/pdf")),
    7: ("sitemap.xml.gz bomb (1M URLs expanded) named in robots.txt", sitemap_bomb),
    8: ("sitemap with entity expansion (billion-laughs style)", entity_sitemap),
    9: ("redirect loop /a <-> /b", redirect_loop),
    10: ("redirect to a 'secret' page on 127.0.0.2 (own machine)", redirect_to_loopback),
    11: ("infinite calendar trap", calendar_trap),
    12: ("session-id URL trap", session_trap),
    13: ("faceted-navigation trap", faceted_trap),
    14: ("long redirect chain (9 hops) then a good page", redirect_chain),
    15: ("malformed sitemap.xml named in robots.txt", sitemap_malformed),
    16: ("sitemap index + .gz child; business pages on non-standard paths", sitemap_index_nonstandard),
    17: ("huge sitemap: 50,000 URLs", sitemap_huge),
    18: ("robots.txt disallow all", robots_site("User-agent: *\nDisallow: /\n")),
    19: ("robots.txt disallows /about only", robots_site("User-agent: *\nDisallow: /about\n")),
    20: ("robots.txt crawl-delay 10", robots_site("User-agent: *\nCrawl-delay: 10\nAllow: /\n")),
    21: ("robots.txt malformed garbage", robots_site("<<<garbage>>> ;;; not robots\nfoo bar\n%%%\nDisallow /nothing\n???\nxyz\n")),
    22: ("robots.txt returns HTTP 503", robots_site(503)),
    23: ("robots.txt is an HTML page (200)", robots_site("<html><body>Welcome to our site</body></html>")),
    24: ("429 Too Many Requests with Retry-After: 5", status_site(429, "5")),
    25: ("503 Service Unavailable with Retry-After: 5", status_site(503, "5")),
    26: ("HTTP 200 soft-404 page ('Page not found')", fixed(SOFT404)),
    27: ("HTTP 200 empty body", fixed(b"")),
    28: ("default nginx welcome page", fixed(NGINX)),
    29: ("'Coming soon' page", fixed(COMING)),
    30: ("parked / for-sale domain page", fixed(PARKED)),
    31: ("login-walled landing page", fixed(LOGIN)),
    32: ("bot challenge page ('Just a moment...') with 403", fixed(BOTPAGE, status=403, headers={"cf-mitigated": "challenge", "Server": "cloudflare"})),
    33: ("latin-1 bytes with no charset declared", charset_latin1),
    34: ("Shift_JIS body but header says utf-8", charset_sjis_wrong_header),
    35: ("UTF-8 with BOM", charset_bom),
    36: ("UTF-16 with BOM", charset_utf16),
    37: ("meta-refresh redirect", meta_refresh),
    38: ("JavaScript redirect", js_redirect),
    39: ("redirect to login page", redirect_to_login),
    40: ("JSON served as homepage", fixed(JSONBODY, "application/json")),
    41: ("deep link chain /depth/N", deep_chain),
    42: ("403 Forbidden", status_site(403)),
    43: ("500 Internal Server Error", status_site(500)),
    44: ("trap: infinite pagination ?page=N", trap(g_pagination)),
    45: ("trap: day-level calendar with next/previous day and next year", trap(g_day_calendar)),
    46: ("trap: session ID in the URL path, new on every response", trap(g_sid_path)),
    47: ("trap: every first request redirected to ?PHPSESSID=<random>", trap(g_sid_redirect)),
    48: ("trap: faceted navigation with sort/dir/per_page/view (96 combinations)", trap(g_facets)),
    49: ("redirect trap: homepage redirects to an endless series of new URLs (?n=1,2,3...)", trap(g_growing_redirect)),
    50: ("redirect loop across two origins (8850 <-> 8851)", cross_loop(BASE + 51)),
    51: ("partner:redirect loop partner (not a dataset row)", cross_loop(BASE + 50)),
    52: ("trap: path keeps growing /a/a/a/...", trap(g_path_growth)),
    53: ("trap: link explosion, each page links to 30 new product pages", trap(g_breadth)),
    54: ("trap: relative link without slash grows /docs/docs/docs/...", trap(g_relative)),
    55: ("trap: every unknown URL answers 200 (random soft-404s)", trap(g_soft404)),
    56: ("trap: case/slash/index/utm duplicates of /about and /services", trap(g_case_dupes)),
    57: ("trap: 50 mirrored pages with identical content", trap(g_mirrors)),
    58: ("trap: endless sitemap index chain sm0.xml -> sm1.xml -> ...", trap(g_sitemap_chain)),
    59: ("trap: infinite scroll ?offset=N", trap(g_infinite_scroll)),
    60: ("trap: endless tag graph, 20 new tag pages per page", trap(g_tags)),
    62: ("TEST ONLY (not a dataset row): gzip bomb, 600 MB when expanded", gzip_bomb_big),
    61: ("TEST ONLY (not a dataset row): JavaScript shell that redirects the browser to http://127.0.0.2:8810/secret (L-04)", fixed(b"<html><head><title>Loading</title><script>window.location.href='http://127.0.0.2:8810/secret';</script></head><body></body></html>")),
}


def make_handler(handler_fn):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _dispatch(self):
            u = urlparse(self.path)
            try:
                handler_fn(self, u.path or "/", parse_qs(u.query))
            except (BrokenPipeError, ConnectionResetError):
                pass

        do_GET = do_HEAD = _dispatch

        def log_message(self, *a):  # quiet
            pass

    return H


def serve_all() -> list[ThreadingHTTPServer]:
    servers = []
    for n, (_desc, fn) in SCENARIOS.items():
        srv = ThreadingHTTPServer(("127.0.0.1", BASE + n), make_handler(fn))
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
    # second loopback address for the redirect-to-private scenario's target
    extra = ThreadingHTTPServer(("127.0.0.2", BASE + 10), make_handler(redirect_to_loopback))
    extra.daemon_threads = True
    threading.Thread(target=extra.serve_forever, daemon=True).start()
    servers.append(extra)
    return servers


if __name__ == "__main__":
    if "--list" in sys.argv:
        for n, (desc, _fn) in SCENARIOS.items():
            print(f"{BASE + n}  {desc}")
        sys.exit(0)
    serve_all()
    print(f"Scenario server running on 127.0.0.1:{BASE}-{BASE + max(SCENARIOS)} (Ctrl-C to stop)", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
