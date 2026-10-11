"""Hand-designed dataset rows: public test endpoints, local scenarios, input-handling inputs.

Oracles (expected_outcome) are decided from the requirements and standards (RFC 9309 robots, RFC 6761 reserved
names, HTTP semantics) - NOT from running the existing crawler.
Each row: dict(category, subcategory, url, source_type, expected_outcome, expected_status, why, source, method, notes, tags)
"""
from __future__ import annotations

from urllib.parse import quote

BASE = 8800
SC = lambda n: f"http://127.0.0.1:{BASE + n}/"  # noqa: E731
HB = "https://httpbin.org"
SRC_HB = "httpbin.org public test service (endpoint list: https://httpbin.org/spec.json)"
SRC_SC = "crawl_eval/scenario_server.py (own server, 127.0.0.1 only)"
SRC_BS = "https://badssl.com/ (public TLS test site; subdomain list read from its homepage)"
SRC_RFC = "RFC 2606 / RFC 6761 reserved names (guaranteed not to exist)"
SRC_IANA = "IANA reserved example domains (example.com / .org / .net)"


def R(category, subcategory, url, source_type, outcome, status, why, source, method, notes="", tags=""):
    return dict(category=category, subcategory=subcategory, url=url, source_type=source_type, expected_outcome=outcome,
                expected_status=status, why_included=why, source_of_url=source, verification_method=method, notes=notes, tags=tags)


rows: list[dict] = []

# ---------------- dead domains (reserved names) ----------------
for i in range(1, 9):
    rows.append(R("Dead domains (NXDOMAIN)", "reserved .invalid name", f"http://crawl-eval-dead-{i}.invalid/", "public-test-endpoint",
                  "Unreachable", "dns:NXDOMAIN", "RFC 2606 guarantees .invalid never resolves", SRC_RFC, "dns:NXDOMAIN(1.1.1.1,8.8.8.8)+system-resolver-fail",
                  "expected reason: DNS failure, not 'invalid URL'"))
for i in range(1, 3):
    rows.append(R("Dead domains (NXDOMAIN)", "reserved .test name", f"https://crawl-eval-dead-{i}.test/about", "public-test-endpoint",
                  "Unreachable", "dns:NXDOMAIN", "RFC 6761 reserves .test; never resolves", SRC_RFC, "dns:NXDOMAIN(1.1.1.1,8.8.8.8)"))

# ---------------- HTTP error classes (httpbin) ----------------
for code, outcome, why in [(401, "Blocked", "auth required"), (403, "Blocked", "forbidden"), (404, "Failed", "not found"),
                           (410, "Failed", "gone"), (429, "Blocked", "rate limited: crawler must slow down / stop, never hammer"),
                           (500, "Failed", "server error"), (502, "Failed", "bad gateway"), (503, "Failed", "unavailable: retry then fail")]:
    rows.append(R("HTTP errors", f"{code} (httpbin)", f"{HB}/status/{code}", "public-test-endpoint", outcome, f"http:{code}",
                  f"HTTP {code} homepage: {why}", SRC_HB, f"GET->{code} (see statics_verified.json)"))

# ---------------- timeouts / slow (httpbin + scenario) ----------------
rows.append(R("Timeouts / refused / slow", "drip 30s (httpbin)", f"{HB}/drip?duration=30&numbytes=30&code=200", "public-test-endpoint", "Unreachable", "timeout",
              "bytes arrive slowly over 30 s", SRC_HB, "GET observed: 29 s total, status 200 (verified 2026-10-10)", "httpbin /delay/N is capped at 10 s so it is not used", "slow-body"))
for n, sub, outcome, st, why, notes in [
    (1, "slow-drip body 2 min", "Unreachable", "timeout", "1 byte per 0.5 s for 2 min: total time must be bounded", "total time cap, not just per-read timeout"),
    (2, "server never answers", "Unreachable", "timeout", "request hangs 60 s", ""),
    (3, "slow headers 20s", "Unreachable", "timeout", "first byte after 20 s", "ambiguous-oracle if timeout > 20 s")]:
    rows.append(R("Timeouts / refused / slow", sub, SC(n), "local-scenario", outcome, st, why, SRC_SC, "scenario_server verified (verify_scenarios.py)", notes,
                  "scenario;ambiguous-oracle" if n == 3 else "scenario"))
rows.append(R("Timeouts / refused / slow", "connection refused (closed loopback port)", "http://127.0.0.1:8899/", "local-scenario", "Unreachable", "refused",
              "nothing listens on this port", SRC_SC, "port verified closed (connection refused)", "needs scenario-host allowance like other scenario rows", "scenario"))

# ---------------- SSL/TLS (badssl) ----------------
BADSSL = [("expired", "expired certificate"), ("wrong.host", "certificate for another host name"), ("self-signed", "self-signed certificate"),
          ("untrusted-root", "chain ends in untrusted root"), ("incomplete-chain", "server omits intermediate certificate"),
          ("revoked", "revoked certificate"), ("no-common-name", "certificate without common name"), ("no-subject", "certificate without subject"),
          ("edellroot", "Dell eDellRoot (untrusted)"), ("superfish", "Superfish (untrusted)"), ("dsdtestprovider", "DSD test provider root (untrusted)"),
          ("pinning-test", "certificate pinning test"), ("null", "NULL cipher"), ("rc4", "RC4 cipher"), ("rc4-md5", "RC4-MD5 cipher"),
          ("3des", "3DES cipher"), ("dh480", "weak DH 480"), ("dh512", "weak DH 512"), ("tls-v1-0", "only TLS 1.0"), ("tls-v1-1", "only TLS 1.1"),
          ("sha1-intermediate", "SHA-1 intermediate"), ("mitm-software", "MITM software root")]

# ---------------- robots.txt (httpbin) ----------------
rows.append(R("robots.txt", "disallowed path (httpbin /deny)", f"{HB}/deny", "public-test-endpoint", "Blocked", "robots",
              "httpbin's robots.txt says 'User-agent: *  Disallow: /deny'", SRC_HB, "robots.txt read: Disallow: /deny"))

# ---------------- non-HTML / heavy (httpbin) ----------------
for path, sub in [("json", "JSON"), ("xml", "XML"), ("image/png", "PNG image"), ("image/svg", "SVG image"), ("gzip", "gzip JSON"),
                  ("deflate", "deflate JSON"), ("brotli", "brotli JSON"), ("bytes/2048", "random bytes"), ("stream-bytes/300000", "300 KB stream of bytes"),
                  ("uuid", "tiny JSON"), ("robots.txt", "plain text"), ("range/1024", "range bytes")]:
    rows.append(R("Non-HTML and heavy content", f"{sub} (httpbin)", f"{HB}/{path}", "public-test-endpoint", "Failed", "not-html",
                  f"homepage is {sub}, not a web page", SRC_HB, "GET observed content-type", "expected reason: not HTML"))

# ---------------- encoding (httpbin) ----------------
rows.append(R("Encoding oddities", "UTF-8 demo page (httpbin)", f"{HB}/encoding/utf8", "public-test-endpoint", "Crawled", "http:200",
              "page full of non-ASCII UTF-8 characters", SRC_HB, "GET 200 text/html utf-8", "text must not be mojibake"))

# ---------------- redirects (httpbin) ----------------
dest = "https://example.com/"
rows.append(R("Redirect behaviour", "cross-domain 302 (httpbin->example.com)", f"{HB}/redirect-to?url={quote(dest, safe='')}", "public-test-endpoint", "Redirected", "final:example.com",
              "302 to another domain: final URL recorded, status Redirected", SRC_HB, "redirect chain observed", "Crawled+final_url recorded = partial credit", "ambiguous-oracle"))
rows.append(R("Redirect behaviour", "cross-domain 301 (httpbin->example.org)", f"{HB}/redirect-to?url={quote('https://example.org/', safe='')}&status_code=301", "public-test-endpoint", "Redirected", "final:example.org",
              "301 to another domain", SRC_HB, "redirect chain observed", "", "ambiguous-oracle"))
rows.append(R("Redirect behaviour", "307 (httpbin->example.net)", f"{HB}/redirect-to?url={quote('https://example.net/', safe='')}&status_code=307", "public-test-endpoint", "Redirected", "final:example.net",
              "307 to another domain", SRC_HB, "redirect chain observed", "", "ambiguous-oracle"))


def nested(depth: int) -> str:
    url = dest
    for _ in range(depth):
        url = f"{HB}/redirect-to?url={quote(url, safe='')}"
    return url


for depth, outcome, note in [(2, "Redirected", ""), (4, "Redirected", ""), (7, "Redirected", "ambiguous-oracle: browsers allow 20 hops"),
                             (12, "Failed", "more than 10 hops: give up with 'too many redirects'")]:
    rows.append(R("Redirect behaviour", f"chain of {depth} httpbin hops -> example.com", nested(depth), "public-test-endpoint", outcome, f"hops:{depth}",
                  "redirect depth handling", SRC_HB, "redirect chain observed", note, "ambiguous-oracle" if depth == 7 else ""))
rows.append(R("Redirect behaviour", "httpbin redirect to private loopback target", f"{HB}/redirect-to?url={quote(f'http://127.0.0.2:{BASE + 10}/secret', safe='')}", "local-scenario",
              "Invalid", "ssrf-redirect", "public host redirects to a loopback address on this machine: must be refused, secret text must not be stored",
              SRC_HB + " + " + SRC_SC, "redirect Location verified; target serves SECRET-TOKEN-4711", "pass criterion: 'SECRET-TOKEN-4711' absent from stored text", "ssrf;scenario-host"))

# ---------------- login-walled (httpbin) ----------------
rows.append(R("Login-walled", "HTTP basic-auth (httpbin)", f"{HB}/basic-auth/user/passwd", "public-test-endpoint", "Blocked", "http:401",
              "page requires credentials; crawler must not try to log in", SRC_HB, "GET->401 + WWW-Authenticate", "no login attempts allowed"))
rows.append(R("Login-walled", "bearer token required (httpbin)", f"{HB}/bearer", "public-test-endpoint", "Blocked", "http:401",
              "page requires a token", SRC_HB, "GET->401"))

# ---------------- thin / empty looks-successful (httpbin) ----------------
rows.append(R("Thin / empty / error-only pages", "empty 200 (httpbin /status/200)", f"{HB}/status/200", "public-test-endpoint", "Under Construction", "http:200",
              "HTTP 200 with an empty body must not become 'crawled'", SRC_HB, "GET->200, 0 bytes"))

# ---------------- local scenarios ----------------
S = lambda cat, sub, n, outcome, status, why, notes="", tags="scenario": rows.append(  # noqa: E731
    R(cat, sub, SC(n), "local-scenario", outcome, status, why, SRC_SC, "scenario_server verified (verify_scenarios.py)", notes, tags))
H = "Non-HTML and heavy content"
S(H, "huge body 60 MB, no Content-Length", 4, "Failed", "too-large", "size must be capped while reading, not after downloading")
S(H, "gzip bomb page (150 MB expanded)", 5, "Failed", "too-large", "decompression must be capped")
S(H, "PDF served as homepage", 6, "Failed", "not-html", "PDF is not an HTML page")
S(H, "gzip sitemap bomb in robots.txt", 7, "Crawled", "http:200", "homepage fine; sitemap must be ignored safely (memory/time)", "pass: run finishes, bounded memory", "scenario;sitemap")
S(H, "entity-expansion sitemap", 8, "Crawled", "http:200", "XML entity expansion must not hang or exhaust memory", "", "scenario;sitemap")
S(H, "huge sitemap (50,000 URLs)", 17, "Crawled", "http:200", "never crawl a whole sitemap blindly (CR-C08)", "pass: pages <= budget", "scenario;sitemap")
S(H, "malformed sitemap.xml", 15, "Crawled", "http:200", "fall back to homepage links when sitemap is broken (CR-C08)", "", "scenario;sitemap")
S(H, "sitemap index + .gz; business pages on non-standard paths", 16, "Crawled", "http:200", "should discover /what-we-do and /who-we-serve (CR-C05, CR-C08)", "gold: /what-we-do, /who-we-serve", "scenario;sitemap;gold")
S(H, "JSON as homepage", 40, "Failed", "not-html", "API response is not a web page")
RB = "Redirect behaviour"
S(RB, "redirect loop", 9, "Failed", "redirect-loop", "must stop and report a redirect loop")
S(RB, "9-hop redirect chain then good page", 14, "Crawled", "hops:9", "long but finite chain", "ambiguous-oracle: depends on redirect limit", "scenario;ambiguous-oracle")
S(RB, "meta-refresh redirect", 37, "Crawled", "http:200", "content is at /real; a meta-refresh page has no content itself", "", "scenario")
S(RB, "JavaScript redirect", 38, "Crawled", "http:200", "content is at /real; needs JS (browser fallback) or must be reported as thin", "", "scenario")
S(RB, "redirect to login page", 39, "Requires Review", "login-wall", "ends on a sign-in form: not business content")
S(RB, "redirect to secret page on 127.0.0.2", 10, "Invalid", "ssrf-redirect", "redirect to loopback must be refused", "pass: 'SECRET-TOKEN-4711' absent", "scenario;ssrf")
RT = "Crawl traps"
S(RT, "infinite calendar", 11, "Crawled", "budget", "must stop at the page budget; no /cal/ pages beyond the budget", "pass: <=10 pages, no calendar pages crawled", "scenario;trap")
S(RT, "session-id URLs", 12, "Crawled", "budget", "same pages with different ?sid= must count as duplicates", "pass: no duplicate page fetched", "scenario;trap")
S(RT, "faceted navigation", 13, "Crawled", "budget", "40 filter combinations on one page: must not crawl them", "pass: <=10 pages, filter URLs skipped", "scenario;trap")
S(RT, "deep link chain", 41, "Crawled", "budget", "each page links only to the next level", "pass: stops early", "scenario;trap")
S(RT, "infinite pagination ?page=N", 44, "Crawled", "budget", "list pages never end", "pass: <=10 pages, at most 1 ?page= URL fetched", "scenario;trap")
S(RT, "day-level calendar (next/previous day, next year)", 45, "Crawled", "budget", "calendar days are unbounded in both directions", "pass: <=10 pages, no /day/ URL beyond 1", "scenario;trap")
S(RT, "session ID in URL path", 46, "Crawled", "budget", "same pages under a new /s/<id>/ prefix on every response", "pass: each business page fetched at most once", "scenario;trap")
S(RT, "session-ID redirect on every first request", 47, "Crawled", "budget", "every URL redirects to ?PHPSESSID=<new>; content is normal", "pass: site crawled, <=10 pages, no loop", "scenario;trap")
S(RT, "faceted navigation, 96 filter/sort combinations", 48, "Crawled", "budget", "sort/dir/per_page/view combinations on one page", "pass: <=10 pages, <=1 faceted URL fetched", "scenario;trap")
S(RT, "homepage redirects to endless new URLs", 49, "Failed", "redirect-loop", "?n=1,2,3... redirect forever: must stop and report", "pass: stops within the redirect limit, status Failed with a reason", "scenario;trap;redirect")
S(RT, "redirect loop across two origins", 50, "Failed", "redirect-loop", "8850 -> 8851 -> 8850 ...", "pass: stops, status Failed, reason mentions redirects", "scenario;trap;redirect")
S(RT, "path keeps growing /a/a/a", 52, "Crawled", "budget", "each archive page links one level deeper", "pass: <=10 pages, depth of /a/ chain <=2", "scenario;trap")
S(RT, "link explosion (30 new links per page)", 53, "Crawled", "budget", "each product page links to 30 new product pages", "pass: <=10 pages in total", "scenario;trap")
S(RT, "relative link without slash grows /docs/docs", 54, "Crawled", "budget", "a broken relative href creates ever longer paths", "pass: <=10 pages, /docs/ chain depth <=2", "scenario;trap")
S(RT, "random soft-404s (every unknown URL is 200)", 55, "Crawled", "budget", "any URL answers 200 and links to more random URLs", "pass: <=10 pages, random /x-N pages <=1", "scenario;trap")
S(RT, "case / slash / index / utm duplicates", 56, "Crawled", "budget", "/About, /about/, /ABOUT/, /about/index.html, ?utm_source= all serve the same page", "pass: /about content stored once (dedupe, CR-C09/C10)", "scenario;trap;duplicates")
S(RT, "50 mirrored pages with identical text", 57, "Crawled", "budget", "identical content at 50 URLs", "pass: identical text stored once; <=3 mirror pages fetched", "scenario;trap;duplicates")
S(RT, "endless sitemap index chain", 58, "Crawled", "budget", "sm0.xml -> sm1.xml -> ... never ends", "pass: finishes; sitemap files fetched <=5", "scenario;trap;sitemap")
S(RT, "infinite scroll ?offset=N", 59, "Crawled", "budget", "load-more feed with no end", "pass: <=10 pages, <=1 ?offset= URL fetched", "scenario;trap")
S(RT, "endless tag graph (20 new tag pages per page)", 60, "Crawled", "budget", "tag pages link to 20 fresh tag pages each", "pass: <=10 pages, <=1 /t/ page fetched", "scenario;trap")
RO = "robots.txt"
S(RO, "disallow all", 18, "Blocked", "robots", "robots.txt: Disallow: / for everyone", "pass: zero page fetches after robots.txt")
S(RO, "partial disallow (/about)", 19, "Crawled", "http:200", "/about is disallowed, others allowed", "pass: /about never fetched")
S(RO, "crawl-delay 10", 20, "Crawled", "http:200", "crawler should honour or at least not violate Crawl-delay: 10", "timing check between requests", "scenario;timing")
S(RO, "malformed robots.txt", 21, "Crawled", "http:200", "garbage robots file: ignore invalid lines; crawl normally", "", "scenario;ambiguous-oracle")
S(RO, "robots.txt returns 503", 22, "Blocked", "robots-5xx", "RFC 9309 s2.3.1.4: server error on robots.txt -> assume complete disallow", "documented policy needed (CR-F01)", "scenario;ambiguous-oracle")
S(RO, "robots.txt is an HTML page (200)", 23, "Crawled", "http:200", "no valid rules found -> allow", "", "scenario")
HE = "HTTP errors"
S(HE, "429 with Retry-After: 5", 24, "Blocked", "http:429", "must honour Retry-After / slow down; never hammer", "timing: check retries", "scenario;retry-after")
S(HE, "503 with Retry-After: 5", 25, "Failed", "http:503", "retry politely (respect Retry-After) then fail", "timing: check retries", "scenario;retry-after")
S(HE, "403 Forbidden", 42, "Blocked", "http:403", "access denied")
S(HE, "500 Internal Server Error", 43, "Failed", "http:500", "server error")
TH = "Thin / empty / error-only pages"
S(TH, "HTTP 200 soft-404 text", 26, "Requires Review", "http:200", "200 status but content says 'Page not found'")
S(TH, "HTTP 200 empty body", 27, "Under Construction", "http:200", "empty site")
UC = "Under construction / default pages"
S(UC, "nginx default welcome page", 28, "Under Construction", "http:200", "default server page, no business content")
S(UC, "'Coming soon' page", 29, "Under Construction", "http:200", "placeholder page")
PK = "Parked / for-sale domains"
S(PK, "parked / for-sale page (synthetic)", 30, "Parked", "http:200", "domain-for-sale landing page")
LW = "Login-walled"
S(LW, "member login landing page", 31, "Requires Review", "login-wall", "only a sign-in form")
BP = "Bot-protected / WAF"
S(BP, "bot challenge ('Just a moment...') 403", 32, "Blocked", "http:403", "challenge page: record as blocked, never bypass")
EN = "Encoding oddities"
S(EN, "latin-1 bytes, no charset declared", 33, "Crawled", "http:200", "German text with umlauts must decode correctly", "pass: 'Café Müller', 'Größere' readable", "scenario;encoding")
S(EN, "Shift_JIS body, header says UTF-8", 34, "Crawled", "http:200", "wrong header: text should still be recovered", "pass: Japanese text readable", "scenario;encoding;ambiguous-oracle")
S(EN, "UTF-8 with BOM", 35, "Crawled", "http:200", "BOM must not appear in text", "", "scenario;encoding")
S(EN, "UTF-16 with BOM", 36, "Crawled", "http:200", "UTF-16 page should decode", "", "scenario;encoding")

# ---------------- input handling ----------------
IN = "Input handling"


def I(sub, url, outcome, status, why, notes="", tags="", stype="public-test-endpoint", method="static-not-probed (input-only row)", source="designed by hand (see notes)"):  # noqa: E741, E501
    rows.append(R(IN, sub, url, stype, outcome, status, why, source, method, notes, tags))


DUP = "import:duplicate"
ADD = "import:added"
M = "dns+GET verified for example.com/.org/.net (IANA reserved example domains)"
I("canonical form", "https://example.com/", "Crawled", ADD, "baseline: clean URL, first of its group", method=M, source=SRC_IANA)
for u, sub, tag in [("http://example.com", "http scheme", ""), ("https://www.example.com", "www prefix", ""), ("http://www.example.com/", "http+www+slash", ""),
                    ("HTTPS://EXAMPLE.COM", "upper-case", ""), ("example.com", "no scheme", ""), ("www.example.com", "no scheme + www", ""),
                    ("EXAMPLE.com/", "mixed case + slash", ""), ("https://example.com/index.html", "path to index", ""),
                    ("https://example.com/about?utm_source=x#top", "path+query+fragment", ""), ("example.com:443", "default https port, no scheme", ""),
                    ("http://example.com:80/", "default http port", ""), ("  https://example.com  ", "surrounding spaces", ""),
                    ("'https://example.com'", "single-quoted", ""), ("https://example.com.", "trailing dot (FQDN)", ""),
                    ("https://www.example.com./", "www + trailing dot + slash", ""), ("//example.com", "scheme-relative", "ambiguous-oracle"),
                    ("https://example.com//", "double slash", ""), ("https://example.com/?", "empty query", ""),
                    ("ｅｘａｍｐｌｅ．ｃｏｍ", "full-width characters", "ambiguous-oracle")]:
    I(sub, u, "Duplicate", DUP, "same site as https://example.com in a different spelling (dedup CR-A06/B05)", "duplicate of the canonical example.com row", tag, source=SRC_IANA, method=M)
I("credentials in URL", "https://user:secret@example.com/", "Duplicate", DUP, "same site; the password must not be stored (CR-F08)", "pass: 'secret' not stored anywhere", "security", source=SRC_IANA, method=M)
I("canonical form", "https://example.org/", "Crawled", ADD, "second site, canonical", method=M, source=SRC_IANA)
for u, sub in [("http://WWW.Example.Org/", "upper-case + www + http"), ("example.org/some/path.html", "bare + deep path"), ("https://example.org:443", "explicit port")]:
    I(sub, u, "Duplicate", DUP, "same site as https://example.org", "duplicate of the example.org canonical row", source=SRC_IANA, method=M)
I("canonical form", "http://example.net", "Crawled", ADD, "third site, http only", method=M, source=SRC_IANA)
I("tracking parameters", "https://www.example.net/?utm_source=newsletter&utm_medium=email", "Duplicate", DUP, "same site with tracking query", source=SRC_IANA, method=M)

# IDN
I("IDN: unicode form", "münchen.de", "Crawled", ADD, "real IDN domain typed with umlaut; must convert to punycode and resolve", "punycode = xn--mnchen-3ya.de", "idn",
  stype="real", method="dns:A(1.1.1.1 + system) resolves via punycode", source="DNS check run in this project (2026-10-10)")
I("IDN: punycode form", "xn--mnchen-3ya.de", "Duplicate", DUP, "same IDN site in punycode form", "duplicate of münchen.de", "idn", stype="real",
  method="dns:A resolves", source="DNS check run in this project (2026-10-10)")
I("IDN: unicode form", "https://bücher.de/", "Crawled", ADD, "second real IDN domain", "punycode = xn--bcher-kva.de", "idn", stype="real", method="dns:A resolves", source="DNS check run in this project (2026-10-10)")
I("IDN: emoji domain", "http://💩.la", "Crawled", ADD, "real emoji domain (xn--ls8h.la)", "must not crash", "idn", stype="real", method="dns:A resolves", source="DNS check run in this project (2026-10-10)")

# public IP literals
I("public IP literal", "http://94.140.14.14", "Redirected", ADD, "valid public IP address typed as a site; it redirects (302) to a named site", "302 -> https://adguard-dns.io; reachable from Lahore (other public IPs such as 1.1.1.1 / 8.8.8.8 time out here)", "ip-literal;network-dependent", stype="real",
  method="GET 302 verified from Lahore on 2026-10-10", source="IP of a public DNS service found by trying well-known public DNS addresses from this network")
I("public IP literal", "http://208.67.222.222", "Failed", ADD, "valid public IP address typed as a site; it answers HTTP 404", "HTTP 404 HTML page; reachable from Lahore", "ip-literal;network-dependent", stype="real",
  method="GET 404 verified from Lahore on 2026-10-10", source="IP of a public DNS service found by trying well-known public DNS addresses from this network")

# private/loopback/restricted -> must be refused
PRIV = [("localhost", "bare localhost"), ("http://localhost", "localhost"), ("http://localhost:8000/admin", "localhost with port"),
        ("http://127.0.0.1", "loopback IPv4"), ("https://127.0.0.1:8080/admin", "loopback with port"), ("http://127.1", "short-form loopback"),
        ("http://2130706433", "decimal-encoded 127.0.0.1"), ("http://0x7f000001", "hex-encoded 127.0.0.1"), ("http://0177.0.0.1", "octal-encoded 127.0.0.1"),
        ("http://[::1]/", "IPv6 loopback"), ("http://[::ffff:127.0.0.1]/", "IPv4-mapped IPv6 loopback"), ("http://0.0.0.0", "unspecified address"),
        ("http://10.0.0.1", "private 10/8"), ("http://172.16.0.1", "private 172.16/12"), ("http://192.168.1.1/admin", "private 192.168/16"),
        ("http://169.254.169.254/latest/meta-data/", "cloud metadata (link-local)"), ("http://metadata.google.internal/computeMetadata/v1/", "GCP metadata name"),
        ("http://100.100.100.200/latest/meta-data/", "Alibaba metadata in CGNAT range 100.64/10"), ("http://224.0.0.1", "multicast"),
        ("http://255.255.255.255", "broadcast"), ("http://intranet.local", ".local name"), ("http://printer.internal", ".internal name"),
        ("http://nas.lan", ".lan name (non-public)"), ("http://router.home.arpa", ".home.arpa name (non-public)"),
        ("http://example.com@127.0.0.1/", "user-info trick: real host is 127.0.0.1"), ("http://127.0.0.1#@example.com/", "fragment trick")]
for u, sub in PRIV:
    I("private/loopback target", u, "Invalid", "import:invalid", f"{sub}: must be refused (SSRF, CR-B09/B10)", "never fetched by us; pass = refused with a clear reason", "ssrf", method="static-not-probed (never contacted)", source="designed by hand (SSRF cases)")
for u, sub in [("http://localtest.me/", "public name that resolves to 127.0.0.1"), ("http://lvh.me/", "public name that resolves to 127.0.0.1")]:
    I("public name -> loopback IP", u, "Invalid", "dns:loopback", f"{sub}: guard must check the resolved address", "DNS resolves to 127.0.0.1 (verified); pass = refused at fetch time", "ssrf;dns-rebind-like", stype="real",
      method="dns:A=127.0.0.1 (1.1.1.1 + system resolver)", source="DNS check run in this project (2026-10-10)")

# malformed / unsupported
for u, sub in [("not a website", "words"), ("http://", "scheme only"), ("https://", "scheme only (https)"), ("://example.com", "missing scheme name"),
               ("htp://example.com", "typo scheme"), ("ftp://example.com", "unsupported scheme"), ("javascript:alert(1)", "javascript: URL"),
               ("mailto:info@example.com", "mailto"), ("file:///etc/passwd", "file: URL"), ("data:text/html,<h1>x</h1>", "data: URL"),
               ("http://exa mple.com", "space inside host"), ("http://example..com", "empty label"), ("http://.example.com", "leading dot"),
               ("http://-example.com", "leading hyphen"), ("example", "single word, no dot"), ("http://example", "no TLD"), ("http://example.com:99999", "port out of range"),
               ("http://example.com:abc", "non-numeric port"), ("http://256.256.256.256", "invalid IPv4"), ("http://[invalid", "broken IPv6 bracket"),
               ("https://" + "a" * 64 + ".com", "label longer than 63 chars"), ("https://" + ".".join(["a" * 60] * 5) + ".com", "host longer than 253 chars")]:
    I("malformed / unsupported", u if len(u) < 120 else u, "Invalid", "import:invalid", f"{sub}", "", "malformed")
for u, sub in [('=HYPERLINK("http://evil.test","click")', "spreadsheet formula"), ("+cmd|' /C calc'!A0", "formula with +"), ("@SUM(1+1)", "formula with @"), ("-2+3", "formula with -")]:
    I("spreadsheet-formula input", u, "Invalid", "import:invalid", f"{sub}: not a URL; must never reach an export as a live formula (CR-E11)", "", "security;formula")
for u, sub in [("# this is a comment", "comment line"), ("url", "CSV header word"), ("Website", "CSV header word")]:
    I("non-data lines", u, "Invalid", "import:invalid", f"{sub} pasted into the list: must not become a site", "", "malformed")
I("very long URL", "https://example.com/" + "a" * 3000, "Duplicate", DUP, "3,000-character path; must neither crash nor truncate silently", "duplicate of example.com", "long", source=SRC_IANA, method=M)
I("very long URL", "https://example.com/?q=" + "x" * 12000, "Duplicate", DUP, "12,000-character query", "duplicate of example.com", "long", source=SRC_IANA, method=M)

# ---- trim to the 80-row quota: drop low-value near-duplicates (decided by hand, not by the tail) ----
_DROP = {"https://example.com/?", "https://example.com//", "EXAMPLE.com/", "https://example.org:443", "http://255.255.255.255", "http://.example.com",
         "http://-example.com", "-2+3", "Website", "http://example.com:abc", "http://256.256.256.256", "data:text/html,<h1>x</h1>"}
rows[:] = [r for r in rows if not (r["category"] == "Input handling" and r["url"] in _DROP)]
