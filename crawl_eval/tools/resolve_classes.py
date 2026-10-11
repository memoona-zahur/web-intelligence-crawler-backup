"""Look up Wikidata class IDs by label (so Q-numbers are never taken from memory).

    python resolve_classes.py "law firm" "accounting firm" ...
Prints the top matches with Wikidata's own description. A human/agent picks the right one.
"""
import sys
import time

import httpx

UA = {"User-Agent": "WebsiteIntelligenceEval/1.0 (academic crawler field test; Lahore)"}


def search(label: str) -> list[dict]:
    for attempt in range(6):
        r = httpx.get(
            "https://www.wikidata.org/w/api.php",
            params={"action": "wbsearchentities", "search": label, "language": "en", "type": "item", "limit": 4, "format": "json"},
            headers=UA, timeout=30,
        )
        if r.status_code == 200 and r.content[:1] == b"{":
            return r.json().get("search", [])
        wait = int(r.headers.get("retry-after", 0) or 0) or 5 * (attempt + 1)
        print(f"   (HTTP {r.status_code}, waiting {wait}s)", file=sys.stderr)
        time.sleep(wait)
    return []


if __name__ == "__main__":
    for label in sys.argv[1:]:
        print(f"## {label}")
        for item in search(label):
            print(f"   {item['id']:<10} {item.get('label','')} | {item.get('description','')[:90]}")
        time.sleep(2)
