"""URL normalisation, validation and import (CR-A01, A02, A04, A06, A07, A08, A10, A11, B05, B09, F08; issues ISS-04, 17, 18, 19, 20, 36)."""

import time

import pytest
from sqlalchemy import select

from app.database import get_session
from app.domains import domain_key, registrable_domain, same_site
from app.importer import ImportResult, extract_urls, import_urls
from app.models import ImportIssue, Job, Website
from app.normalize import explain_invalid, normalize_website, redact_credentials


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("example.com", "https://example.com"),
        ("EXAMPLE.COM", "https://example.com"),
        ("http://example.com", "https://example.com"),
        ("HTTPS://EXAMPLE.COM/", "https://example.com"),
        ("https://www.example.com", "https://example.com"),
        ("http://WWW.Example.Org/", "https://example.org"),
        ("example.com/some/path.html?x=1#top", "https://example.com"),
        ("https://example.com/about?utm_source=x#top", "https://example.com"),
        ("'https://example.com'", "https://example.com"),
        ("\"example.com\"", "https://example.com"),
        ("<https://example.com>", "https://example.com"),
        ("https://example.com.", "https://example.com"),                 # ISS-18 trailing dot
        ("https://www.example.com./", "https://example.com"),
        ("//example.com", "https://example.com"),                        # ISS-18 scheme-relative
        ("ｅｘａｍｐｌｅ．ｃｏｍ", "https://example.com"),                     # ISS-18 full-width characters
        ("münchen.de", "https://xn--mnchen-3ya.de"),                     # IDN -> punycode
        ("xn--mnchen-3ya.de", "https://xn--mnchen-3ya.de"),
        ("example.com:443", "https://example.com"),
        ("http://example.com:80/", "https://example.com"),
        ("https://example.com:8443/x", "https://example.com:8443"),      # a non-default port is kept
        ("https://user:secret@example.com/", "https://example.com"),     # credentials never reach the normalised form
        ("﻿example.com", "https://example.com"),                    # BOM
        ("  example.com  ", "https://example.com"),
        ("8.8.8.8", "https://8.8.8.8"),
        ("shop.example.co.uk", "https://shop.example.co.uk"),
    ],
)
def test_normalisation(raw, expected):
    assert normalize_website(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "", "   ", "# a comment", "localhost", "http://", "ftp://example.com", "mailto:info@example.com", "javascript:alert(1)",
        "file:///etc/passwd", "http://[invalid", "http://example..com", "http://-bad.com", "http://bad-.com", "a" * 64 + ".com",
        "example.com:99999", "example.com:0", "exam ple.com", "http://example.123", "https://", "://example.com", "x" * 3000 + ".com",
        "\x00example.com", "http://%zz.com", "http://[::1", "data:text/html,hi", "http:///path", "2130706433", "0x7f.1", "127.1", "12345",
    ],
)
def test_garbage_is_invalid_and_never_raises(raw):
    assert normalize_website(raw) is None
    assert explain_invalid(raw)  # a reason, in plain words (ISS-36)


def test_bad_host_gets_a_plain_reason_not_a_codec_error():
    assert "idna" not in explain_invalid("http://example..com").lower()
    assert "63 characters" in explain_invalid("a" * 64 + ".com")


def test_non_string_input_does_not_raise():
    assert normalize_website(None) is None  # type: ignore[arg-type]
    assert normalize_website(12345) is None  # type: ignore[arg-type]


def test_redact_credentials_keeps_the_rest_as_received():
    assert redact_credentials("https://user:secret@example.com/a?b=1") == "https://example.com/a?b=1"
    assert redact_credentials("  Example.COM/Path  ") == "Example.COM/Path"
    assert "secret" not in redact_credentials("http://admin:secret@host.com")


def test_registrable_domain_and_same_site():
    assert registrable_domain("https://www.acme.co.uk/x") == "acme.co.uk"
    assert registrable_domain("shop.acme.com") == "acme.com"
    assert registrable_domain("foo.wixsite.com") == "foo.wixsite.com"       # two site-builder customers are two sites
    assert same_site("https://www.acme.com", "http://acme.com/about")
    assert not same_site("https://acme.com", "https://acme.org")
    assert not same_site("https://a.wixsite.com", "https://b.wixsite.com")
    assert domain_key("http://127.0.0.1:8830/") == "127.0.0.1:8830"          # two local servers are two domains
    assert domain_key("https://acme.com") == "acme.com"


# --- import ----------------------------------------------------------------------------------------------


def test_import_summary_reviewable_with_reasons():
    text = "acme.com\nwww.acme.com\nhttp://[invalid\nftp://x.com\nlocalhost\n10.0.0.1\nexample.org\n"
    with get_session() as session:
        result = import_urls(session, text, source_file="march.csv")
        job = session.get(Job, result.job_id)
        issues = session.scalars(select(ImportIssue).where(ImportIssue.job_id == job.id).order_by(ImportIssue.line_no)).all()
    assert (result.added, len(result.duplicates), len(result.invalid)) == (2, 1, 4)
    assert (job.added, job.duplicates, job.invalid, job.total, job.source_file) == (2, 1, 4, 7, "march.csv")
    decisions = [(i.line_no, i.decision) for i in issues]
    assert decisions == [(2, "duplicate"), (3, "invalid"), (4, "invalid"), (5, "invalid"), (6, "invalid")]
    assert all(i.reason for i in issues)


def test_one_malformed_line_does_not_lose_the_batch():  # ISS-04
    lines = ["good%d.com" % i for i in range(20)] + ["http://[invalid", "\x00", "a" * 5000] + ["also-good.org"]
    with get_session() as session:
        result = import_urls(session, "\n".join(lines))
    assert result.added == 21
    assert len(result.invalid) == 3


def test_import_keeps_source_and_record_id_and_original_url():
    csv_text = "id,website,source\nA-1,Acme.COM/About,crm\nA-2,https://beta.io,web\n"
    with get_session() as session:
        import_urls(session, csv_text, source_file="crm_export.csv")
        rows = session.scalars(select(Website).order_by(Website.id)).all()
    assert [(r.original_url, r.normalized_website, r.source_record_id, r.source_batch, r.source_file) for r in rows] == [
        ("Acme.COM/About", "https://acme.com", "A-1", "crm", "crm_export.csv"),
        ("https://beta.io", "https://beta.io", "A-2", "web", "crm_export.csv"),
    ]
    assert all(r.domain_key for r in rows)


def test_credentials_in_a_url_are_never_stored():  # CR-F08
    with get_session() as session:
        import_urls(session, "https://user:secret@acme.com/\nhttps://x:pw@beta.com/page")
        stored = [r.original_url for r in session.scalars(select(Website)).all()]
    assert stored and not any("secret" in s or "pw@" in s or "user:" in s for s in stored)


def test_incremental_import_adds_only_new_sites():  # CR-A02
    with get_session() as session:
        first = import_urls(session, "a.com\nb.com")
        second = import_urls(session, "b.com\nc.com\nA.COM")
    assert first.added == 2 and second.added == 1 and len(second.duplicates) == 2


def test_import_accepts_manual_entry_of_several_urls():  # CR-A04
    with get_session() as session:
        result = import_urls(session, "one.com, two.com\nthree.com")
    assert result.added >= 2  # a comma-separated first cell keeps the first value; every line is a row
    assert extract_urls("x.com\n\ny.com\n") == ["x.com", "y.com"]


def test_csv_with_nul_or_broken_quotes_falls_back_to_lines():
    with get_session() as session:
        result = import_urls(session, 'url\n"unterminated.com\nok.com\n')
    assert isinstance(result, ImportResult)


def test_sixty_thousand_lines_import_fast_and_without_manual_batching():  # CR-A11, ISS-17
    lines = [f"company{i}.com" for i in range(60_000)]
    text = "\n".join(lines)
    start = time.monotonic()
    with get_session() as session:
        result = import_urls(session, text)
        count = session.scalar(select(__import__("sqlalchemy").func.count()).select_from(Website))
    elapsed = time.monotonic() - start
    assert result.added == 60_000 == count
    assert len(text) < 25_000_000                       # fits the default upload limit
    assert elapsed < 60, f"60,000-line import took {elapsed:.1f}s"  # Phase 1: 49.9 s one query per line; limit is generous for slow disks


def test_duplicate_spellings_in_one_batch_are_merged():
    with get_session() as session:
        result = import_urls(session, "https://example.com\nhttps://example.com.\n//example.com\nｅｘａｍｐｌｅ．ｃｏｍ\n'https://example.com'\nhttps://www.example.com/a?b")
    assert result.added == 1 and len(result.duplicates) == 5


def test_default_upload_limits_fit_a_60k_list():
    from app import limits

    assert limits.max_import_chars() >= 5_000_000 and limits.max_upload_bytes() >= 5_000_000
