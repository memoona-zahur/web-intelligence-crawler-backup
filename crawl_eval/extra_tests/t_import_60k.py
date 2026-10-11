"""A11 / L-10: import (NOT crawl) a synthetic 60,000-URL list through the real importer, and through the real web upload endpoint limits.
No network. Synthetic names under the reserved .invalid-like pattern are never fetched."""
import io
import random
import threading
import time

from common import save, setup

database, _ = setup("import60k", install_telemetry=False)
import telemetry
from app import importer
from app.limits import max_import_chars, max_upload_bytes

rng = random.Random(60000)
WORDS = ["acme", "north", "global", "delta", "prime", "apex", "blue", "green", "smart", "terra", "nova", "inter", "metro", "alpha", "omega", "pacific", "atlas", "summit"]
TLDS = [".com", ".net", ".org", ".co.uk", ".de", ".io"]


def domains(n):
    seen = set()
    while len(seen) < n:
        seen.add(f"{rng.choice(WORDS)}-{rng.choice(WORDS)}-{rng.randint(1, 999999):06d}{rng.choice(TLDS)}")
    return sorted(seen)


doms = domains(60_000)
short = "\n".join(f"https://www.{d}" for d in doms)  # domain only
realistic = "\n".join(f"https://www.{d}/{rng.choice(['about', 'about-us', 'services', 'products', 'company/overview', 'en/home', ''])}" for d in doms)
out = {"urls": len(doms), "chars_domain_only": len(short), "chars_with_paths": len(realistic), "avg_chars_per_line_domain_only": round(len(short) / len(doms), 1),
       "avg_chars_per_line_with_paths": round(len(realistic) / len(doms), 1), "MAX_IMPORT_CHARS": max_import_chars(), "MAX_UPLOAD_BYTES": max_upload_bytes()}
out["urls_that_fit_in_limit_at_domain_only_avg"] = int(max_import_chars() / (len(short) / len(doms)))
out["urls_that_fit_in_limit_at_with_paths_avg"] = int(max_import_chars() / (len(realistic) / len(doms)))

# 1) the real importer function on 60,000 rows
peak = {"v": 0.0}
stop = threading.Event()


def sampler():
    while not stop.is_set():
        peak["v"] = max(peak["v"], telemetry.rss_mb())
        stop.wait(0.2)


threading.Thread(target=sampler, daemon=True).start()
rss0 = telemetry.rss_mb()
t = time.monotonic()
with database.get_session() as session:
    res = importer.import_urls(session, short)
out["importer_function"] = {"seconds": round(time.monotonic() - t, 1), "added": res.added, "duplicates": len(res.duplicates), "invalid": len(res.invalid),
                            "rss_before_mb": round(rss0, 1), "rss_peak_mb": round(peak["v"], 1)}
# second import of the same list: incremental ingestion / duplicate detection speed (CR-A02)
t = time.monotonic()
with database.get_session() as session:
    res2 = importer.import_urls(session, short)
out["second_import_same_list"] = {"seconds": round(time.monotonic() - t, 1), "added": res2.added, "duplicates": len(res2.duplicates)}
stop.set()

# 2) the real web endpoint (POST /import) with the same lists. TestClient WITHOUT a 'with' block: the app's lifespan (init_db) is not run.
try:
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    for label, text in (("domain_only_60000_lines", short), ("with_paths_60000_lines", realistic)):
        b = text.encode("utf-8")
        r = client.post("/import", files={"file": ("urls.csv", io.BytesIO(b), "text/csv")}, data={"urls": ""}, follow_redirects=False)
        out.setdefault("web_endpoint_post_import", {})[label] = {"bytes": len(b), "http_status": r.status_code, "redirect_to": r.headers.get("location"),
                                                                  "accepted": "imported=1" in (r.headers.get("location") or ""),
                                                                  "refused_as_too_large": "notice=upload" in (r.headers.get("location") or "")}
        if "notice=upload" not in (r.headers.get("location") or ""):  # accepted by the endpoint: clean the DB so the next case starts equal
            pass
except Exception as exc:  # noqa: BLE001
    out["web_endpoint_error"] = f"{type(exc).__name__}: {exc}"
save("t_import_60k", out)
