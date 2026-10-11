# Oracle agreement check (before any crawler run)

Fresh independent probe of a random sample of 40 rows (seed 20261011): 30 real happy-path, 10 real error-path. Per-row detail: `oracle_agreement.csv`.
The probe judges each site by its own rules (never by the crawler) and is compared with the row's `expected_outcome`.

| Group | Agree (plain probe) | Agree (after browser re-render of the 3 JS sites) |
|---|---:|---:|
| Happy path (30) | 27 / 30 | 30 / 30 |
| Error path (10) | 10 / 10 | 10 / 10 |
| **All (40)** | **37 / 40 = 92.5%** | **40 / 40 = 100%** |

The 3 raw disagreements are all `JavaScript-heavy SPAs` rows (T0504 habs.ai, T0508 tattebakery.com, T0544 almarai.com). The plain HTTP probe sees almost no text,
which is exactly why they are in that category. A real browser render showed 2,731 / 1,174 / 2,027 characters of content, so the expected outcome `Crawled` (via browser) holds.
Both numbers are reported on purpose: 92.5% is the figure for a probe without a browser; 100% is the figure once JS sites are judged the way the oracle defines them.
Limit: 40 rows is a small sample. It does not prove the other 948 rows are right; it shows no sign of a systematic oracle error in the sampled rows.
