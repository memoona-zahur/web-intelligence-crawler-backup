"""Phase 1 close-out, condition 1: list every SITE-CHANGED and ENV-DEPENDENT row with reason and evidence, re-probe 10 random SITE-CHANGED rows, reclassify those whose label does not hold.
    C:\\crawl_eval_data\\venv\\Scripts\\python.exe -B crawl_eval\\relabel_check.py <results dir>
Rule (written before looking at the fresh results):
  SITE-CHANGED HOLDS      if the fresh probe still reads the site in a way that is INCOMPATIBLE with the dataset expectation (judge.COMPAT), or the name resolves nowhere (all resolvers, 3 tries).
  DOES NOT HOLD           if the fresh probe now reads the site as COMPATIBLE with the dataset expectation (the site is as the dataset said), or the name resolves but the site is merely unreachable
                          from this network (that is the ENV-DEPENDENT definition).
  New label when it does not hold: ENV-DEPENDENT if the crawler's own result was a network/DNS failure (unreachable / invalid-by-DNS), otherwise MISMATCH (a crawler result).
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True
import asyncio
import csv
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import judge  # noqa: E402
import run_eval as R  # noqa: E402

out = Path(sys.argv[1])
final_rows = {r["id"]: r for r in csv.DictReader((out / "results.csv").open(encoding="utf-8-sig"))}


def _probe_agrees_as_of_close_out_start(expected, cls, category="", subcategory=""):
    """The probe comparison exactly as it was when the 41 SITE-CHANGED / 28 ENV-DEPENDENT labels were first produced (before the JavaScript-redirect refinement)."""
    if cls == "unknown" or expected not in judge.COMPAT:
        return None
    if category == "JavaScript-heavy SPAs":
        return None
    return cls in judge.COMPAT[expected]


_saved = judge.probe_agrees
judge.probe_agrees = _probe_agrees_as_of_close_out_start
rows, _m = R.build_reports(out, quiet=True, apply_reclass=False)  # ORIGINAL labels, reconstructed
judge.probe_agrees = _saved
assert sum(r["verdict"] == "SITE-CHANGED" for r in rows) == 41 and sum(r["verdict"] == "ENV-DEPENDENT" for r in rows) == 28, "original labels not reproduced"
ds ={r["id"]: r for r in csv.DictReader((HERE / "dataset" / "testing_URLs.csv").open(encoding="utf-8-sig"))}
probes = {}
for n in ("probes_after_reused.json", "probes_after.json"):
    if (out / n).exists():
        probes.update(json.loads((out / n).read_text(encoding="utf-8")))
recs = {}
for line in (out / "per_site.jsonl").read_text(encoding="utf-8").split("\n"):
    if line.strip():
        x = json.loads(line)
        recs[x["row_id"]] = x
sel = [r for r in rows if r["verdict"] in ("SITE-CHANGED", "ENV-DEPENDENT")]
sc_ids = sorted(r["id"] for r in rows if r["verdict"] == "SITE-CHANGED")
sample = sorted(random.Random(20261012).sample(sc_ids, 10))
# rows that became SITE-CHANGED only because of the JavaScript-redirect refinement of probe_agrees (not in the original 41): checked with the same rule
refined_rows, _m2 = R.build_reports(out, quiet=True, apply_reclass=False)  # refined judge, before any reclassification (stable basis)
extra_ids = sorted(r2["id"] for r2 in refined_rows if r2["verdict"] == "SITE-CHANGED" and next(o for o in rows if o["id"] == r2["id"])["verdict"] != "SITE-CHANGED")
sample = sorted(set(sample) | set(extra_ids))
orig_sample = sorted(random.Random(20261012).sample(sc_ids, 10))


async def fresh(rid):
    x = recs[rid]
    host = x["site_url"].split("://", 1)[1].split("/", 1)[0].split(":")[0]
    import httpx
    async with httpx.AsyncClient() as client:
        dns = await R.dns_robust(host)
        p = await R.runtime_probe(host, x["site_url"], True, client)
        p.update(dns)
    return p


async def main():
    res = {}
    for rid in sample:
        res[rid] = await fresh(rid)
        await asyncio.sleep(1.0)
    return res


stored = out / "fresh_probe_review.json"
fresh_res = json.loads(stored.read_text(encoding="utf-8"))["fresh_probes"] if stored.exists() else {}  # reuse: the evidence must not change from run to run
missing = [rid for rid in sample if rid not in fresh_res]
print("reusing stored fresh probes for", [rid for rid in sample if rid in fresh_res], "| probing now:", missing)
if missing:
    _all = sample
    sample = missing
    fresh_res.update(asyncio.run(main()))
    sample = _all
review = []
reclass = {}
for r in rows:
    if r["verdict"] not in ("SITE-CHANGED", "ENV-DEPENDENT") and r["id"] not in extra_ids:
        continue
    rid = r["id"]
    p = probes.get(rid, {})
    entry = {"id": rid, "label": r["verdict"], "final_label_after_review": final_rows[rid]["verdict"], "category": r["category"], "url": r["url"], "expected": r["expected_outcome"], "crawler_status": r["crawler_status"], "crawler_result": r["actual"],
             "crawler_error": (r["crawler_error"] or "")[:90], "probe_reading": p.get("predicted", "-"), "probe_detail": (p.get("note") or p.get("error") or "")[:60],
             "dns_recheck": json.dumps(p.get("dns_recheck", {})) if p.get("dns_recheck") else "", "dns_any_ok": p.get("dns_any_ok", ""), "why_labelled": r["env_flags"][:200],
             "evidence_files": "probes_after*.json[" + rid + "]; per_site.jsonl row " + rid + "; requests.jsonl (site " + (recs[rid]["site_url"][:50] if rid in recs else "") + ")",
             "fresh_probe_reading": "", "fresh_probe_detail": "", "fresh_dns": "", "label_holds": "", "new_label": ""}
    if rid in fresh_res:
        f = fresh_res[rid]
        reading = f.get("predicted", "unknown")
        expected = r["expected_outcome"]
        agrees = judge.probe_agrees(expected, reading, r["category"], r["subcategory"])
        dns_none = not f.get("dns_any_ok", False)
        unreachable_but_resolves = reading == "Unreachable" and f.get("dns_any_ok", False)
        if agrees is True or unreachable_but_resolves:
            holds = False
        elif agrees is None and reading != "unknown" and not dns_none:
            holds = False  # the probe cannot judge this kind of row (JavaScript), so a SITE-CHANGED label has no support
        elif agrees is False or dns_none:
            holds = True
        else:
            holds = True  # unknown reading: keep the label, do not change on no evidence
        entry.update(fresh_probe_reading=reading, fresh_probe_detail=(f.get("note") or f.get("error") or "")[:70], fresh_dns=json.dumps(f.get("dns_recheck", {})),
                     label_holds="YES" if holds else "NO")
        if not holds:
            net = r["crawler_status"] in ("unreachable",) or "cannot resolve host" in (r["crawler_error"] or "") or unreachable_but_resolves
            new = "ENV-DEPENDENT" if net else "MISMATCH"
            entry["new_label"] = new
            why = (f"fresh probe reads the site as '{reading}' ({entry['fresh_probe_detail']}), "
                   + ("a plain GET cannot execute JavaScript, so the probe cannot show that this JavaScript-redirect site changed; the SITE-CHANGED label has no support and the difference is a crawler result" if agrees is None and not unreachable_but_resolves else
                      "compatible with the dataset expectation, so the site had not changed; the crawler's failure was a network/DNS failure" if net and agrees else
                      "name resolves but the site is not reachable from this network" if unreachable_but_resolves else
                      "compatible with the dataset expectation, so the site had not changed; the difference is a crawler result"))
            reclass[rid] = {"to": new, "reason": why, "fresh_probe": {k: f.get(k) for k in ("predicted", "note", "error", "head_status", "dns_any_ok")}}
    review.append(entry)
changed = [(r["id"], r["verdict"], final_rows[r["id"]]["verdict"]) for r in rows if r["verdict"] != final_rows[r["id"]]["verdict"]]
(out / "label_changes_since_run_end.json").write_text(json.dumps({"rows_whose_verdict_differs_between_original_labels_and_final": changed}, indent=1), encoding="utf-8")
print("rows whose verdict differs original -> final:", changed)
keys = list(review[0])
with (out / "label_review.csv").open("w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=keys)
    w.writeheader()
    w.writerows(review)
(HERE / "dataset" / "label_reclassifications.json").write_text(json.dumps({
    "rule": "Fresh independent probe of 10 random SITE-CHANGED rows (seed 20261012) at Phase 1 close. A label is changed only when the fresh probe shows it does not hold. Applied by run_eval.build_reports. Same rule in Phase 2.",
    "sampled": orig_sample, "extra_checked": extra_ids, "rows": reclass}, indent=1, ensure_ascii=False), encoding="utf-8")
(out / "fresh_probe_review.json").write_text(json.dumps({"sampled_rows": orig_sample, "extra_rows_checked_because_the_refinement_moved_them": extra_ids, "fresh_probes": fresh_res, "reclassified": reclass}, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
print(f"{len(review)} rows listed; sampled {len(sample)}; holds: {sum(1 for e in review if e['label_holds']=='YES')}; does not hold: {sum(1 for e in review if e['label_holds']=='NO')}")
for e in review:
    if e["fresh_probe_reading"]:
        print(e["id"], e["category"][:16].ljust(16), e["url"][:38].ljust(38), "exp", e["expected"][:9].ljust(9), "crawler", e["crawler_result"][:12].ljust(12), "| orig probe", e["probe_reading"][:12].ljust(12), "| FRESH", e["fresh_probe_reading"][:12].ljust(12), e["fresh_probe_detail"][:26], "| holds", e["label_holds"], e["new_label"])
