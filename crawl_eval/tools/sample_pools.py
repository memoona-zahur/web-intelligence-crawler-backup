"""Draw fixed-seed samples from big harvested pools so we probe only what we need (seed 20261010)."""
import csv
import random
from collections import defaultdict
from pathlib import Path

CAND = Path(__file__).resolve().parents[1] / "dataset" / "candidates"
SEED = 20261010
random.seed(SEED)
BLOCK = ("facebook.", "linkedin.", "twitter.", "x.com", "instagram.", "youtube.", "tiktok.", "pinterest.", "reddit.",
         "wikipedia.", "wikimedia.", "github.com", "t.me", "vk.com", "weibo.", "blogspot.", "wordpress.com/", "medium.com")


def read(name):
    with (CAND / f"pool_{name}.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if not any(b in r["url"].lower() for b in BLOCK)]


def write(name, rows):
    with (CAND / f"pool_{name}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["qid", "label", "url", "country", "class", "source_of_url", "harvested_at"])
        w.writeheader()
        w.writerows(rows)
    print(name, len(rows))


write("institutions_s", random.sample(read("institutions"), min(450, len(read("institutions")))))
write("local_small_s", random.sample(read("local_small"), min(600, len(read("local_small")))))
by_country = defaultdict(list)
for r in read("international"):
    by_country[r["country"] or "?"].append(r)
intl = []
for c, rows in sorted(by_country.items()):
    intl += random.sample(rows, min(45, len(rows)))
write("international_s", intl)
print({c: len(v) for c, v in sorted(by_country.items())})
