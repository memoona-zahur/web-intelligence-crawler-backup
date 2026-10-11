"""Harvest candidate website URLs from Wikidata (official website, property P856).

Nothing is typed from memory: classes and countries are matched by English label inside the
SPARQL query, and every candidate keeps the Wikidata item id it came from (source_of_url).
Results are cached per query in C:/crawl_eval_data/scratch/harvest_cache so a run can resume.

    python harvest.py            # run every query below
    python harvest.py pool_name  # only one pool
Output: crawl_eval/dataset/candidates/pool_<name>.csv
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

HERE = Path(__file__).resolve().parents[1]
CAND = HERE / "dataset" / "candidates"
CACHE = Path("C:/crawl_eval_data/scratch/harvest_cache")
CACHE.mkdir(parents=True, exist_ok=True)
CAND.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "WebsiteIntelligenceEval/1.0 (academic crawler field test; Lahore)",
      "Accept": "application/sparql-results+json"}
ENDPOINT = "https://query.wikidata.org/sparql"

COMPANY_CLASSES = ["business", "company", "enterprise"]
COUNTRIES_NON_EN = [
    "Germany", "France", "Spain", "Italy", "Saudi Arabia", "United Arab Emirates", "Egypt", "Japan",
    "People's Republic of China", "South Korea", "Pakistan", "India", "Bangladesh", "Brazil", "Mexico",
    "Argentina", "Colombia", "Turkey", "Poland", "Russia", "Iran", "Morocco", "Chile", "Peru",
    "Taiwan", "Thailand", "Indonesia", "Greece", "Czech Republic", "Israel",
]

# pool -> list of (class labels, countries or None, limit)
POOLS: dict[str, list[tuple[list[str], list[str] | None, int]]] = {
    "corporate": [(["law firm", "accountancy firm", "management consulting company", "advertising agency",
                    "public relations agency", "engineering company", "consulting company"], None, 250)],
    "manufacturing": [(["manufacturer", "manufacturing company", "chemical company", "wholesaler",
                        "distribution company", "steel producer", "automobile manufacturer"], None, 250)],
    "retail": [(["online shop", "retail company", "retailer", "supermarket chain", "department store",
                 "e-commerce company"], None, 250)],
    "software": [(["software company", "technology company", "internet company", "cloud computing company",
                   "startup company"], None, 400)],
    "institutions": [(["hospital", "clinic", "university", "school", "bank", "real estate company",
                       "non-governmental organization", "non-profit organization", "government agency",
                       "insurance company", "charitable organization", "public library", "museum"], None, 150)],
    "multinational": [(["multinational corporation"], None, 300)],
    "local_small": [(["restaurant", "hotel", "winery", "brewery", "bakery", "cafe", "bed and breakfast",
                      "hair salon", "bookstore", "art gallery", "guest house", "campsite", "farm"], None, 200)],
    "international": [(COMPANY_CLASSES, COUNTRIES_NON_EN, 120)],
}


def _label_union(var: str, labels: list[str]) -> str:
    values = " ".join(f'"{x}"@en' for x in labels)
    return f"VALUES ?{var}Label {{ {values} }} ?{var} rdfs:label ?{var}Label ."


def build_query(classes: list[str], country: str | None, limit: int) -> str:
    country_part = ""
    if country:
        country_part = f"?item wdt:P17 ?country . ?country rdfs:label \"{country}\"@en ."
    return f"""
SELECT ?item ?itemLabel ?url ?countryLabel ?classLabel WHERE {{
  {_label_union('class', classes)}
  ?item wdt:P31 ?class .
  ?item wdt:P856 ?url .
  {country_part}
  OPTIONAL {{ ?item wdt:P17 ?c . }}
  BIND(COALESCE(?c, ?country) AS ?countryX)
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". ?item rdfs:label ?itemLabel . ?countryX rdfs:label ?countryLabel . }}
}} LIMIT {limit}
"""


DEFUNCT_QUERY = """
SELECT ?item ?itemLabel ?url ?countryLabel ?d WHERE {{
  ?item wdt:P576 ?d . ?item wdt:P856 ?url .
  FILTER(?d > "{lo}-01-01T00:00:00Z"^^xsd:dateTime && ?d < "{hi}-01-01T00:00:00Z"^^xsd:dateTime)
  ?item wdt:P31 ?class . ?class rdfs:label ?cl . FILTER(?cl IN ("business"@en, "company"@en, "enterprise"@en, "brand"@en, "startup company"@en, "software company"@en, "retailer"@en, "manufacturer"@en))
  OPTIONAL {{ ?item wdt:P17 ?c . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". ?c rdfs:label ?countryLabel . ?item rdfs:label ?itemLabel . }}
}} LIMIT {limit}
"""


def run_query(query: str, tag: str) -> list[dict]:
    key = hashlib.sha1(query.encode()).hexdigest()[:16]
    cache_file = CACHE / f"{key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    for attempt in range(6):
        try:
            r = httpx.post(ENDPOINT, data={"query": query}, headers=UA, timeout=90)
        except httpx.HTTPError as exc:
            print(f"  {tag}: network error {type(exc).__name__}, retry", flush=True)
            time.sleep(10 * (attempt + 1))
            continue
        if r.status_code == 200:
            rows = r.json()["results"]["bindings"]
            cache_file.write_text(json.dumps(rows), encoding="utf-8")
            time.sleep(3)
            return rows
        wait = int(r.headers.get("retry-after", 0) or 0) or 15 * (attempt + 1)
        print(f"  {tag}: HTTP {r.status_code}, wait {wait}s", flush=True)
        time.sleep(wait)
    print(f"  {tag}: GAVE UP", flush=True)
    return []


def val(b: dict, k: str) -> str:
    return b.get(k, {}).get("value", "")


def write_pool(name: str, rows: list[dict], desc: dict[int, str] | None = None) -> None:
    seen, out = set(), []
    for b in rows:
        url = val(b, "url").strip()
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        if not host or host in seen or not url.startswith(("http://", "https://")):
            continue
        seen.add(host)
        qid = val(b, "item").rsplit("/", 1)[-1]
        out.append({
            "qid": qid, "label": val(b, "itemLabel"), "url": url, "country": val(b, "countryLabel"),
            "class": val(b, "classLabel"), "source_of_url": f"Wikidata {qid} property P856 (pool {name})",
            "harvested_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        })
    with (CAND / f"pool_{name}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["qid", "label", "url", "country", "class", "source_of_url", "harvested_at"])
        w.writeheader()
        w.writerows(out)
    print(f"pool {name}: {len(out)} unique domains", flush=True)


def main() -> None:
    wanted = sys.argv[1:] or [*POOLS, "defunct"]
    for name in wanted:
        rows: list[dict] = []
        if name == "defunct":
            for lo, hi in [(2005, 2010), (2010, 2014), (2014, 2017), (2017, 2020), (2020, 2023)]:
                q = DEFUNCT_QUERY.format(lo=lo, hi=hi, limit=250)
                rows += run_query(q, f"defunct {lo}-{hi}")
        else:
            for classes, countries, limit in POOLS[name]:
                if countries:
                    for c in countries:
                        rows += run_query(build_query(classes, c, limit), f"{name}/{c}")
                else:
                    # one class at a time keeps each query small and the mix balanced
                    for cl in classes:
                        rows += run_query(build_query([cl], None, limit), f"{name}/{cl}")
        write_pool(name, rows)


if __name__ == "__main__":
    main()
