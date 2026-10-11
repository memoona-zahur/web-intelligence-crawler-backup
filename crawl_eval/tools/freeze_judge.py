"""Freeze the judge, oracle and labelling code (Phase 1 close-out, condition 2).
    python freeze_judge.py write <results dir>     -> writes crawl_eval/FROZEN_JUDGE.json and adds "frozen_judge" to <results dir>/run_manifest.json
    python freeze_judge.py verify                  -> exit 0 only if every frozen file still has its recorded SHA-256 (Phase 2 must run this before using the judge)
Phase 2 must use the identical judge: judge.py, the labelling/probe/report functions in run_eval.py, the dataset and the oracle files below.
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
FROZEN = {
    "judge (mechanical expected-vs-actual rules, compatibility table, checks)": "judge.py",
    "labelling + probe + verdict logic + reports (run_eval.py: build_reports, probe_after, probe_recheck, predict_word, dns_robust)": "run_eval.py",
    "pass-through telemetry wrappers + safety net + watchdog": "telemetry.py",
    "scenario server (oracle for local scenarios)": "scenario_server.py",
    "dataset with expected outcomes (the oracle)": "dataset/testing_URLs.csv",
    "oracle limitations rule file": "dataset/oracle_limitations.json",
    "label reclassifications (fresh-probe review)": "dataset/label_reclassifications.json",
    "label review procedure": "relabel_check.py",
    "post-run analysis (gold set, browser, politeness)": "analyze_full.py",
    "static rows (hand-designed oracle rows)": "tools/static_rows.py",
    "app code hash manifest (proves the crawler under test)": "baseline/run_manifest.json",
    "hash tool": "tools/hash_manifest.py",
}
NOT_FROZEN_NOTE = "make_deliverables.py and deliverables_data.py write the Phase 1 report text; they are not part of the judge."


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def compute():
    files = {rel: {"role": role, "sha256": sha(HERE / rel)} for role, rel in FROZEN.items()}
    combined = hashlib.sha256("".join(f"{k}:{v['sha256']}\n" for k, v in sorted(files.items())).encode()).hexdigest()
    return {"files": files, "combined_sha256": combined, "note": NOT_FROZEN_NOTE}


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "write":
        out = Path(sys.argv[2])
        rec = compute()
        old_path = HERE / "FROZEN_JUDGE.json"
        if old_path.exists():  # keep every earlier freeze on record
            old = json.loads(old_path.read_text(encoding="utf-8"))
            rec["previous_freezes"] = old.get("previous_freezes", []) + [{"combined_sha256": old["combined_sha256"], "frozen_at": old.get("frozen_at"), "git_tag": old.get("git_tag", "phase1-complete"),
                                                                       "files": {k: v["sha256"] for k, v in old["files"].items()}}]
            rec["files_changed_since_previous_freeze"] = [k for k, v in rec["files"].items() if old["files"].get(k, {}).get("sha256") != v["sha256"]]
            rec["git_tag"] = "phase1-complete-v2"
            rec["reason_for_refreeze"] = "Label review round 2: every remaining SITE-CHANGED / ENV-DEPENDENT row re-probed; written ENV-DEPENDENT rule added to relabel_check.py; run_eval.py applies reclassifications to ENV-DEPENDENT labels too."
        rec["frozen_at"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
        rec["rule"] = "Phase 2 must use the identical judge. Any change needs the project owner's written approval and a new freeze."
        (HERE / "FROZEN_JUDGE.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
        mp = out / "run_manifest.json"
        m = json.loads(mp.read_text(encoding="utf-8"))
        m["frozen_judge"] = rec
        mp.write_text(json.dumps(m, indent=1, ensure_ascii=False), encoding="utf-8")
        print("frozen:", rec["combined_sha256"])
    elif mode == "verify":
        rec = json.loads((HERE / "FROZEN_JUDGE.json").read_text(encoding="utf-8"))
        bad = [rel for rel, v in rec["files"].items() if sha(HERE / rel) != v["sha256"]]
        print("FROZEN JUDGE OK" if not bad else f"FROZEN JUDGE CHANGED: {bad}")
        sys.exit(1 if bad else 0)
    else:
        sys.exit(__doc__)
