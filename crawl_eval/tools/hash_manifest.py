"""SHA-256 manifest of the crawler code, to prove it is unchanged.

    python crawl_eval/tools/hash_manifest.py create  <out.json>
    python crawl_eval/tools/hash_manifest.py verify  <manifest.json>

Covers every file under app/, templates/, tests/ and scripts/ (never __pycache__).
Exit code 0 = identical, 1 = something differs.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLDERS = ("app", "templates", "tests", "scripts")


def _scan() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for folder in FOLDERS:
        for path in sorted((ROOT / folder).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def create(out: Path) -> None:
    hashes = _scan()
    combined = hashlib.sha256("".join(f"{k}:{v}\n" for k, v in sorted(hashes.items())).encode()).hexdigest()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"files": hashes, "combined_sha256": combined, "file_count": len(hashes)}, indent=2))
    print(f"{len(hashes)} files, combined {combined}")


def verify(manifest: Path) -> int:
    expected = json.loads(manifest.read_text())["files"]
    actual = _scan()
    changed = [k for k in expected if k in actual and expected[k] != actual[k]]
    missing = [k for k in expected if k not in actual]
    added = [k for k in actual if k not in expected]
    if changed or missing or added:
        print("MISMATCH", {"changed": changed, "missing": missing, "added": added})
        return 1
    print(f"OK: {len(actual)} files match the baseline")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("create", "verify"):
        sys.exit(__doc__)
    target = Path(sys.argv[2])
    if sys.argv[1] == "create":
        create(target)
    else:
        sys.exit(verify(target))
