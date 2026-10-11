"""What a crawl leaves in the database (CR-B06-B08, D07, D10, E06-E09, F09, H02-H05; issues ISS-13, ISS-27)."""

import gzip
from datetime import timedelta

from sqlalchemy import select

from app import settings
from app.crawler import runner
from app.crawler.persist import purge_raw_html
from app.crawler.pipeline import CrawlResult
from app.database import get_session
from app.models import CrawlError, DomainStat, FetchAttempt, Page, PageContent, Website
from app.profile import content_hash
from app.recovery import utcnow
from tests.sitekit import crawl, standard_site


def run_save(site_id, result):
    runner._save(site_id, result)


def full_result(url="https://acme.com"):
    result = crawl(standard_site(), url)
    assert result.status == "crawled"
    return result


def test_a_good_crawl_fills_every_crawl_fact(make_website):
    site_id = make_website("https://acme.com")
    result = full_result()
    result.job_id, result.attempt_no = 7, 1
    run_save(site_id, result)
    with get_session() as session:
        site = session.get(Website, site_id)
        assert (site.status, site.crawl_status, site.website_status, site.crawl_outcome) == ("crawled", "crawled", "Crawled", "Completed")
        assert site.final_url == "https://acme.com" and site.http_status == 200 and site.pages_crawled == 5 and site.pages_attempted >= 5
        assert site.last_crawled_at and site.content_crawled_at and site.content_hash == content_hash(site.clean_text) and site.content_is_stale is False
        assert site.crawl_error is None and site.crawl_error_category is None and site.retry_count == 1 and site.domain_key == "acme.com"
        pages = session.scalars(select(Page).where(Page.website_id == site_id).order_by(Page.id)).all()
        assert [p.page_type for p in pages] == ["home", "about", "products", "services", "industries"] and all(p.job_id == 7 for p in pages)
        assert all(p.http_status == 200 and p.crawl_status == "fetched" and p.crawled_at and p.content_length > 0 for p in pages)
        contents = session.scalars(select(PageContent).where(PageContent.website_id == site_id)).all()
        assert len(contents) == 5 and all(len(c.content_hash) == 64 and c.text and c.extraction_method for c in contents)
        attempts = session.scalars(select(FetchAttempt).where(FetchAttempt.website_id == site_id)).all()
        assert attempts and any(a.url.endswith("/robots.txt") for a in attempts) and all(a.attempt_no >= 1 for a in attempts)


def test_cleaned_text_is_stored_apart_from_crawl_metadata(make_website):
    site_id = make_website("https://acme.com")
    run_save(site_id, full_result())
    with get_session() as session:
        page = session.scalars(select(Page).where(Page.website_id == site_id)).first()
        assert not hasattr(page, "text")                                 # the pages table has no text column
        assert session.scalar(select(PageContent.text).where(PageContent.page_id == page.id))


def test_each_stored_fact_traces_to_a_fetched_page(make_website):  # CR-E09
    site_id = make_website("https://acme.com")
    run_save(site_id, full_result())
    with get_session() as session:
        site = session.get(Website, site_id)
        urls = {p.url for p in session.scalars(select(Page).where(Page.website_id == site_id))}
        for line in site.clean_text.splitlines():
            if line.startswith("=== PAGE:"):
                assert line.split("|", 1)[1].strip() in urls
            if line.startswith("Retrieved via"):
                assert line.split(": ", 1)[1].strip() in urls


def test_crawling_again_replaces_the_page_rows_and_keeps_the_history(make_website):
    site_id = make_website("https://acme.com")
    run_save(site_id, full_result())
    run_save(site_id, full_result())
    with get_session() as session:
        assert session.query(Page).filter_by(website_id=site_id).count() == 5              # replaced, not doubled
        assert session.query(FetchAttempt).filter_by(website_id=site_id).count() > 8        # attempts of both crawls are kept


def test_failed_recrawl_keeps_old_text_but_marks_it_stale(make_website):  # ISS-27, CR-B08
    site_id = make_website("https://acme.com")
    run_save(site_id, full_result())
    run_save(site_id, CrawlResult("unreachable", None, "cannot reach the site", 0, error_category="network", crawl_outcome="Failed", website_status="Unreachable"))
    with get_session() as session:
        site = session.get(Website, site_id)
        assert site.status == "unreachable" and site.crawl_status == "unreachable" and site.crawl_error == "cannot reach the site"
        assert site.clean_text and site.content_is_stale is True
        assert session.query(Page).filter_by(website_id=site_id).count() == 5             # the old pages are still there for review
        error = session.scalars(select(CrawlError).where(CrawlError.website_id == site_id)).one()
        assert error.category == "network" and error.message == "cannot reach the site" and error.last_attempt_at


def test_crawl_status_is_separate_from_classification_status(make_website):  # CR-B08
    site_id = make_website("https://acme.com", status="classified", classification_status="classified", crawl_status="crawled", company_name="Acme",
                           clean_text="old", content_hash=content_hash("old"))
    result = full_result()
    run_save(site_id, result)
    with get_session() as session:
        site = session.get(Website, site_id)
        assert site.crawl_status == "crawled" and site.company_name is None and site.classification_status is None   # text changed: reclassify
    unchanged = make_website("https://b.com", status="classified", classification_status="classified", crawl_status="crawled", company_name="B",
                             clean_text=result.clean_text, content_hash=content_hash(result.clean_text))
    run_save(unchanged, result)
    with get_session() as session:
        site = session.get(Website, unchanged)
        assert site.company_name == "B" and site.status == "classified" and site.crawl_status == "crawled"             # same text: classification stays


def test_partial_crawl_keeps_the_evidence_and_the_failed_page_is_recorded(make_website):
    site = standard_site()
    site.add("/services", "boom", status=500)
    result = crawl(site)
    site_id = make_website("https://acme.com")
    run_save(site_id, result)
    with get_session() as session:
        row = session.get(Website, site_id)
        assert row.crawl_outcome == "Partial" and row.clean_text and row.pages_crawled >= 3
        failed = session.scalars(select(Page).where(Page.website_id == site_id, Page.crawl_status == "failed")).one()
        assert failed.http_status == 500 and "HTTP 500" in failed.error
        error = session.scalars(select(CrawlError).where(CrawlError.website_id == site_id, CrawlError.category == "page_failed")).one()
        assert error.url.endswith("/services")


def test_redirected_site_stores_final_url_and_status_word(make_website):
    from tests.sitekit import Site, page

    site = Site().redirect("/", "https://new-owner.com/")
    site.add("new-owner.com/", page("New Owner"))
    result = crawl(site)
    site_id = make_website("https://acme.com")
    run_save(site_id, result)
    with get_session() as session:
        row = session.get(Website, site_id)
        assert (row.status, row.website_status, row.final_url) == ("redirected", "Redirected", "https://new-owner.com/") and row.clean_text


def test_a_site_that_redirects_to_a_site_already_in_the_list_is_flagged_as_a_duplicate(make_website):  # CR-B05
    from tests.sitekit import Site, page

    target = make_website("https://new-owner.com")
    old = make_website("https://old-name.com")
    site = Site().redirect("/", "https://new-owner.com/")
    site.add("new-owner.com/", page("New Owner"))
    run_save(old, crawl(site, "https://old-name.com"))
    with get_session() as session:
        row = session.get(Website, old)
        assert row.status == "redirected" and row.duplicate_of_id == target and "already in the list" in row.crawl_error
        assert session.get(Website, target).duplicate_of_id is None
    other = make_website("https://other-old.com")
    alone = Site().redirect("/", "https://somewhere-new.com/")
    alone.add("somewhere-new.com/", page("Somewhere"))
    run_save(other, crawl(alone, "https://other-old.com"))
    with get_session() as session:
        assert session.get(Website, other).duplicate_of_id is None          # the target is not in the list: just Redirected


def test_the_extracting_stage_marks_the_website_active(make_website):
    from app.crawler import runner as r

    site_id = make_website("https://acme.com")
    r._task_state(0, "extracting", site_id)
    with get_session() as session:
        site = session.get(Website, site_id)
        assert site.status == "extracting" and site.website_status == "Active"


def test_retry_after_is_stored_as_the_next_retry_time(make_website):
    site_id = make_website("https://acme.com")
    run_save(site_id, CrawlResult("robots_blocked", None, "robots.txt unavailable (HTTP 503)", 0, error_category="robots_unavailable", retry_after=900.0, crawl_outcome="Blocked"))
    with get_session() as session:
        row = session.get(Website, site_id)
        assert row.next_retry_at and timedelta(minutes=14) < row.next_retry_at - utcnow() < timedelta(minutes=16)
        assert row.crawl_outcome == "Blocked" and row.crawl_error_category == "robots_unavailable"


def test_unknown_website_is_a_no_op():
    run_save(424242, CrawlResult("crawled", "x", None, 1))


# --- domain health is written (and read by the queue; see test_queue) --------------------------------------------


def test_domain_health_records_success_failure_and_latency(make_website):
    site_id = make_website("https://www.acme.com")
    for latency in (100, 200):
        run_save(site_id, CrawlResult("crawled", "t", None, 1, "https://acme.com", latency))
    with get_session() as session:
        stat = session.scalars(select(DomainStat).where(DomainStat.domain == "acme.com")).one()
        assert stat.success_count == 2 and stat.consecutive_failures == 0 and stat.last_latency_ms == 200 and 100 < stat.avg_latency_ms < 200 and stat.backoff_until is None


def test_three_failures_in_a_row_start_a_backoff_and_a_success_ends_it(make_website):
    site_id = make_website("https://acme.com")
    for _ in range(3):
        run_save(site_id, CrawlResult("unreachable", None, "timeout", 0, error_category="timeout"))
    with get_session() as session:
        stat = session.scalars(select(DomainStat)).one()
        assert stat.consecutive_failures == 3 and stat.failure_count == 3 and stat.backoff_until > utcnow()
    run_save(site_id, CrawlResult("crawled", "t", None, 1))
    with get_session() as session:
        stat = session.scalars(select(DomainStat)).one()
        assert stat.consecutive_failures == 0 and stat.backoff_until is None


def test_content_verdicts_are_not_host_health_problems(make_website):
    """Found by the harness run: parked / under construction / login / 404 pages prove the server answers; they must never start a back-off."""
    site_id = make_website("https://acme.com")
    for status, category in (("parked", "parked"), ("under_construction", "under_construction"), ("requires_review", "login_wall"), ("failed", "http_4xx"),
                             ("robots_blocked", "robots_disallowed"), ("invalid", "unsafe_target")):
        run_save(site_id, CrawlResult(status, None, "x", 0, error_category=category))
    with get_session() as session:
        stat = session.scalars(select(DomainStat)).one()
        assert stat.consecutive_failures == 0 and stat.backoff_until is None and stat.failure_count == 6


def test_servers_on_different_ports_have_separate_health_records(make_website):
    a, b = make_website("http://127.0.0.1:8830"), make_website("http://127.0.0.1:8831")
    for _ in range(3):
        run_save(a, CrawlResult("unreachable", None, "timeout", 0, error_category="timeout"))
    run_save(b, CrawlResult("crawled", "t", None, 1))
    with get_session() as session:
        stats = {s.domain: s for s in session.scalars(select(DomainStat))}
        assert set(stats) == {"127.0.0.1:8830", "127.0.0.1:8831"}
        assert stats["127.0.0.1:8830"].backoff_until is not None and stats["127.0.0.1:8831"].backoff_until is None


def test_a_block_with_retry_after_backs_the_domain_off_at_once(make_website):
    site_id = make_website("https://acme.com")
    run_save(site_id, CrawlResult("blocked", None, "HTTP 429", 0, error_category="rate_limited", retry_after=7200.0))
    with get_session() as session:
        stat = session.scalars(select(DomainStat)).one()
        assert stat.blocked_reason == "HTTP 429" and stat.blocked_at and stat.backoff_until - utcnow() > timedelta(hours=1, minutes=50)


# --- raw HTML (optional, off by default) ---------------------------------------------------------------------------


def test_raw_html_is_not_stored_by_default(make_website, tmp_path, monkeypatch):
    monkeypatch.setenv("RAW_HTML_DIR", str(tmp_path / "raw"))
    site_id = make_website("https://acme.com")
    run_save(site_id, full_result())
    with get_session() as session:
        assert all(c.raw_path is None for c in session.scalars(select(PageContent)))
    assert not (tmp_path / "raw").exists()


def test_raw_html_is_stored_compressed_and_purged_after_the_retention_period(make_website, tmp_path, monkeypatch):
    monkeypatch.setenv("RAW_HTML_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("RAW_HTML_RETENTION_DAYS", "30")
    site_id = make_website("https://acme.com")
    run_save(site_id, full_result())
    with get_session() as session:
        paths = [c.raw_path for c in session.scalars(select(PageContent))]
    assert paths and all(p and p.endswith(".html.gz") for p in paths)
    assert b"<html" in gzip.open(paths[0]).read()
    assert purge_raw_html() == 0                                          # still within the retention period
    import time

    assert purge_raw_html(now=time.time() + 31 * 86400) == len(paths)     # a month later they go
    assert not any(__import__("pathlib").Path(p).exists() for p in paths)
    monkeypatch.setenv("RAW_HTML_RETENTION_DAYS", "0")
    assert purge_raw_html() == 0 and settings.raw_html_retention_days() == 0
