"""Check testing_URLs.csv against docs/phase-plan.md section 1.3. Exit code 1 if a hard rule fails."""
import csv
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_dataset as B  # noqa: E402

path = Path(__file__).resolve().parents[1] / "dataset" / "testing_URLs.csv"
rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
fails, warns = [], []
if list(rows[0].keys()) != B.COLUMNS:
    fails.append(f"columns differ: {list(rows[0].keys())}")
for r in rows:
    for c in ("verified_at", "verification_method", "source_of_url", "expected_outcome", "category", "source_type"):
        if not r[c].strip():
            fails.append(f"{r['id']} empty {c}")
    if r["source_type"] not in ("real", "public-test-endpoint", "local-scenario"):
        fails.append(f"{r['id']} bad source_type {r['source_type']}")
    if r["category"] in B.HAPPY and r["source_type"] != "real":
        fails.append(f"{r['id']} happy-path row is not a real site")
for r in rows:
    amb = "ambiguous-oracle" in r["tags"].split(";")
    if amb and not r["oracle_rule"].strip():
        fails.append(f"{r['id']} ambiguous row without oracle_rule")
    if not amb and r["oracle_rule"].strip():
        fails.append(f"{r['id']} oracle_rule on a non-ambiguous row")
ids = [r["id"] for r in rows]
if len(set(ids)) != len(ids):
    fails.append("duplicate ids")
urls = Counter(r["url"] for r in rows)
dups = [u for u, n in urls.items() if n > 1]
if dups:
    fails.append(f"duplicate url strings: {dups[:5]}")
cats = Counter(r["category"] for r in rows)
for c, q in B.QUOTA.items():
    if cats[c] > q:
        fails.append(f"over quota {c}: {cats[c]}>{q}")
    if cats[c] < q:
        warns.append(f"short {c}: {cats[c]}/{q}")
unknown = set(cats) - set(B.QUOTA)
if unknown:
    fails.append(f"unknown categories {unknown}")
smoke = [r for r in rows if r["smoke"] == "Y"]
if len(smoke) != 100:
    fails.append(f"smoke rows {len(smoke)} != 100")
missing = [c for c in B.QUOTA if cats[c] and not any(r["category"] == c for r in smoke)]
if missing:
    fails.append(f"categories missing from smoke: {missing}")
gold = [r for r in rows if "gold" in r["tags"].split(";") and r["source_type"] == "real"]
if len(gold) < 100:
    fails.append(f"gold rows {len(gold)} < 100")
review = [r for r in rows if "manual-text-review" in r["tags"]]
if len(review) < 30:
    fails.append(f"manual-text-review rows {len(review)} < 30")
BAD = ("porn", "xxx", "casino", "betting", "escort", "nude", "adult", "gambling", "poker")
bad = [r["id"] + " " + r["url"][:80] for r in rows if r["source_type"] == "real" and any(b in (r["url"] + r["notes"] + r["why_included"]).lower() for b in BAD)]
if bad:
    fails.append(f"possible adult/gambling content: {bad[:5]}")
SOCIAL = ("facebook.", "linkedin.", "twitter.", "instagram.", "youtube.", "tiktok.")
soc = [r["url"] for r in rows if r["source_type"] == "real" and any(s in r["url"].lower() for s in SOCIAL)]
if soc:
    fails.append(f"social network rows: {soc[:5]}")
hap = sum(1 for r in rows if r["category"] in B.HAPPY)
print(f"rows {len(rows)} (happy {hap}, error/edge {len(rows) - hap}); smoke {len(smoke)}; gold {len(gold)}; manual-text-review {len(review)}")
print("source types:", dict(Counter(r["source_type"] for r in rows)))
print("expected outcomes:", dict(Counter(r["expected_outcome"] for r in rows)))
print("tags geo/network:", sum(1 for r in rows if "network-dependent" in r["tags"] or "geo-risk" in r["tags"]), "| ambiguous-oracle:", sum(1 for r in rows if "ambiguous-oracle" in r["tags"]))
print("countries (real):", dict(Counter(r["country"] for r in rows if r["country"]).most_common(12)))
print("languages (happy):", dict(Counter(r["language"] for r in rows if r["category"] in B.HAPPY).most_common(12)))
for w in warns:
    print("WARN", w)
for f in fails:
    print("FAIL", f)
print("RESULT:", "FAIL" if fails else "OK (hard rules)")
sys.exit(1 if fails else 0)
