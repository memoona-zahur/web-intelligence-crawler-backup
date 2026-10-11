"""Decide what an HTTP response really is: useful business content, or something else (CR-B02, B03, B04, D04).

HTTP 200 does not mean a useful page. `assess_page` looks at the cleaned text, the title and the raw HTML and returns ONE kind:

    challenge           anti-bot / CAPTCHA / 'checking your browser' page   -> status Blocked (never bypassed, never sent to the browser)
    login               password form or members-only wall                   -> Requires Review
    parked              for-sale / parking page                              -> Parked
    under_construction  coming soon, default server page                     -> Under Construction
    soft_404            'page not found' with HTTP 200                       -> Requires Review
    js_shell            empty application shell that a browser may fill      -> browser fallback (only here)
    thin                too little text to use                               -> Requires Review (after the browser had its chance)
    ok                  useful content

All wording lists are plain data at the top of the file so they can be extended without touching the logic. Text patterns only fire on SHORT
pages (a real company site that sells 'items for sale' is not a parked domain).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.crawler import config

# Phrases that show up on empty application shells, not on real copy.
_SHELL_HINTS = (
    "enable javascript",
    "you need to enable javascript",
    "please enable javascript",
    "javascript is required",
    "javascript is disabled",
    "this app works best with javascript",
)
_SHELL_ROOTS = (b'id="root"', b"id='root'", b'id="__next"', b'id="app"', b"id='app'", b'id="___gatsby"', b"ng-app", b"data-reactroot", b"<app-root", b'id="__nuxt"')

_CHALLENGE_STRONG = (
    "just a moment...", "checking your browser", "checking if the site connection is secure", "attention required! | cloudflare",
    "cf-browser-verification", "cf-chl-", "challenge-platform", "pardon our interruption", "_incapsula_resource", "incapsula incident",
    "px-captcha", "perimeterx", "datadome", "please verify you are a human", "verify you are human", "are you a robot",
    "unusual traffic from your computer", "ddos protection by", "sucuri website firewall", "request unsuccessful. incapsula",
    "access to this page has been denied", "you have been blocked", "why have i been blocked", "bot protection", "akamai reference",
)
_CHALLENGE_WEAK = ("captcha", "g-recaptcha", "hcaptcha", "access denied", "request blocked", "forbidden", "security check", "robot check")

_PARKED_PROVIDER_HOSTS = (
    "sedoparking", "sedo.com", "parkingcrew", "bodis.com", "above.com", "domainsponsor", "namedrive", "ztds.info", "afternic.com",
    "hugedomains.com", "dan.com", "undeveloped.com", "buydomains.com", "uniregistry", "parklogic", "fabulous.com", "voodoo.com",
    "domainmarket.com", "sav.com", "atom.com", "squadhelp.com", "brandbucket.com", "namesilo.com/domain", "godaddy.com/forsale",
    "domainnameshop", "parked-content", "searchhounds", "dsnextgen", "trafficz.com", "skenzo.com", "cashparking", "parkingpage",
)
_PARKED_PHRASES = (
    "this domain is for sale", "domain is for sale", "domain for sale", "buy this domain", "this domain may be for sale",
    "this domain name is for sale", "is for sale!", "make an offer on this domain", "inquire about this domain", "purchase this domain",
    "this web page is parked", "this site is parked", "parked domain", "parked free", "domain parking",
    "this domain has been registered", "this domain is registered", "domain is available", "register this domain",
    "this domain name has expired", "this domain has expired", "domain expired", "renew this domain", "related searches",
    "sponsored listings", "the sponsored listings displayed above", "domain is parked",
    "get this domain", "domain name for sale", "is available for purchase", "contact the domain owner",
)
_PARKED_STRONG = (
    "this domain is for sale", "domain is for sale", "buy this domain", "this domain may be for sale", "domain name is for sale",
    "this web page is parked", "this site is parked", "domain is parked", "parked free", "the sponsored listings displayed above",
    "this domain has expired", "this domain name has expired", "make an offer on this domain", "inquire about this domain",
    "purchase this domain", "domain for sale", "contact the domain owner",
)

_CONSTRUCTION_PHRASES = (
    "coming soon", "under construction", "site is under construction", "website under construction", "launching soon",
    "we are launching soon", "we're launching soon", "be right back", "our website is coming", "new website coming",
    "website coming soon", "page under construction", "site is temporarily unavailable", "maintenance mode", "scheduled maintenance",
    "we'll be back soon", "we will be back soon", "currently being built", "is being redesigned", "opening soon", "stay tuned",
    "something awesome is coming", "site en construction", "en construction", "seite im aufbau", "im aufbau", "website im aufbau",
    "en construccion", "en construcción", "in costruzione", "em construção", "em construcao", "website onder constructie",
)
_DEFAULT_SERVER_PHRASES = (
    "welcome to nginx", "apache2 ubuntu default page", "apache2 debian default page", "apache http server test page",
    "test page for the apache", "it works!", "iis windows server", "internet information services", "default web site page",
    "this is the default welcome page", "congratulations! your website is created", "web server's default page",
    "domain default page", "default parallels plesk page", "plesk default page", "cpanel", "site not found", "this site can't be reached",
    "future home of something quite cool", "is your new web server", "the web server software is running but no content has been added",
    "default page", "lighttpd", "welcome to centos", "welcome to openresty", "caddy works", "hello world!", "wordpress › installation",
    "no website configured", "no site configured", "account suspended", "this account has been suspended",
    "this website is not configured",
)

_LOGIN_PHRASES = (
    "this store is password protected", "enter store using password", "password protected", "members only", "member login",
    "please log in to view", "please login to view", "log in to continue", "sign in to continue", "restricted access",
    "you must be logged in", "authorized users only", "client login", "customer login", "enter password to view",
    "this page is password protected", "please enter your password", "protected by password",
)
_LOGIN_TITLE = re.compile(r"\b(log ?in|sign ?in|anmelden|iniciar sesi[oó]n|connexion|accedi|login required)\b", re.I)

# Chinese, Japanese and Korean text carries about 2.5 times as much meaning per character as English, so the "enough text" thresholds count it that way.
_CJK = re.compile("[぀-ヿ㐀-䶿一-鿿豈-﫿가-힯]")


def info_length(text: str) -> float:
    """Length of the text in English-equivalent characters (CJK characters count 2.5)."""
    return len(text) + 1.5 * len(_CJK.findall(text))


_SOFT404_TITLE = re.compile(
    r"(404|page not found|not found|nothing found|error 40\d|no longer available|doesn.?t exist|seite nicht gefunden|page introuvable|p[aá]gina no encontrada|"
    r"pagina non trovata|oops!?\b|something went wrong|this page can.?t be found|we can.?t find|couldn.?t find)",
    re.I,
)
_SOFT404_TEXT = (
    "sorry, the page you are looking for", "the page you are looking for could not", "page you were looking for",
    "page not found", "404 not found", "404 error", "error 404", "this page does not exist", "the page you requested could not be found",
    "the page you are looking for might have been removed", "nothing was found", "no longer exists", "we couldn't find that page",
    "page you're looking for doesn't exist", "page you are looking for doesn't exist", "seite wurde nicht gefunden", "page introuvable",
)


@dataclass
class PageAssessment:
    kind: str
    reasons: list[str] = field(default_factory=list)

    @property
    def is_ok(self) -> bool:
        return self.kind == "ok"


def looks_like_shell(text: str, html: bytes) -> bool:
    """True when the HTML likely needs a browser to reveal the page (empty application shell)."""
    if info_length(text) >= config.MIN_USEFUL_PAGE_CHARS:
        return False
    raw = html.decode("utf-8", errors="ignore").lower() if isinstance(html, (bytes, bytearray)) else str(html).lower()
    if any(hint in raw for hint in _SHELL_HINTS):
        return True
    return "<script" in raw


def page_is_useful(text: str) -> bool:
    return info_length(text) >= config.MIN_USEFUL_PAGE_CHARS


def _hits(haystack: str, phrases) -> list[str]:
    return [p for p in phrases if p in haystack]


def assess_page(text: str, title: str, html: bytes | str, final_host: str = "", status: int = 200) -> PageAssessment:
    """Classify one fetched page. `text` is the cleaned text, `html` the raw page (bytes or str)."""
    raw = html.decode("utf-8", errors="ignore") if isinstance(html, (bytes, bytearray)) else str(html)
    low_raw = raw[:400_000].lower()
    low_text = text.lower()
    low_title = (title or "").lower()
    n = len(text.strip())
    host = (final_host or "").lower()

    # --- challenge / anti-bot (CR-B04, F05): never bypassed ---
    strong = _hits(low_title + " " + low_text[:2500], _CHALLENGE_STRONG) + _hits(low_raw[:150_000], ("cf-browser-verification", "cf-chl-", "challenge-platform", "_incapsula_resource", "px-captcha", "datadome"))
    if strong and n < 1500:
        return PageAssessment("challenge", strong[:3])
    weak = _hits(low_title + " " + low_text[:1500], _CHALLENGE_WEAK)
    if weak and n < 400:
        return PageAssessment("challenge", weak[:3])

    # --- login / password wall ---
    has_password_field = bool(re.search(r"<input[^>]+type\s*=\s*[\"']?password", low_raw))
    login_hits = _hits(low_text[:2500], _LOGIN_PHRASES)
    if (has_password_field and n < 700) or (login_hits and n < 900) or (_LOGIN_TITLE.search(low_title) and n < 500 and has_password_field):
        return PageAssessment("login", login_hits[:3] or ["password form"])

    # --- parked / for sale ---
    provider_hits = [h for h in _PARKED_PROVIDER_HOSTS if h in low_raw or h in host]
    phrase_hits = _hits(low_text[:3000] + " " + low_title, _PARKED_PHRASES)
    strong_phrase = [p for p in phrase_hits if p in _PARKED_STRONG]
    if host.endswith(("hugedomains.com", "afternic.com", "dan.com", "sedo.com", "sav.com", "atom.com", "brandbucket.com", "squadhelp.com")):
        return PageAssessment("parked", [f"landed on marketplace {host}"])
    if n < 2500 and (strong_phrase or len(phrase_hits) >= 2 or (provider_hits and (phrase_hits or n < 600))):
        return PageAssessment("parked", (strong_phrase or phrase_hits or provider_hits)[:3])

    # --- under construction / default server page ---
    default_hits = _hits(low_title + " " + low_text[:1500], _DEFAULT_SERVER_PHRASES)
    build_hits = _hits(low_title + " " + low_text[:1500], _CONSTRUCTION_PHRASES)
    if n < 900 and (default_hits or build_hits):
        return PageAssessment("under_construction", (default_hits or build_hits)[:3])

    # --- soft 404 (HTTP 200 on an error page) ---
    if n < 800 and (_SOFT404_TITLE.search(low_title) or _hits(low_text[:1500], _SOFT404_TEXT)):
        return PageAssessment("soft_404", [title or "error text"])

    # --- JS shell / empty / thin ---
    if info_length(text.strip()) < config.MIN_USEFUL_PAGE_CHARS:
        if any(h in low_raw for h in _SHELL_HINTS) or any(r.decode() in low_raw for r in _SHELL_ROOTS) or "<script" in low_raw:
            return PageAssessment("js_shell", ["little text and a script-driven page"])
        if n == 0:  # CR-B03 "empty website": no text at all and nothing a browser could add
            return PageAssessment("under_construction", ["empty page (no text at all)"])
        return PageAssessment("thin", [f"{n} characters of text"])
    return PageAssessment("ok")
