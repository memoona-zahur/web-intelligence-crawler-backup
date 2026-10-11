# Run summary – existing-code_full_20261011

Code under test: `existing-code` (git `24818a60`, tag `crawler-baseline-v1`). App code unchanged during the run: **True**. Dataset `testing_URLs.csv` sha256 `0963ab3fead262c8…`. Concurrency used: **5** (the crawler's own default is 10; Phase 2 must use the same value as the final Phase 1 run).



## Verdicts

| Verdict | Rows |
|---|---:|
| MATCH | 752 |
| PARTIAL | 3 |
| MISMATCH | 163 |
| ENV-DEPENDENT | 28 |
| SITE-CHANGED | 41 |
| ORACLE-LIMITATION | 1 |
| HARNESS-ERROR | 0 |
| NOT-RUN | 0 |
| **Total** | 988 |

`ENV-DEPENDENT` = result caused by this network (Pakistan ISP resolver, geo-blocking), not counted as a crawler bug. `SITE-CHANGED` = the site no longer behaves as it did when the dataset was built.

## By category

| Category | Rows | MATCH | PARTIAL | MISMATCH | ENV | SITE-CHG | Other |
|---|---:|---:|---:|---:|---:|---:|---:|
| Bot-protected / WAF | 25 | 24 | 0 | 0 | 0 | 1 | 0 |
| Corporate / B2B services | 70 | 66 | 0 | 3 | 1 | 0 | 0 |
| Crawl traps | 20 | 19 | 0 | 1 | 0 | 0 | 0 |
| Dead domains (NXDOMAIN) | 30 | 1 | 0 | 26 | 0 | 3 | 0 |
| E-commerce and retail | 60 | 56 | 0 | 2 | 1 | 1 | 0 |
| Encoding oddities | 15 | 12 | 0 | 2 | 1 | 0 | 0 |
| HTTP errors | 30 | 21 | 0 | 2 | 0 | 7 | 0 |
| Healthcare, education, finance, real estate, non-profit, government | 80 | 67 | 0 | 2 | 7 | 4 | 0 |
| Input handling | 80 | 59 | 0 | 18 | 1 | 1 | 1 |
| JavaScript-heavy SPAs | 50 | 38 | 0 | 11 | 1 | 0 | 0 |
| Large multinational enterprises | 30 | 28 | 0 | 1 | 1 | 0 | 0 |
| Login-walled | 7 | 2 | 0 | 5 | 0 | 0 | 0 |
| Manufacturers, industrial, distributors, wholesalers | 60 | 47 | 0 | 6 | 2 | 5 | 0 |
| Minimal / one-page / static sites | 30 | 28 | 0 | 1 | 0 | 1 | 0 |
| Non-English / international | 80 | 68 | 0 | 2 | 8 | 2 | 0 |
| Non-HTML and heavy content | 15 | 13 | 0 | 2 | 0 | 0 | 0 |
| Parked / for-sale domains | 30 | 0 | 0 | 29 | 1 | 0 | 0 |
| Redirect behaviour | 40 | 18 | 3 | 15 | 1 | 3 | 0 |
| SSL/TLS problems | 20 | 17 | 0 | 0 | 0 | 3 | 0 |
| SaaS / software / platforms | 60 | 55 | 0 | 1 | 3 | 1 | 0 |
| Sitemap variants and non-standard navigation | 20 | 20 | 0 | 0 | 0 | 0 | 0 |
| Small local businesses on site builders | 60 | 57 | 0 | 2 | 0 | 1 | 0 |
| Thin / empty / error-only pages | 15 | 2 | 0 | 10 | 0 | 3 | 0 |
| Timeouts / refused / slow | 25 | 16 | 0 | 7 | 0 | 2 | 0 |
| Under construction / default pages | 16 | 5 | 0 | 8 | 0 | 3 | 0 |
| robots.txt | 20 | 13 | 0 | 7 | 0 | 0 | 0 |

## Numbers from this run only

* Crawler statuses: {'crawled': 664, 'blocked': 60, 'unreachable': 51, 'empty': 44, 'invalid': 66, 'failed': 37, 'robots_blocked': 7}
* Happy-path rows: 600; crawled: 530; with ≥500 characters of text: 498
* Per-site time p50 7.44 s, p95 55.96 s; HTTP requests 7058; retries 307; browser used on 115 rows
* Wall time of crawl 2997.4 s; throughput 1115.8 sites/hour (this run, concurrency 5, mixed fast/slow test rows — not a forecast); peak memory of the Python process 296.5 MB (Chromium not included)

## Rows that did not match (first 60)

| Id | Category | URL | Expected | Actual | Verdict | Reason |
|---|---|---|---|---|---|---|
| T0004 | Corporate / B2B services | https://fabioluizvieira.com.br/vz-associados-consu | Crawled | Blocked | MISMATCH | expected Crawled, crawler said Blocked: HTTP 403 from https://fabioluizvieira.com.br |
| T0021 | Corporate / B2B services | http://www.belex.com | Crawled | Unreachable | ENV-DEPENDENT | expected Crawled, crawler said Unreachable: timeout fetching http://belex.com |
| T0047 | Corporate / B2B services | https://prlab.co | Crawled | Blocked | MISMATCH | expected Crawled, crawler said Blocked: HTTP 403 from https://prlab.co |
| T0054 | Corporate / B2B services | https://mongrove.com/ | Crawled | Blocked | MISMATCH | expected Crawled, crawler said Blocked: HTTP 403 from https://mongrove.com |
| T0079 | Manufacturers, industrial, d | http://www.agrinar.com.ar/ | Crawled | Under Construction | MISMATCH | expected Crawled, crawler said Under Construction: no usable text found |
| T0081 | Manufacturers, industrial, d | https://gem.polaris.com/en-us/ | Crawled | Blocked | MISMATCH | expected Crawled, crawler said Blocked: HTTP 403 from https://www.gemcar.com |
| T0082 | Manufacturers, industrial, d | https://matthewsaurora.com/ | Crawled | Blocked | MISMATCH | expected Crawled, crawler said Blocked: HTTP 403 from https://matthewsaurora.com |
| T0085 | Manufacturers, industrial, d | https://www.dino-cars.de/ | Crawled | Invalid | ENV-DEPENDENT | expected Crawled, crawler said Invalid: cannot resolve host 'www.dino-cars.de' |
| T0089 | Manufacturers, industrial, d | https://www.nutro.com/ | Crawled | Blocked | SITE-CHANGED | expected Crawled, crawler said Blocked: HTTP 403 from https://nutro.com |
| T0090 | Manufacturers, industrial, d | http://www.marlinsportscars.co.uk | Crawled | Invalid | SITE-CHANGED | expected Crawled, crawler said Invalid: cannot resolve host 'marlinsportscars.co.uk' |
| T0091 | Manufacturers, industrial, d | https://www.pedigree.com/ | Crawled | Blocked | SITE-CHANGED | expected Crawled, crawler said Blocked: HTTP 403 from https://pedigree.com |
| T0093 | Manufacturers, industrial, d | http://busplant.bogdan.ua | Crawled | Under Construction | MISMATCH | expected Crawled, crawler said Under Construction: no usable text found |
| T0101 | Manufacturers, industrial, d | https://easteggbottle.com/ | Crawled | Blocked | MISMATCH | expected Crawled, crawler said Blocked: HTTP 403 from https://easteggbottle.com |
| T0113 | Manufacturers, industrial, d | http://www.cryorig.com/ | Crawled | Invalid | ENV-DEPENDENT | expected Crawled, crawler said Invalid: cannot resolve host 'cryorig.com' |
| T0116 | Manufacturers, industrial, d | https://www.briomoulds.com/ | Crawled | Under Construction | MISMATCH | expected Crawled, crawler said Under Construction: no usable text found |
| T0118 | Manufacturers, industrial, d | https://www.electric-center.co.uk/ | Crawled | Blocked | SITE-CHANGED | expected Crawled, crawler said Blocked: HTTP 403 from https://electric-center.co.uk |
| T0124 | Manufacturers, industrial, d | http://www.pagani.com/ | Crawled | Blocked | SITE-CHANGED | expected Crawled, crawler said Blocked: HTTP 429 from https://pagani.com |
| T0133 | E-commerce and retail | https://www.thekirbyonmain.com | Crawled | Blocked | SITE-CHANGED | expected Crawled, crawler said Blocked: HTTP 403 from https://www.thekirbyonmain.com/ |
| T0147 | E-commerce and retail | https://www.maruiimai.mistore.jp/hakodate.html | Crawled | Unreachable | ENV-DEPENDENT | expected Crawled, crawler said Unreachable: timeout fetching http://maruiimai.mistore.jp |
| T0164 | E-commerce and retail | https://carvanbits.co.uk/ | Crawled | Blocked | MISMATCH | expected Crawled, crawler said Blocked: HTTP 403 from https://carvanbits.co.uk |
| T0181 | E-commerce and retail | https://www.bim.com.tr | Crawled | Under Construction | MISMATCH | expected Crawled, crawler said Under Construction: no usable text found |
| T0204 | SaaS / software / platforms | https://calavion.com | Crawled | Invalid | ENV-DEPENDENT | expected Crawled, crawler said Invalid: cannot resolve host 'calavion.com' |
| T0205 | SaaS / software / platforms | http://www.bromcom.com/ | Crawled | Blocked | MISMATCH | expected Crawled, crawler said Blocked: HTTP 403 from https://bromcom.com |
| T0212 | SaaS / software / platforms | https://www.gluster.org/ | Crawled | Invalid | ENV-DEPENDENT | expected Crawled, crawler said Invalid: cannot resolve host 'gluster.org' |
| T0218 | SaaS / software / platforms | http://www.rock-chips.com/ | Crawled | Invalid | SITE-CHANGED | expected Crawled, crawler said Invalid: cannot resolve host 'rock-chips.com' |
| T0245 | SaaS / software / platforms | http://www.explus.com.tw | Crawled | Unreachable | ENV-DEPENDENT | expected Crawled, crawler said Unreachable: timeout fetching http://explus.com.tw |
| T0252 | Healthcare, education, finan | https://freedomclinicutah.com/ | Crawled | Blocked | MISMATCH | expected Crawled, crawler said Blocked: HTTP 403 from https://freedomclinicutah.com |
| T0256 | Healthcare, education, finan | http://www.uk-erlangen.de/en/ | Crawled | Invalid | SITE-CHANGED | expected Crawled, crawler said Invalid: cannot resolve host 'uk-erlangen.de' |
| T0263 | Healthcare, education, finan | https://www.liusmed.com/ | Crawled | Under Construction | MISMATCH | expected Crawled, crawler said Under Construction: no usable text found |
| T0266 | Healthcare, education, finan | https://www.city.minamisoma.lg.jp/portal/health/ho | Crawled | Invalid | SITE-CHANGED | expected Crawled, crawler said Invalid: cannot resolve host 'city.minamisoma.lg.jp' |
| T0268 | Healthcare, education, finan | http://www.bit.edu.cn/ | Crawled | Unreachable | ENV-DEPENDENT | expected Crawled, crawler said Unreachable: timeout fetching https://bit.edu.cn/ |
| T0288 | Healthcare, education, finan | http://www.qbe.com/ | Crawled | Blocked | SITE-CHANGED | expected Crawled, crawler said Blocked: HTTP 403 from https://www.qbe.com/ |
| T0293 | Healthcare, education, finan | https://www.gob.mx/banobras | Crawled | Unreachable | ENV-DEPENDENT | expected Crawled, crawler said Unreachable: timeout fetching http://gob.mx |
| T0303 | Healthcare, education, finan | http://www.umoncton.ca/ | Crawled | Unreachable | ENV-DEPENDENT | expected Crawled, crawler said Unreachable: timeout fetching http://umoncton.ca |
| T0304 | Healthcare, education, finan | https://www.sevenoaksschool.org/ | Crawled | Failed | ENV-DEPENDENT | expected Crawled, crawler said Failed: page larger than 2000000 bytes |
| T0308 | Healthcare, education, finan | https://www.wti.org.in | Crawled | Invalid | ENV-DEPENDENT | expected Crawled, crawler said Invalid: cannot resolve host 'www.wti.org.in' |
| T0315 | Healthcare, education, finan | https://www.ign.gob.ar/ | Crawled | Unreachable | ENV-DEPENDENT | expected Crawled, crawler said Unreachable: connection error fetching https://ign.gob.ar/: [SSL: CERTIFICATE_VERIFY_FAILED] certificate veri |
| T0316 | Healthcare, education, finan | http://www.81.cn/jw_208551/index.html | Crawled | Invalid | SITE-CHANGED | expected Crawled, crawler said Invalid: cannot resolve host '81.cn' |
| T0325 | Healthcare, education, finan | https://www.bpa.ad/ | Crawled | Invalid | ENV-DEPENDENT | expected Crawled, crawler said Invalid: cannot resolve host 'www.areb.ad' |
| T0358 | Small local businesses on si | http://www.montelena.com/ | Crawled | Blocked | MISMATCH | expected Crawled, crawler said Blocked: HTTP 403 from https://montelena.com |
| T0364 | Small local businesses on si | http://www.koperenknop.nl | Crawled | Blocked | MISMATCH | expected Crawled, crawler said Blocked: HTTP 403 from https://koperenknop.nl |
| T0369 | Small local businesses on si | https://www.kantiv.com/ | Crawled | Invalid | SITE-CHANGED | expected Crawled, crawler said Invalid: cannot resolve host 'kantiv.com' |
| T0402 | Large multinational enterpri | http://www.tetralaval.com | Crawled | Invalid | ENV-DEPENDENT | expected Crawled, crawler said Invalid: cannot resolve host 'tetralaval.com' |
| T0420 | Large multinational enterpri | https://www.hamiltoncompany.com | Crawled | Failed | MISMATCH | expected Crawled, crawler said Failed: page larger than 2000000 bytes |
| T0436 | Non-English / international | https://www.dirk.org/ | Crawled | Invalid | ENV-DEPENDENT | expected Crawled, crawler said Invalid: cannot resolve host 'dirk.org' |
| T0437 | Non-English / international | https://skad.ru/ | Crawled | Under Construction | SITE-CHANGED | expected Crawled, crawler said Under Construction: no usable text found |
| T0440 | Non-English / international | http://www.pei.co.il | Crawled | Unreachable | ENV-DEPENDENT | expected Crawled, crawler said Unreachable: timeout fetching http://pei.co.il |
| T0441 | Non-English / international | https://www.kimberly-clark.co.il | Crawled | Blocked | ENV-DEPENDENT | expected Crawled, crawler said Blocked: HTTP 403 from https://kimberly-clark.co.il |
| T0450 | Non-English / international | http://mellishoeco.com/ | Crawled | Unreachable | MISMATCH | expected Crawled, crawler said Unreachable: timeout fetching https://injectslotgacor.com/ |
| T0451 | Non-English / international | https://www.groupebcp.com/ar | Crawled | Under Construction | MISMATCH | expected Crawled, crawler said Under Construction: no usable text found |
| T0454 | Non-English / international | https://www.hanwa.co.jp/ | Crawled | Invalid | ENV-DEPENDENT | expected Crawled, crawler said Invalid: cannot resolve host 'hanwa.co.jp' |
| T0456 | Non-English / international | http://www.tbipet.com.tw/ | Crawled | Invalid | ENV-DEPENDENT | expected Crawled, crawler said Invalid: cannot resolve host 'tbipet.com.tw' |
| T0465 | Non-English / international | http://www.lgdisplay.com/ | Crawled | Invalid | ENV-DEPENDENT | expected Crawled, crawler said Invalid: cannot resolve host 'www.lgdisplay.com' |
| T0468 | Non-English / international | http://www.dm.co.kr/ | Crawled | Failed | SITE-CHANGED | expected Crawled, crawler said Failed: HTTP 404 from http://dm.co.kr |
| T0494 | Non-English / international | http://www.serpost.com.pe/ | Crawled | Invalid | ENV-DEPENDENT | expected Crawled, crawler said Invalid: cannot resolve host 'serpost.com.pe' |
| T0495 | Non-English / international | http://www.koandina.com/ | Crawled | Unreachable | ENV-DEPENDENT | expected Crawled, crawler said Unreachable: timeout fetching http://koandina.com |
| T0507 | JavaScript-heavy SPAs | http://smule.com | Crawled | Blocked | MISMATCH | expected Crawled, crawler said Blocked: HTTP 403 from https://www.smule.com/ |
| T0518 | JavaScript-heavy SPAs | https://kettleconsulting.co.za | Crawled | Invalid | ENV-DEPENDENT | expected Crawled, crawler said Invalid: cannot resolve host 'kettleconsulting.co.za' |
| T0521 | JavaScript-heavy SPAs | https://www.clap-walk.com/ | Crawled | Under Construction | MISMATCH | expected Crawled, crawler said Under Construction: no usable text found |
| T0522 | JavaScript-heavy SPAs | https://www.kg-mobility.com/ | Crawled | Invalid | MISMATCH | expected Crawled, crawler said Invalid: cannot resolve host 'kg-mobility.com' |
