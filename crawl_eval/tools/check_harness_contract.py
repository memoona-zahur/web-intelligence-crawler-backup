"""Check that the code under test still offers every seam the FROZEN evaluation harness hooks into (plan GATE 4, section 1).

    python -B crawl_eval/tools/check_harness_contract.py        (exit 0 = every seam present)

The harness (run_eval.py, telemetry.py) patches functions by name and reads database columns. If the crawler is refactored so that one of them
changes its name or signature, the harness would silently measure nothing; this check makes that a loud failure instead.
Not a frozen file: it only reads.
"""
from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CRAWLER_MODE", "test")
sys.dont_write_bytecode = True

failures: list[str] = []
checked = 0


def check(ok: bool, what: str) -> None:
    global checked
    checked += 1
    if not ok:
        failures.append(what)


def params(fn) -> list[str]:
    return [p.name for p in inspect.signature(fn).parameters.values() if p.default is inspect.Parameter.empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]


def main() -> int:
    import app.crawler.browser as browser
    import app.crawler.config as config
    import app.crawler.extract as extract
    import app.crawler.fetcher as fetcher
    import app.crawler.pipeline as pipeline
    import app.crawler.runner as runner
    import app.database as database
    import app.importer as importer
    import app.limits as limits
    from app.models import Base, DomainStat, Job, Website

    # --- functions the wrappers replace (module attribute names matter: the code must call them through the module) ---
    seams = [
        (fetcher, "_one_attempt", ["client", "url", "expect_html"]),                    # exactly these three: the wrapper takes no more
        (fetcher, "assert_public_url", ["url"]), (browser, "assert_public_url", ["url"]), (browser, "render_page", ["url"]),
        (pipeline, "load_robots", ["client", "url", "cache"]), (pipeline, "render_page", ["url"]), (pipeline, "crawl_one", ["client", "normalized_url", "robots_cache"]),
        (runner, "crawl_one", ["client", "normalized_url", "robots_cache"]), (runner, "_save", ["site_id", "result"]),
        (importer, "extract_urls", ["text"]), (importer, "normalize_website", ["raw"]), (importer, "is_safe_import_target", ["url"]),
    ]
    for module, name, expected in seams:
        fn = getattr(module, name, None)
        check(callable(fn), f"{module.__name__}.{name} exists")
        if callable(fn):
            check(params(fn) == expected, f"{module.__name__}.{name} takes exactly {expected} (found {params(fn)})")
    import asyncio

    for module, name in ((fetcher, "_one_attempt"), (browser, "render_page"), (pipeline, "crawl_one"), (runner, "crawl_one"), (pipeline, "load_robots")):
        check(inspect.iscoroutinefunction(getattr(module, name)), f"{module.__name__}.{name} is async")
    for module, name in ((fetcher, "assert_public_url"), (runner, "_save"), (importer, "extract_urls"), (importer, "normalize_website")):
        check(not inspect.iscoroutinefunction(getattr(module, name)), f"{module.__name__}.{name} is a plain function")
    run_params = inspect.signature(runner.run).parameters
    check({"limit", "site_ids", "force", "concurrency", "log"} <= set(run_params), "runner.run(limit, site_ids, force, concurrency, log)")
    check(set(params(importer.import_urls)) == {"session", "text"}, "importer.import_urls(session, text, ...) with optional extras")

    # --- the importer must call the wrapped names by module attribute (patched functions are looked up at call time) ---
    source = inspect.getsource(importer.import_urls)
    check("normalize_website(" in source and "is_safe_import_target(" in source, "import_urls calls normalize_website and is_safe_import_target")
    check("extract_urls(" in source, "import_urls calls extract_urls")
    check(source.index("normalize_website(") < source.index("is_safe_import_target("), "normalize_website is called before is_safe_import_target for each line")

    # --- results and rules the telemetry reads ---
    result = pipeline.CrawlResult("crawled", "t", None, 1)
    for attr in ("status", "error", "pages_crawled", "final_url", "latency_ms", "clean_text"):
        check(hasattr(result, attr), f"CrawlResult.{attr}")
    rules = fetcher.RobotsRules(origin="https://x.com")
    check(hasattr(rules, "origin") and hasattr(rules, "missing"), "RobotsRules.origin and .missing")
    check(hasattr(config, "CONCURRENCY") and hasattr(limits, "crawl_concurrency"), "config.CONCURRENCY and limits.crawl_concurrency()")
    check(hasattr(extract, "DROP_TAGS") and hasattr(extract, "DROP_NAME_HINTS") and hasattr(extract, "extract_page"), "extract.DROP_TAGS, DROP_NAME_HINTS, extract_page")
    check(hasattr(fetcher, "FetchResult") and {"status_code", "final_url", "content", "content_type"} <= set(fetcher.FetchResult.__dataclass_fields__), "FetchResult fields")

    # --- database: names the harness imports and columns it reads ---
    check(all(hasattr(database, n) for n in ("engine", "SessionLocal", "get_session")), "database.engine / SessionLocal / get_session")
    for column in ("status", "crawl_status", "crawl_error", "pages_crawled", "last_crawled_at", "content_hash", "original_url", "clean_text", "normalized_website", "source_batch"):
        check(hasattr(Website, column), f"Website.{column}")
    for column in ("id", "kind", "status", "added", "note"):
        check(hasattr(Job, column), f"Job.{column}")
    check(hasattr(DomainStat, "domain"), "DomainStat")
    check("websites" in Base.metadata.tables and "jobs" in Base.metadata.tables, "tables created by Base.metadata.create_all")

    # --- the clean_text format the judge parses ---
    import re

    from tests.sitekit import crawl, standard_site

    out = crawl(standard_site())
    check(bool(re.search(r"^=== PAGE: (.*?) \| (\S+)\n", out.clean_text or "", re.M)), "clean_text sections look like '=== PAGE: label | url'")
    check("Retrieved via http:" in (out.clean_text or ""), "clean_text carries 'Retrieved via http|browser:'")

    for line in failures:
        print("MISSING:", line)
    print(f"harness contract: {checked - len(failures)}/{checked} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
