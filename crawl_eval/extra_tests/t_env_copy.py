"""L-12: is a value in .env used by the crawler CLI? Done on a COPY of app/ in the scratch folder (the repo gets no .env)."""
import shutil
import subprocess
import sys
from pathlib import Path

from common import ROOT, save

copy = Path("C:/crawl_eval_data/scratch/envcopy")
shutil.rmtree(copy, ignore_errors=True)
shutil.copytree(ROOT / "app", copy / "app", ignore=shutil.ignore_patterns("__pycache__"))
(copy / ".env").write_text("CRAWL_CONCURRENCY=3\nCRAWLER_CONTACT_URL=https://example.test/bot-policy\n", encoding="utf-8")
code = r"""
import sys; sys.dont_write_bytecode = True
import os, json
out = {"env_before": {k: os.environ.get(k) for k in ("CRAWL_CONCURRENCY", "CRAWLER_CONTACT_URL")}}
import app.limits as L, app.crawler.config as C
import app.crawler_cli  # what `python -m app.crawler_cli` imports
out["after_importing_crawler_cli"] = {"crawl_concurrency": L.crawl_concurrency(), "user_agent": C.user_agent()}
import app.ops  # `python -m app.ops` imports
out["after_importing_ops"] = {"crawl_concurrency": L.crawl_concurrency(), "user_agent": C.user_agent()}
import app.classifier  # only this import runs load_dotenv()
out["after_importing_classifier"] = {"crawl_concurrency": L.crawl_concurrency(), "user_agent": C.user_agent()}
print(json.dumps(out))
"""
r = subprocess.run([sys.executable, "-B", "-c", code], cwd=copy, capture_output=True, text=True)
import json
try:
    res = json.loads(r.stdout.strip().splitlines()[-1])
except Exception:
    res = {"error": r.stderr[-800:], "stdout": r.stdout[-400:]}
save("t_env_copy", {"what": ".env contains CRAWL_CONCURRENCY=3 and CRAWLER_CONTACT_URL=https://example.test/bot-policy (copy of app/ in scratch, repo untouched)", "result": res,
                    "reading": "if the first two blocks still show 10 / the default User-Agent, the crawler CLI ignores .env until app.classifier is imported (lead L-12)"})
