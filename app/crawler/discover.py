"""Find the business pages worth reading (About, Products, Services, Industries ...), CR-C01-C10.

Fixes against Phase 1 (ISS-07, ISS-28):
- words are matched as WHOLE words (so 'compressors' is not 'press', 'accounting' is not 'account', 'stage' is not 'tag')
- a skip word only wins when nothing in the same path or link text says the page is valuable ('legal-services' is kept, 'privacy-policy' is not);
  section words such as /blog/ or /careers/ always win
- word lists exist in many languages (EN, DE, FR, ES, IT, PT, NL, TR, ID, RU, PL, SV, AR, UR, HI, ZH, JA, KO)
- link text, link position (menu/header), URL path and sitemap entries are all used; the page title confirms the type after the fetch
- the order of fetching follows the preference in the requirements: About, Products, Services, Industries, Customers, Contact
- duplicates (case, trailing slash, index.html, tracking parameters) share one canonical key and are fetched once
- trap guards: depth, repeated segments, date archives, pagination, query strings, number of candidates
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from app.crawler import config
from app.domains import registrable_domain

# ---------------------------------------------------------------------------------------------- word lists
# Each entry is a word or a phrase (words separated by spaces). Latin script: whole-word match, accents ignored.
# Other scripts (CJK, Arabic, Devanagari ...): substring match, because those languages do not put spaces between words.
TERMS: dict[str, tuple[str, ...]] = {
    "about": (
        "about", "about us", "aboutus", "company", "who we are", "whoweare", "our story", "ourstory", "story", "profile", "history",
        "mission", "vision", "values", "corporate", "overview", "company profile", "get to know us", "meet us", "our company",
        "ueber uns", "uber uns", "ueberuns", "unternehmen", "firma", "wir", "ueber", "wer wir sind", "philosophie",
        "a propos", "apropos", "qui sommes nous", "societe", "entreprise", "notre histoire", "presentation", "qui sommes-nous",
        "nosotros", "quienes somos", "quienes", "acerca", "acerca de", "empresa", "sobre nosotros", "historia", "quienes-somos",
        "chi siamo", "azienda", "societa", "storia", "profilo", "sobre", "quem somos", "sobre nos", "a empresa", "institucional",
        "over ons", "bedrijf", "wie zijn wij", "over", "hakkimizda", "kurumsal", "tentang", "tentang kami", "profil", "perusahaan",
        "o nas", "o firmie", "o kompanii", "kompaniya", "o kompaniya", "om oss", "foretag", "om foretaget",
        "من نحن", "عن الشركة", "عن شركتنا", "نبذة عنا", "نبذة", "من-نحن", "ہمارے بارے میں", "ہمارے بارے", "ہم کون ہیں", "हमारे बारे में", "हमारे बारे", "कंपनी",
        "关于我们", "关于", "公司简介", "公司介绍", "企业介绍", "会社概要", "企業情報", "私たちについて", "会社案内", "会社情報", "회사소개", "회사 소개", "기업소개", "소개",
    ),
    "services": (
        "services", "service", "solutions", "solution", "capabilities", "expertise", "what we do", "whatwedo", "offerings", "practice areas",
        "practices", "consulting", "research", "research and development", "r d", "innovation", "our services", "our solutions", "service offerings", "specialties", "specialisms", "competencies",
        "leistungen", "dienstleistungen", "loesungen", "losungen", "angebot", "kompetenzen", "was wir tun", "leistung", "dienste",
        "nos services", "prestations", "expertises", "offres", "activites", "metiers", "savoir faire", "ce que nous faisons",
        "servicios", "soluciones", "que hacemos", "nuestros servicios", "capacidades", "servicio",
        "servizi", "soluzioni", "cosa facciamo", "competenze", "servicos", "solucoes", "o que fazemos", "servico",
        "diensten", "oplossingen", "wat we doen", "dienst", "hizmetler", "hizmetlerimiz", "cozumler", "cozumlerimiz", "hizmet", "layanan", "jasa", "solusi",
        "uslugi", "usługi", "resheniya", "rozwiazania", "oferta", "tjanster", "losningar",
        "خدماتنا", "الخدمات", "خدمات", "حلول", "حلولنا", "ہماری خدمات", "سروسز", "सेवाएं", "सेवाएँ", "समाधान",
        "服务", "产品与服务", "解决方案", "业务", "业务范围", "サービス", "事業内容", "ソリューション", "業務内容", "서비스", "사업분야", "사업 분야", "솔루션",
    ),
    "products": (
        "products", "product", "platform", "software", "features", "catalog", "catalogue", "shop", "store", "categories", "collection",
        "collections", "our products", "product range", "range", "equipment", "machinery", "apps", "tools", "pricing plans",
        "produkte", "produkt", "sortiment", "produits", "gamme", "gammes", "productos", "catalogo", "prodotti", "produtos", "producten",
        "urunler", "urunlerimiz", "produk", "produkty", "produkciya", "katalog", "produktion",
        "منتجاتنا", "المنتجات", "منتجات", "مصنوعات", "پروڈکٹس", "उत्पाद", "产品", "商品", "产品中心", "製品", "製品情報", "商品情報", "제품", "상품", "제품소개",
    ),
    "industries": (
        "industries", "industry", "markets", "sectors", "who we serve", "whoweserve", "solutions by industry", "verticals", "industries served",
        "markets served", "sectors we serve", "clients by industry", "who we help", "industry solutions",
        "branchen", "branche", "industrien", "zielgruppen", "secteurs", "domaines d activite", "marches", "secteur",
        "sectores", "industrias", "mercados", "settori", "industrie", "mercati", "setores", "sectoren", "branches",
        "sektorler", "sektor", "industri", "otrasli", "branze", "branża", "القطاعات", "الصناعات", "قطاعات", "صنعتیں", "उद्योग", "行业", "行业解决方案", "業界", "業種", "산업", "업종",
    ),
    "customers": (
        "customers", "clients", "case studies", "casestudies", "case study", "portfolio", "references", "success stories", "testimonials",
        "partners", "partnerships", "projects", "our work", "work", "pricing", "prices", "plans", "reseller", "distributors",
        "kunden", "referenzen", "projekte", "preise", "partner", "clients", "realisations", "tarifs", "clientes", "casos", "proyectos",
        "precios", "clienti", "progetti", "prezzi", "projetos", "precos", "klanten", "prijzen", "musteriler", "referanslar",
        "عملاؤنا", "العملاء", "مشاريعنا", "客户", "案例", "合作伙伴", "お客様", "事例", "導入事例", "고객", "사례",
    ),
    "contact": (
        "contact", "contacts", "contact us", "contactus", "locations", "offices", "find us", "reach us", "get in touch", "imprint", "impressum",
        "kontakt", "kontaktieren", "contactez nous", "nous contacter", "contacto", "contactenos", "contatti", "contattaci", "contato", "fale conosco",
        "iletisim", "kontak", "kontakty", "kontaktai", "اتصل بنا", "تواصل معنا", "رابطہ", "संपर्क", "联系我们", "联系", "お問い合わせ", "お問合せ", "문의", "연락처",
    ),
}
# Order of fetching and base score (CR-C03, C04): About, Products, Services, Industries, Customers, Contact.
ORDER = ("about", "products", "services", "industries", "customers", "contact")
BASE_SCORE = {"about": 30, "products": 30, "services": 30, "industries": 20, "customers": 12, "contact": 8, "other": 1}

# Section words: a path starting with one of these is never worth a slot, whatever else the path says.
SECTION_SKIP = {
    "blog", "blogs", "news", "newsroom", "press", "articles", "posts", "careers", "career", "jobs", "job",
    "vacancies", "tag", "tags", "category", "categories-archive", "author", "authors", "feed", "rss", "events", "event", "webinar", "webinars",
    "podcast", "podcasts", "forum", "forums", "wp-admin", "wp-content", "wp-includes", "wp-json", "wp-login", "cart", "basket", "checkout",
    "account", "my-account", "myaccount", "login", "signin", "sign-in", "signup", "sign-up", "register", "wishlist", "search", "comments",
    "karriere", "stellenangebote", "nachrichten", "aktuelles", "presse", "carrieres", "emplois", "actualites", "actualite", "noticias",
    "prensa", "empleo", "trabajo", "carriere", "notizie", "stampa", "noticias", "imprensa", "vagas", "nieuws", "vacatures", "haber",
    "haberler", "kariyer", "berita", "karir", "новости", "карьера", "أخبار", "وظائف", "新闻", "新闻中心", "招聘", "ニュース", "採用", "뉴스", "채용",
    "download", "downloads", "unsubscribe", "print", "sitemap", "admin", "tel", "mailto", "javascript",
}
_SKIP_FILLER = {"and", "the", "of", "our", "latest", "und", "et", "y", "e", "en"}
# Policy words: skip the page unless the same path/link text also says it is valuable ('legal-services').
POLICY_SKIP = {
    "privacy", "terms", "tos", "cookie", "cookies", "legal", "policy", "policies", "disclaimer", "gdpr", "conditions", "faq", "faqs", "help",
    "support", "accessibility", "datenschutz", "agb", "mentions", "confidentialite", "privacidad", "terminos", "privacita", "termini",
    "gizlilik", "kebijakan", "политика", "الخصوصية", "الشروط", "隐私", "条款", "プライバシー", "利用規約", "개인정보", "이용약관",
}
SKIP_ANCHOR = (
    "blog", "careers", "jobs", "privacy", "terms", "cookie", "login", "log in", "sign in", "sign up", "subscribe", "newsletter", "cart",
    "checkout", "download", "facebook", "twitter", "linkedin", "instagram", "youtube", "tiktok", "pinterest", "whatsapp", "my account",
)
SKIP_HOST_LABELS = {"blog", "careers", "jobs", "status", "mail", "webmail", "mx", "forum", "community", "login", "account", "accounts",
                    "secure", "auth", "sso", "cdn", "static", "assets", "api", "docs", "developer", "developers", "help", "support"}
SKIP_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".zip", ".rar", ".mp4", ".mp3", ".css", ".js", ".xml", ".rss",
                   ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".ico", ".woff", ".woff2", ".exe", ".dmg", ".gz", ".txt", ".json")
INDEX_FILES = ("index.html", "index.htm", "index.php", "index.asp", "index.aspx", "default.aspx", "default.asp", "home.html", "home.php")
ALLOWED_QUERY_KEYS = {"page_id", "p_id", "id", "pageid", "pid", "cid", "sec", "section", "pagina"}
TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "msclkid", "mc_", "_ga", "ref", "source", "sessionid", "sid", "phpsessid", "jsessionid")
_LANG_SEGMENT = re.compile(r"^[a-z]{2}([-_][a-z]{2,4})?$")
_DATE_ARCHIVE = re.compile(r"/(19|20)\d{2}/(0?[1-9]|1[0-2])(/|$)")
_PAGINATION = re.compile(r"/(page|p|seite|pagina)/\d{1,3}(/|$)")
_JSESSION = re.compile(r";jsessionid=[^/?#]*", re.I)
_WORDS = re.compile(r"[^\W_]+", re.UNICODE)


_LETTER_MAP = str.maketrans({"ı": "i", "İ": "i", "ł": "l", "Ł": "l", "ø": "o", "Ø": "o", "đ": "d", "Đ": "d", "ß": "ss", "æ": "ae", "œ": "oe"})


def _strip_accents(text: str) -> str:
    """Remove accents from Latin letters only (münchen -> munchen). Kana, Hangul, Arabic ... are composed, never decomposed."""
    out = []
    for char in text.translate(_LETTER_MAP):
        if ord(char) < 0x250:
            out.append("".join(c for c in unicodedata.normalize("NFKD", char) if not unicodedata.combining(c)))
        else:
            out.append(unicodedata.normalize("NFKC", char))
    return "".join(out)


def _is_latin(text: str) -> bool:
    return all(ord(c) < 0x250 or not c.isalpha() for c in text)


def _prepare_terms():
    latin: dict[str, set[tuple[str, ...]]] = {}
    other: dict[str, list[str]] = {}
    for kind, words in TERMS.items():
        latin[kind], other[kind] = set(), []
        for word in words:
            norm = _strip_accents(word.lower())
            if _is_latin(norm):
                latin[kind].add(tuple(_WORDS.findall(norm.replace("-", " "))))
            else:
                other[kind].append(word.lower())
    return latin, other


_LATIN_TERMS, _OTHER_TERMS = _prepare_terms()


def tokens(text: str) -> list[str]:
    """Words of a path or link text, lower case, accents removed (münchen -> munchen). Non-Latin words stay whole."""
    return _WORDS.findall(_strip_accents(text.lower().replace("-", " ").replace("_", " ")))


def _contains_sequence(words: list[str], phrase: tuple[str, ...]) -> bool:
    n = len(phrase)
    if n == 0 or n > len(words):
        return False
    return any(tuple(words[i:i + n]) == phrase for i in range(len(words) - n + 1))


def matches_type(words: list[str], kind: str) -> bool:
    for phrase in _LATIN_TERMS[kind]:
        if _contains_sequence(words, phrase):
            return True
    joined = " ".join(words)
    return any(term in joined for term in _OTHER_TERMS[kind])


@dataclass
class PageLink:
    url: str
    label: str
    score: int
    page_type: str = "other"
    nav: bool = False
    source: str = "link"


# ---------------------------------------------------------------------------------------------- URL handling
def _normalize(url: str) -> str:
    """Stable form of an internal link: no fragment, no tracking parameters, no session id, no trailing slash, no www."""
    parsed = urlparse(_JSESSION.sub("", url))
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    host = (parsed.hostname or "").lower()
    try:
        port = f":{parsed.port}" if parsed.port and parsed.port not in (80, 443) else ""
    except ValueError:
        port = ""
    kept = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=False)
            if k.lower() in ALLOWED_QUERY_KEYS and not k.lower().startswith(TRACKING_PREFIXES)]
    query = urlencode(kept[:2])
    return urlunparse((parsed.scheme.lower(), f"{host}{port}", path, "", query, ""))


def canonical_key(url: str) -> str:
    """Key that is equal for /About, /about/, /ABOUT and /about/index.html (CR-C09, C10, ISS-28)."""
    norm = _normalize(url)
    parsed = urlparse(norm)
    path = parsed.path.lower()
    for index in INDEX_FILES:
        if path.endswith("/" + index):
            path = path[: -len(index) - 1] or "/"
    path = path.rstrip("/") or "/"
    host = (parsed.hostname or "").removeprefix("www.")
    return f"{host}{path}" + (f"?{parsed.query.lower()}" if parsed.query else "")


def _segments(path: str) -> list[str]:
    segments = [s for s in path.split("/") if s]
    if segments and _LANG_SEGMENT.match(segments[0].lower()):
        segments = segments[1:]
    return segments


def is_trap(path: str, query: str = "") -> bool:
    """Calendars, pagination, deep or self-repeating paths: never worth a request (CR-C09)."""
    segs = _segments(path)
    if len(segs) > config.MAX_PATH_DEPTH or len(path) > 200:
        return True
    lowered = [s.lower() for s in segs]
    if any(lowered.count(s) >= 3 for s in set(lowered)):
        return True
    if any(lowered[i] == lowered[i + 1] for i in range(len(lowered) - 1)) and len(lowered) > 3:
        return True
    return bool(_DATE_ARCHIVE.search(path.lower()) or _PAGINATION.search(path.lower()))


# ---------------------------------------------------------------------------------------------- scoring
def classify(path: str, anchor_text: str = "", nav: bool = False) -> tuple[str, int]:
    """(page_type, score). page_type 'skip' means: do not spend a request on it. Score 0 / 'other' means no business signal."""
    lowered_path = path.lower()
    if lowered_path.endswith(SKIP_EXTENSIONS):
        return "skip", 0
    segs = _segments(path)
    first_words = tokens(segs[0]) if segs else []
    top = [s for s in path.lower().split("/") if s][:2]   # before the language prefix is removed: "wp-json" looks like a language code
    if any(s in SECTION_SKIP or s.startswith("wp-") for s in top[:1] + (top[1:2] if top and _LANG_SEGMENT.match(top[0]) else [])):
        return "skip", 0
    if first_words and all(w in SECTION_SKIP or w in _SKIP_FILLER for w in first_words) and any(w in SECTION_SKIP for w in first_words):
        return "skip", 0
    path_words = tokens(" ".join(segs))
    anchor_words = tokens(anchor_text)
    last_words = tokens(segs[-1]) if segs else []

    best_type, best_score = "other", 0
    for kind in ORDER:
        in_path = matches_type(path_words, kind)
        in_anchor = matches_type(anchor_words, kind)
        if not (in_path or in_anchor):
            continue
        score = BASE_SCORE[kind] + (5 if in_path and in_anchor else 0) + (3 if nav else 0)
        score -= max(0, len(segs) - 2) * 2
        if kind == "products" and segs and not in_path and in_anchor:
            score -= 2
        if score > best_score:
            best_type, best_score = kind, score

    if best_type != "other":
        return best_type, max(1, best_score)

    # No business signal. Policy words and skip anchors say 'skip'; otherwise a short menu link is a weak 'other' candidate.
    if any(w in POLICY_SKIP for w in last_words) or any(w in POLICY_SKIP for w in anchor_words):
        return "skip", 0
    joined_anchor = " ".join(anchor_words)
    if any(phrase in joined_anchor for phrase in SKIP_ANCHOR):
        return "skip", 0
    if nav and len(segs) <= 2 and segs and anchor_text.strip():
        return "other", BASE_SCORE["other"]
    return "other", 0


def _host_allowed(host: str, base_domain: str) -> bool:
    if not host:
        return False
    if registrable_domain(host) != base_domain:
        return False
    labels = host.split(".")
    registrable_labels = base_domain.split(".")
    extra = labels[: len(labels) - len(registrable_labels)]
    return not any(label in SKIP_HOST_LABELS for label in extra)


def _is_nav(anchor) -> bool:
    if anchor.find_parent(["nav", "header"]) is not None:
        return True
    for parent in anchor.parents:
        names = " ".join(parent.get("class") or []) + " " + str(parent.get("id") or "") if hasattr(parent, "get") else ""
        if re.search(r"\b(menu|navbar|nav|navigation)\b", names.lower()):
            return True
    return False


def merge_candidates(pages: list[PageLink], extra_urls: list[str]) -> list[PageLink]:
    """Add sitemap URLs into the ranked list. Higher score wins on a tie URL."""
    best: dict[str, PageLink] = {canonical_key(item.url): item for item in pages}
    for raw in extra_urls:
        url = _normalize(raw)
        parsed = urlparse(url)
        path = parsed.path or "/"
        if path in ("", "/") or is_trap(path, parsed.query) or parsed.query:
            continue
        page_type, score = classify(path, "")
        if page_type in ("skip", "other") or score <= 0:
            continue
        key = canonical_key(url)
        existing = best.get(key)
        if existing is None or score > existing.score:
            best[key] = PageLink(url=url, label=path, score=score, page_type=page_type, source="sitemap")
    return rank(list(best.values()))


def rank(links: list[PageLink]) -> list[PageLink]:
    """Best candidates first, following the preference order About, Products, Services, Industries, Customers, Contact."""
    order = {kind: index for index, kind in enumerate(ORDER)}
    return sorted(links, key=lambda link: (order.get(link.page_type, 99), -link.score, len(urlparse(link.url).path), link.url))


def discover_pages(html: bytes | str, base_url: str) -> list[PageLink]:
    """Score same-site links by how useful they are for classification.

    Returns the best candidates first; the caller takes what fits in the page budget. The homepage itself is always page 1 and not listed here.
    Business pages come first (typed), then a few weak menu links ('other') that the caller uses only when the evidence is thin.
    """
    soup = BeautifulSoup(html, "lxml")
    base_domain = registrable_domain(base_url)
    base_key = canonical_key(base_url)
    best: dict[str, PageLink] = {}
    scanned = 0
    for anchor in soup.find_all("a", href=True):
        scanned += 1
        if scanned > config.MAX_LINKS_SCANNED or len(best) >= config.MAX_DISCOVERED_PER_SITE:
            break
        href = str(anchor["href"]).strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#", "data:", "sms:", "whatsapp:")):
            continue
        try:
            absolute = _normalize(urljoin(base_url, href))
            parsed = urlparse(absolute)
            host = parsed.hostname or ""
        except ValueError:
            continue
        if parsed.scheme not in ("http", "https") or not _host_allowed(host, base_domain):
            continue
        path = parsed.path or "/"
        if path in ("", "/") or canonical_key(absolute) == base_key:
            continue  # the homepage (or a duplicate of it)
        if is_trap(path, parsed.query) or (parsed.query and not any(k in parsed.query for k in ALLOWED_QUERY_KEYS)):
            continue
        anchor_text = anchor.get_text(" ", strip=True)[:120] or str(anchor.get("title") or anchor.get("aria-label") or "")[:120]
        nav = _is_nav(anchor)
        page_type, score = classify(path, anchor_text, nav)
        if page_type == "skip" or score <= 0:
            continue
        key = canonical_key(absolute)
        existing = best.get(key)
        if existing is None or score > existing.score:
            best[key] = PageLink(url=absolute, label=anchor_text or path, score=score, page_type=page_type, nav=nav,
                                 source="nav" if nav else "link")
    return rank(list(best.values()))
