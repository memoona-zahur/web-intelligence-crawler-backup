# Dataset summary – `testing_URLs.csv`

File: `crawl_eval/dataset/testing_URLs.csv` · 988 rows · SHA-256 `0963ab3fead262c89d249e1f8d421eed857dc07968af65294e8e12f35c74c2bb` · built 2026-10-10 (seed 20261010).

**The target was 1,000 rows. This file has 988.** The 12 missing rows are accepted shortfalls (listed below). Nothing was padded.

## 1. Counts per category (target vs. actual)

| Group | Category | Target | Actual | Real sites | Test endpoints | Local scenarios | Smoke |
|---|---|---:|---:|---:|---:|---:|---:|
| Happy | Corporate / B2B services | 70 | 70 | 70 | 0 | 0 | 7 |
| Happy | Manufacturers, industrial, distributors, wholesalers | 60 | 60 | 60 | 0 | 0 | 6 |
| Happy | E-commerce and retail | 60 | 60 | 60 | 0 | 0 | 6 |
| Happy | SaaS / software / platforms | 60 | 60 | 60 | 0 | 0 | 6 |
| Happy | Healthcare, education, finance, real estate, non-profit, government | 80 | 80 | 80 | 0 | 0 | 8 |
| Happy | Small local businesses on site builders | 60 | 60 | 60 | 0 | 0 | 6 |
| Happy | Large multinational enterprises | 30 | 30 | 30 | 0 | 0 | 3 |
| Happy | Non-English / international | 80 | 80 | 80 | 0 | 0 | 8 |
| Happy | JavaScript-heavy SPAs | 50 | 50 | 50 | 0 | 0 | 5 |
| Happy | Minimal / one-page / static sites | 30 | 30 | 30 | 0 | 0 | 3 |
| Happy | Sitemap variants and non-standard navigation | 20 | 20 | 20 | 0 | 0 | 2 |
| Error/edge | Dead domains (NXDOMAIN) | 30 | 30 | 20 | 10 | 0 | 3 |
| Error/edge | Parked / for-sale domains | 30 | 30 | 29 | 0 | 1 | 3 |
| Error/edge | Under construction / default pages | 25 | 16 **SHORT** | 14 | 0 | 2 | 2 |
| Error/edge | Timeouts / refused / slow | 25 | 25 | 20 | 1 | 4 | 2 |
| Error/edge | SSL/TLS problems | 20 | 20 | 6 | 14 | 0 | 2 |
| Error/edge | HTTP errors | 30 | 30 | 18 | 8 | 4 | 3 |
| Error/edge | Redirect behaviour | 40 | 40 | 26 | 7 | 7 | 4 |
| Error/edge | Bot-protected / WAF | 25 | 25 | 24 | 0 | 1 | 2 |
| Error/edge | robots.txt | 20 | 20 | 13 | 1 | 6 | 2 |
| Error/edge | Non-HTML and heavy content | 15 | 15 | 0 | 6 | 9 | 2 |
| Error/edge | Login-walled | 10 | 7 **SHORT** | 4 | 2 | 1 | 1 |
| Error/edge | Encoding oddities | 15 | 15 | 10 | 1 | 4 | 2 |
| Error/edge | Input handling | 80 | 80 | 8 | 72 | 0 | 8 |
| Error/edge | Thin / empty / error-only pages | 15 | 15 | 12 | 1 | 2 | 2 |
| Error/edge | Crawl traps | 20 | 20 | 0 | 0 | 20 | 2 |
| | **Total** | 1000 | **988** | 804 | 123 | 61 | 100 |

Happy path: **600** of 600. Error/edge path: **388** of 400. Smoke subset: **100** rows, every category represented.

## 2. Shortfalls (not padded) and why

| Category | Missing | Why | Options |
|---|---:|---|---|
| Under construction / default pages | 9 | Only 14 real placeholder / default-server pages were found among ~6,400 probed domains (0.2%); with 2 local scenarios the category has 16. | Probe the ~3,400 harvested-but-unprobed domains (about 30–40 min) or add a web-search source for default pages. |
| Login-walled | 3 | Only 4 real sites whose landing page is just a password/sign-in wall (7 incl. 3 test endpoints/scenarios). | Probe more domains, or accept 7. |

**GATE 1 decision:** the under-construction (9) and login-walled (3) shortfalls are accepted, no extra probing. The crawl-trap shortfall (16) was filled with 16 more LOCAL SCENARIO rows (`source_type=local-scenario`): infinite pagination, day-level calendar, session ID in path, session-ID redirect, faceted navigation, endless redirect URLs, two-origin redirect loop, growing path, link explosion, growing relative link, random soft-404s, case/slash duplicates, mirrored content, endless sitemap index, infinite scroll, endless tag graph. Together with the first 4 traps, CR-C09 is tested on 20 different traps. These are synthetic: real-world trap behaviour may differ.

## 3. Where the URLs came from (nothing typed from memory)

| Source | Used for | Rows |
|---|---|---:|
| Wikidata official-website property P856 (query by class/country label; Q-id kept per row) | | 796 |
| own scenario server (127.0.0.1) | | 60 |
| designed by hand (input-handling / SSRF cases) | | 47 |
| RFC-reserved names (.invalid/.test) and IANA example domains | | 35 |
| httpbin.org public test service | | 28 |
| badssl.com public TLS test site | | 14 |
| DNS/HTTP checks run in this project | | 8 |

Wikidata candidate pools (domains harvested, before probing): corporate 904, defunct 953, institutions 1503, institutions_s 450, international 2320, international_s 1219, local_small 1850, local_small_s 600, manufacturing 586, multinational 119, retail 703, software 867.
Large pools were sampled with a fixed seed (international: up to 45 per country). Social networks, Wikipedia/Wikimedia, GitHub, Medium, Blogspot-style hosts and similar platform domains were removed from the pools. Terms of service of individual sites were NOT read; only robots.txt was respected.
Web search (WebSearch) was tried for real PDF / very-large-page examples and did not return usable URLs; those cases are covered by httpbin and the scenario server instead.

## 4. How each URL was verified

Every real URL was probed by `tools/probe.py` (independent of `app/`): DNS on the system resolver **and** 1.1.1.1/8.8.8.8 (plus NS records), then `robots.txt`, then one homepage GET **only if robots allowed our user-agent**, then the sitemap. 6,366 domains were probed. One request at a time per domain, 8 domains in parallel.

| Probe outcome | Domains |
|---|---:|
| fetched | 5374 |
| dns_fail | 403 |
| fetch_error:timeout | 317 |
| fetch_error:tls | 91 |
| robots_disallow | 81 |
| fetch_error:dns | 44 |
| fetch_error:connect | 35 |
| fetch_error:http | 20 |
| fetch_error:invalid_url | 1 |

* **Re-verification:** rows in volatile categories (dead, timeouts, TLS, HTTP errors, bot pages, robots, login, thin, parked, under construction) were probed a **second time**; a row stays only if both probes agree. 286 domains were re-probed; rows dropped because the two probes disagreed: 13 (Parked / for-sale domains: 3, Timeouts / refused / slow: 3, Bot-protected / WAF: 7).
* **Browser check:** 236 JavaScript-looking or empty-looking pages were rendered in a real Chromium (independent of the crawler). SPA rows need almost no static text but ≥500 characters after rendering; 'thin' rows must stay under 100 characters even after rendering.
* **Gold set:** 156 happy-path sites have About / Services / Products / Industries pages found from their homepage links and each confirmed with a real request (HTTP 200, HTML, ≥150 characters). Required: 100.
* **Manual text review set:** 50 rows tagged `manual-text-review` (required: 30). Encoding rows are included.
* **Hand review:** parked, under-construction, login and thin candidates were read one by one; false positives (shops that say 'for sale', real sites with a 'coming soon' banner) were excluded. The first dataset draft had error pages and one hosting placeholder among the happy-path rows; they were found by spot-checking and removed. Happy-path rows were NOT all read by a person.
* **Test endpoints:** httpbin and badssl rows were each requested once at build time (`statics_verified.json`); httpbin `/delay/N` is capped at 10 s so it is not used for timeouts; badssl `revoked`/`pinning-test` open normally on this machine and were left out.
* **Local scenarios:** all 44 routes were requested once and behaved as designed (`verify_scenarios.py`); one bug in my own latin-1 page was found and fixed.
* **Input-handling rows** are inputs only. Private, loopback and metadata addresses are **never contacted** by us; `localtest.me` and `lvh.me` were only DNS-checked (they resolve to 127.0.0.1).

* **Oracle agreement check:** a fresh independent probe of 40 random rows agreed with the expected outcome on 37/40 (92.5%) as a plain probe, and 40/40 once the 3 JavaScript-site rows were judged with a real browser (`oracle_agreement.md`).

## 5. How the expected outcome (oracle) was decided

From the requirements (CR-B01..B10, C, D, F) and standards (HTTP semantics, RFC 9309 for robots.txt, RFC 6761/2606 for reserved names) plus what the probe saw. **Never** from running the existing crawler. 19 rows are tagged `ambiguous-oracle` (e.g. how many redirects are acceptable, robots.txt 5xx policy, timeout of 20 s): a mismatch on those is judged by hand, not automatically.

| Expected outcome | Rows |
|---|---:|
| Crawled | 673 |
| Unreachable | 75 |
| Blocked | 56 |
| Invalid | 51 |
| Parked | 30 |
| Failed | 28 |
| Duplicate | 23 |
| Requires Review | 19 |
| Under Construction | 18 |
| Redirected | 15 |

`Duplicate` is an import-level outcome (second spelling of the same site); the requirement vocabulary has no word for it, so it is documented here and in `expected_status` (`import:duplicate`).

## 6. Testing from Lahore, Pakistan – read before judging results

The dataset was built and will be run from a home connection in Lahore. Some sites may show different content, a challenge page or a block from Pakistan than from Europe or the US. 215 rows are tagged `network-dependent` or `geo-risk`. Observed on this network:

* Some public IPs (1.1.1.1, 8.8.8.8, 9.9.9.9) do not accept HTTP connections; only 94.140.14.14 and 208.67.222.222 were usable as IP-literal rows.
* The local ISP resolver failed for some names that resolve fine on 1.1.1.1 (e.g. `blmlaw.com` at first probe). Dead-domain rows therefore require **both** resolvers to say the domain is gone.
* No IPv6 route: IPv6-literal rows were removed.
* 419 of 6,366 probed domains (about 7%) answered 403/429/503 with a bot-challenge page; some may be region- or rate-related. The 25 bot-protected rows were confirmed by a second probe.

## 7. Known limits of this dataset

* Wikidata skews to larger and older organisations. Very small local shops are under-represented; the 'site builders' category means *built with Wix/Squarespace/Shopify/Webflow/WordPress* and size-filtered (≤80 links, ≤12,000 chars), **not** proven to be small local businesses.
* Language is read from `<html lang>` or the script of the text, not from a language detector. Country comes from Wikidata.
* Sites change. Every row has `verified_at`; a later mismatch must be re-checked and labelled `SITE-CHANGED` before it counts against the crawler.
* Real sites that were dead or parked at build time may come back, and vice versa.
* The dataset is a field test, not a statistical sample of the 60,000 URLs. No rate computed from it should be extrapolated.

## 8. Columns

`id, url, category, subcategory, source_type, expected_outcome, expected_status, expected_pages_note, tags, smoke, country, language, tech_stack_hint, why_included, source_of_url, verified_at, verification_method, notes, oracle_rule`

`oracle_rule` is filled only for the `ambiguous-oracle` rows. The rules were frozen before any crawler run; they are applied mechanically in Phase 1 and Phase 2 and are never changed after results are seen.
