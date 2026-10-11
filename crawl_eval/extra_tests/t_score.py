"""L-01 / L-02: run the crawler's real page-ranking function (discover._score) on business paths. Offline, no network."""
from common import save, setup  # noqa: F401

from app.crawler.discover import _score

CASES = [
    # (path, anchor text, what a person would say)
    ("/services", "Services", "good"), ("/about", "About us", "good"), ("/products", "Products", "good"),
    ("/services/accounting", "Accounting services", "good"), ("/services/legal-advice", "Legal advice", "good"),
    ("/research", "Research", "good"), ("/products/compressors", "Compressors", "good"), ("/express-delivery", "Express delivery", "good"),
    ("/products/cartridges", "Cartridges", "good"), ("/services/administration", "Administration services", "good"),
    ("/about/our-advantage", "Our advantage", "good"), ("/about/heritage", "Our heritage", "good"), ("/company/mortgage-services", "Mortgage services", "good"),
    ("/solutions/stage-lighting", "Stage lighting", "good"), ("/industries/newsprint", "Newsprint", "good"), ("/products/guides-and-rails", "Guide rails", "good"),
    ("/what-we-do", "What we do", "good"), ("/en/solutions", "Solutions", "good"),
    # non-English and non-standard paths (L-02)
    ("/ueber-uns", "Über uns", "good"), ("/leistungen", "Leistungen", "good"), ("/produkte", "Produkte", "good"), ("/unternehmen", "Unternehmen", "good"),
    ("/nosotros", "Nosotros", "good"), ("/quienes-somos", "Quiénes somos", "good"), ("/servicios", "Servicios", "good"), ("/productos", "Productos", "good"),
    ("/a-propos", "À propos", "good"), ("/nos-services", "Nos services", "good"), ("/produits", "Produits", "good"),
    ("/chi-siamo", "Chi siamo", "good"), ("/servizi", "Servizi", "good"), ("/会社概要", "会社概要", "good"), ("/company/", "会社案内", "good"),
    ("/o-nas", "O nas", "good"), ("/hakkimizda", "Hakkımızda", "good"), ("/hizmetlerimiz", "Hizmetlerimiz", "good"),
    # things that should be skipped
    ("/blog", "Blog", "skip"), ("/careers", "Careers", "skip"), ("/privacy-policy", "Privacy", "skip"), ("/login", "Login", "skip"), ("/cart", "Cart", "skip"),
]
rows = []
for path, text, expect in CASES:
    s = _score(path, text)
    rows.append({"path": path, "anchor": text, "person_says": expect, "crawler_score": s, "wrongly_skipped": expect == "good" and s == 0, "wrongly_kept": expect == "skip" and s > 0})
bad_good = [r for r in rows if r["wrongly_skipped"]]
save("t_score", {"what": "discover._score on business and non-business paths (the real function, no network)", "rows": rows,
                 "good_paths_scored_0": len(bad_good), "good_paths_total": sum(1 for r in rows if r["person_says"] == "good"),
                 "english_good_scored_0": [r["path"] for r in bad_good if r["path"].isascii() and r["path"] in
                                           ("/services/accounting", "/services/legal-advice", "/research", "/products/compressors", "/express-delivery", "/products/cartridges",
                                            "/services/administration", "/about/our-advantage", "/about/heritage", "/company/mortgage-services", "/solutions/stage-lighting",
                                            "/industries/newsprint", "/products/guides-and-rails")],
                 "non_english_good_scored_0": [r["path"] for r in bad_good if r["path"] in ("/ueber-uns", "/leistungen", "/produkte", "/unternehmen", "/nosotros", "/quienes-somos",
                                                                                          "/servicios", "/productos", "/a-propos", "/nos-services", "/produits", "/chi-siamo", "/servizi",
                                                                                          "/会社概要", "/o-nas", "/hakkimizda", "/hizmetlerimiz")]})
