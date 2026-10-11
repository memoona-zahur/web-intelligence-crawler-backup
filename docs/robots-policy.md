# robots.txt policy of the crawler (CR-F01)

Status: **default decided by the project owner on 2026-10-11, pending sir confirmation** (see `docs/open-questions-for-sir.md`, question 2).

The crawler follows RFC 9309 ("Robots Exclusion Protocol") with the parser `protego`.

| What robots.txt does | What the crawler does |
|---|---|
| Answers **200** | Parses it. `Allow`/`Disallow` use the longest matching rule (Allow wins a tie); `*` and `$` work; our own group (`WebsiteIntelligenceBot`) wins over `User-agent: *`; `Crawl-delay` is honoured up to 60 s (a larger value means: homepage only, crawl marked Partial); `Sitemap:` lines are used. |
| Answers **404, 410, 401, 403 or another 4xx** (not 429) | No rules apply: the whole site may be crawled (RFC 9309 §2.3.1.3). |
| Is **not usable** (HTML page, too large) | Treated as "no rules". |
| Answers **5xx or 429**, or the request fails after **3 attempts** (1 s, 2 s back-off, Retry-After honoured) | **Do not crawl now** (RFC 9309 §2.3.1.4). Status `robots_blocked` ("Blocked") with the reason *robots.txt unavailable (HTTP 503)*; the queue retries the site later (15 min, 30 min, 1 h; 3 attempts). |
| Cannot be fetched because the whole site is unreachable (connection refused, TLS failure, timeout) | Nothing is crawled; status **Unreachable**; retried later. (The site itself is down, so "Blocked" would be the wrong word.) |
| Disallows the homepage | Status `robots_blocked` with the reason *disallowed by robots.txt*; no page of the site is requested; not retried. |
| Disallows a page the crawler would like to read | That page is skipped and recorded (`pages.crawl_status = skipped`, reason in `pages.error`). |

Setting: `ROBOTS_5XX_POLICY=disallow` (default) or `allow` (treat an unreadable robots.txt like a missing one — the Phase 1 behaviour).
robots.txt is fetched with the same User-Agent, per-domain spacing, size limit and SSRF guard as every other request. It is cached per site for the length of a run.
Never done: bypassing a disallow, rotating the User-Agent or IP address, or retrying a "Disallow" answer.
