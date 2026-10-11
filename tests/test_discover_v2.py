"""Page discovery, ranking and sitemaps (CR-C03-C10, issues ISS-07, ISS-28)."""

import asyncio
import gzip

import httpx
import pytest

from app.crawler import config
from app.crawler.discover import PageLink, canonical_key, classify, discover_pages, is_trap, merge_candidates, rank, tokens
from app.crawler.fetcher import RobotsRules, load_robots
from app.crawler.sitemap import parse_sitemap, sitemap_urls
from tests.helpers import make_client

BASE = "https://example.com"


def links(html: str, base: str = BASE) -> list[PageLink]:
    return discover_pages(html.encode(), base)


# Phase 1 measured these: 28 of 36 genuine business paths scored 0 (ISS-07). All of them must now be recognised.
GOOD = [
    ("/services", "Services", "services"), ("/about", "About us", "about"), ("/products", "Products", "products"),
    ("/services/accounting", "Accounting services", "services"), ("/services/legal-advice", "Legal advice", "services"),
    ("/products/compressors", "Compressors", "products"), ("/products/cartridges", "Cartridges", "products"),
    ("/services/administration", "Administration services", "services"), ("/about/our-advantage", "Our advantage", "about"),
    ("/about/heritage", "Our heritage", "about"), ("/company/mortgage-services", "Mortgage services", "services"),
    ("/solutions/stage-lighting", "Stage lighting", "services"), ("/industries/newsprint", "Newsprint", "industries"),
    ("/products/guides-and-rails", "Guide rails", "products"), ("/what-we-do", "What we do", "services"), ("/en/solutions", "Solutions", "services"),
    ("/who-we-serve", "Who we serve", "industries"), ("/who-we-are", "Who we are", "about"), ("/our-story", "Our story", "about"),
    ("/practice-areas", "Practice areas", "services"), ("/case-studies", "Case studies", "customers"), ("/contact-us", "Contact us", "contact"),
    # other languages (ISS-07 / L-02)
    ("/ueber-uns", "Über uns", "about"), ("/leistungen", "Leistungen", "services"), ("/produkte", "Produkte", "products"), ("/unternehmen", "Unternehmen", "about"),
    ("/branchen", "Branchen", "industries"), ("/kontakt", "Kontakt", "contact"),
    ("/nosotros", "Nosotros", "about"), ("/quienes-somos", "Quiénes somos", "about"), ("/servicios", "Servicios", "services"), ("/productos", "Productos", "products"),
    ("/a-propos", "À propos", "about"), ("/nos-services", "Nos services", "services"), ("/produits", "Produits", "products"), ("/secteurs", "Secteurs", "industries"),
    ("/chi-siamo", "Chi siamo", "about"), ("/servizi", "Servizi", "services"), ("/prodotti", "Prodotti", "products"),
    ("/sobre-nos", "Sobre nós", "about"), ("/servicos", "Serviços", "services"), ("/produtos", "Produtos", "products"),
    ("/over-ons", "Over ons", "about"), ("/diensten", "Diensten", "services"), ("/producten", "Producten", "products"),
    ("/o-nas", "O nas", "about"), ("/uslugi", "Usługi", "services"), ("/produkty", "Produkty", "products"),
    ("/hakkimizda", "Hakkımızda", "about"), ("/hizmetlerimiz", "Hizmetlerimiz", "services"), ("/urunlerimiz", "Ürünlerimiz", "products"),
    ("/tentang-kami", "Tentang kami", "about"), ("/layanan", "Layanan", "services"), ("/produk", "Produk", "products"),
    ("/会社概要", "会社概要", "about"), ("/company/", "会社案内", "about"), ("/サービス", "サービス", "services"), ("/製品情報", "製品情報", "products"),
    ("/关于我们", "关于我们", "about"), ("/产品与服务", "产品与服务", "products"), ("/解决方案", "解决方案", "services"),
    ("/회사소개", "회사소개", "about"), ("/من-نحن", "من نحن", "about"), ("/خدماتنا", "خدماتنا", "services"), ("/ہمارے-بارے-میں", "ہمارے بارے میں", "about"),
]


@pytest.mark.parametrize("path, anchor, kind", GOOD)
def test_genuine_business_pages_are_recognised(path, anchor, kind):
    page_type, score = classify(path, anchor)
    assert page_type == kind and score > 0


@pytest.mark.parametrize("path", ["/", ""])
def test_the_homepage_path_is_not_a_candidate(path):
    assert classify(path, "Home")[0] in ("other", "skip")


@pytest.mark.parametrize(
    "path, anchor",
    [
        ("/blog", "Blog"), ("/blog/our-services-explained", "Our services explained"), ("/careers", "Careers"), ("/news/2024/launch", "News"),
        ("/privacy-policy", "Privacy"), ("/terms-and-conditions", "Terms"), ("/login", "Login"), ("/cart", "Cart"), ("/checkout", "Checkout"),
        ("/wp-admin/", "Admin"), ("/tag/startup", "Tag"), ("/author/jane", "Jane"), ("/search", "Search"), ("/my-account", "Account"), ("/feed", "RSS"),
        ("/brochure.pdf", "Brochure"), ("/logo.png", "Logo"), ("/press", "Press"), ("/events", "Events"), ("/webinars", "Webinars"),
        ("/karriere", "Karriere"), ("/datenschutz", "Datenschutz"), ("/mentions-legales", "Mentions légales"), ("/news-and-events", "News"),
        ("/faq", "FAQ"), ("/cookie-policy", "Cookies"), ("/disclaimer", "Disclaimer"), ("/downloads", "Downloads"), ("/wp-json/x", "x"),
    ],
)
def test_junk_pages_never_get_a_slot(path, anchor):
    assert classify(path, anchor)[0] == "skip"


def test_skip_words_match_whole_words_only():
    """'press' is not 'compressors', 'account' is not 'accounting', 'tag' is not 'stage', 'legal' next to 'services' is a service."""
    assert tokens("/products/compressors") == ["products", "compressors"]
    assert classify("/products/compressors", "Compressors")[0] == "products"
    assert classify("/services/accounting", "")[0] == "services"
    assert classify("/solutions/stage-lighting", "")[0] == "services"
    assert classify("/legal-services", "Legal services")[0] == "services"
    assert classify("/legal", "Legal")[0] == "skip"


def test_weak_menu_links_are_kept_only_as_last_resort_candidates():
    assert classify("/express-delivery", "Express delivery", nav=True) == ("other", 1)       # no business word, but a short menu link
    assert classify("/express-delivery", "Express delivery", nav=False) == ("other", 0)      # same link in the page body: no slot


def test_preference_order_is_about_products_services_industries_customers_contact():
    html = """<nav>
      <a href="/contact">Contact</a><a href="/case-studies">Case studies</a><a href="/industries">Industries</a>
      <a href="/services">Services</a><a href="/products">Products</a><a href="/about">About us</a></nav>"""
    assert [link.page_type for link in links(html)] == ["about", "products", "services", "industries", "customers", "contact"]


def test_navigation_links_rank_above_footer_links_of_the_same_kind():
    html = '<nav><a href="/services/web">Web services</a></nav><footer><a href="/services/seo">SEO services</a></footer>'
    found = links(html)
    assert found[0].url.endswith("/services/web") and found[0].nav is True and found[1].nav is False


def test_link_text_finds_a_page_whose_path_says_nothing():
    html = '<a href="/p/12345">Our Services</a><a href="/page?id=9">About Us</a>'
    kinds = {link.url: link.page_type for link in links(html)}
    assert kinds["https://example.com/p/12345"] == "services" and "about" in kinds.values()


def test_non_standard_paths_found_through_nav_text_and_title_attribute():
    html = '<a href="/x/1" title="Who we serve">&nbsp;</a><a href="/x/2" aria-label="What we do"></a>'
    assert {link.page_type for link in links(html)} == {"industries", "services"}


def test_urls_that_differ_only_by_case_slash_index_or_tracking_are_one_page():  # ISS-28
    html = "".join(f'<a href="{h}">About</a>' for h in ("/About", "/about/", "/ABOUT/", "/about/index.html", "/about?utm_source=x", "/about#team", "/about/index.php"))
    found = links(html)
    assert len(found) == 1
    keys = {canonical_key(h) for h in ("https://x.com/About", "https://www.x.com/about/", "https://x.com/ABOUT/index.html", "https://x.com/about?ref=1")}
    assert keys == {"x.com/about"}


def test_session_ids_and_pagination_and_calendars_are_traps():
    for path in ("/products/page/2", "/events/2024/05/", "/a/a/a/a", "/x/y/x/y/x/y", "/1/2/3/4/5/6/7", "/" + "long" * 80):
        assert is_trap(path), path
    assert not is_trap("/products/robots") and not is_trap("/en/about-us")
    html = '<a href="/products;jsessionid=ABC123">Products</a><a href="/products?sessionid=9">Products</a><a href="/products/page/3">Products</a>'
    assert [link.url for link in links(html)] == ["https://example.com/products"]


def test_language_prefix_does_not_count_as_depth_or_hide_a_skip_section():
    assert classify("/en/about-us", "")[0] == "about"
    assert classify("/de/blog/post", "")[0] == "skip"


def test_subdomains_of_the_same_company_count_but_not_blog_or_careers_hosts():
    html = '<a href="https://shop.example.com/products">Shop</a><a href="https://blog.example.com/products">Blog</a><a href="https://other.com/about">x</a>'
    assert [link.url for link in links(html)] == ["https://shop.example.com/products"]


def test_candidates_per_site_are_bounded(monkeypatch):
    monkeypatch.setattr(config, "MAX_DISCOVERED_PER_SITE", 5)
    html = "".join(f'<a href="/services/s{i}">Service {i}</a>' for i in range(100))
    assert len(links(html)) == 5


def test_sitemap_candidates_are_ranked_with_the_same_rules():
    pages = [PageLink("https://example.com/about", "About", 30, "about")]
    merged = merge_candidates(pages, ["https://example.com/blog/2024/x", "https://example.com/produkte", "https://example.com/leistungen/beratung",
                                      "https://example.com/about/", "https://example.com/products/page/9", "https://example.com/impressum"])
    kinds = {canonical_key(m.url): m.page_type for m in merged}
    assert kinds == {"example.com/about": "about", "example.com/produkte": "products", "example.com/leistungen/beratung": "services", "example.com/impressum": "contact"}
    assert [m.page_type for m in rank(merged)][0] == "about"


# --- sitemaps ----------------------------------------------------------------------------------------------------

URLSET = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{}</urlset>"""


def urlset(*locs):
    return URLSET.format("".join(f"<url><loc>{loc}</loc></url>" for loc in locs)).encode()


def test_sitemap_index_urlset_and_invalid():
    assert parse_sitemap(b"<sitemapindex><sitemap><loc>https://e.com/a.xml</loc></sitemap></sitemapindex>") == ("index", ["https://e.com/a.xml"])
    assert parse_sitemap(urlset("https://e.com/a", "https://e.com/b")) == ("urlset", ["https://e.com/a", "https://e.com/b"])
    assert parse_sitemap(b"not xml")[0] == "invalid" and parse_sitemap(b"<html/>")[0] == "invalid" and parse_sitemap(b"")[0] == "invalid"
    assert parse_sitemap(urlset("https://e.com/a")[:-10])[0] == "invalid"       # truncated / malformed


def test_gzipped_sitemap_is_read():
    assert parse_sitemap(gzip.compress(urlset("https://e.com/a")))[1] == ["https://e.com/a"]


def test_gzip_bomb_sitemap_is_refused_not_expanded(monkeypatch):
    monkeypatch.setattr(config, "SITEMAP_MAX_BYTES", 1_000_000)
    bomb = gzip.compress(b"<urlset>" + b"<url><loc>https://e.com/x</loc></url>" * 5_000_000 + b"</urlset>", 9)
    assert len(bomb) < 3_000_000
    assert parse_sitemap(bomb) == ("invalid", [])


def test_entity_expansion_sitemap_is_refused():
    laughs = b"""<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>
    <urlset><url><loc>&lol2;</loc></url></urlset>"""
    assert parse_sitemap(laughs) == ("invalid", [])
    assert parse_sitemap(b'<?xml version="1.0"?><!DOCTYPE x SYSTEM "http://evil.example/x.dtd"><urlset/>') == ("invalid", [])


def make_sitemap_client(files: dict[str, bytes], robots: str = "", calls: list | None = None):
    def handler(request):
        if calls is not None:
            calls.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots, request=request) if robots else httpx.Response(404, request=request)
        if request.url.path in files:
            return httpx.Response(200, content=files[request.url.path], headers={"content-type": "application/xml"}, request=request)
        return httpx.Response(404, request=request)

    return make_client(handler)


def collect(client, robots_text: str = "") -> list[str]:
    async def go():
        rules = await load_robots(client, BASE, {})
        return await sitemap_urls(client, rules, BASE, "example.com")

    return asyncio.run(go())


def test_sitemap_listed_in_robots_is_used_with_index_and_other_hosts_ignored():
    files = {
        "/maps/index.xml": b"<sitemapindex><sitemap><loc>https://example.com/maps/a.xml</loc></sitemap><sitemap><loc>https://evil.com/b.xml</loc></sitemap></sitemapindex>",
        "/maps/a.xml": urlset("https://example.com/services", "https://other.com/about", "https://example.com/products"),
    }
    found = collect(make_sitemap_client(files, robots="User-agent: *\nSitemap: https://example.com/maps/index.xml\n"))
    assert found == ["https://example.com/services", "https://example.com/products"]


def test_common_locations_are_tried_when_robots_lists_none():
    calls: list[str] = []
    found = collect(make_sitemap_client({"/sitemap_index.xml": urlset("https://example.com/about")}, calls=calls))
    assert found == ["https://example.com/about"]
    assert "/sitemap.xml" in calls and "/sitemap_index.xml" in calls and calls.index("/sitemap.xml") < calls.index("/sitemap_index.xml")


def test_number_of_sitemap_files_is_bounded(monkeypatch):
    monkeypatch.setattr(config, "MAX_SITEMAPS", 3)
    calls: list[str] = []
    index = "<sitemapindex>" + "".join(f"<sitemap><loc>https://example.com/s{i}.xml</loc></sitemap>" for i in range(50)) + "</sitemapindex>"
    files = {"/sitemap.xml": index.encode()} | {f"/s{i}.xml": urlset(f"https://example.com/p{i}") for i in range(50)}
    collect(make_sitemap_client(files, calls=calls))
    assert len([c for c in calls if c != "/robots.txt"]) <= 3


def test_a_huge_sitemap_is_read_but_only_business_pages_become_candidates():
    locs = [f"https://example.com/news/article-{i}" for i in range(20_000)] + ["https://example.com/leistungen", "https://example.com/ueber-uns"]
    found = collect(make_sitemap_client({"/sitemap.xml": urlset(*locs)}))
    assert len(found) == 20_002
    merged = merge_candidates([], found)
    assert [m.page_type for m in merged] == ["about", "services"]            # 20,000 blog URLs rejected, never fetched


def test_robots_disallowed_sitemap_is_not_fetched():
    calls: list[str] = []
    collect(make_sitemap_client({"/sitemap.xml": urlset("https://example.com/about")}, robots="User-agent: *\nDisallow: /sitemap.xml\n", calls=calls))
    assert "/sitemap.xml" not in calls
