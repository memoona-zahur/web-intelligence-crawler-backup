"""The frozen evaluation harness must keep working against this code (plan GATE 4, section 1)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_every_seam_the_harness_uses_is_present():
    done = subprocess.run([sys.executable, "-B", str(ROOT / "crawl_eval" / "tools" / "check_harness_contract.py")], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "checks passed" in done.stdout


def test_the_frozen_judge_is_intact():
    done = subprocess.run([sys.executable, "-B", str(ROOT / "crawl_eval" / "tools" / "freeze_judge.py"), "verify"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0 and "FROZEN JUDGE OK" in done.stdout
