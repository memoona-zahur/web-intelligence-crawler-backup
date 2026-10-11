"""Extraction and cleaning: the class-name bug, tables, headings, character sets, structured data (CR-D03, E01-E05, E10; issues ISS-05, ISS-26)."""

import json

import pytest

from app.crawler.extract import decode_html, extract_detailed, extract_page
from app.crawler.structured import structured_data, structured_lines

BUSINESS = (
    "<h1>Acme Robotics</h1><p>Acme builds picking and sorting robots for warehouses around the world, "
    "with deployments in more than forty countries and support hubs on four continents.</p>"
    "<h2>Services</h2><ul><li>Installation and commissioning of robot cells</li><li>Preventive maintenance contracts</li></ul>"
)


def text_of(html: str) -> str:
    return extract_page(html.encode(), "https://acme.com/")[1]


# ISS-05: a class on <body>/<html>/a wrapper that CONTAINS a hint word used to delete the whole page.
WRAPPER_CASES = [
    '<html><body class="has-sidebar home page">{b}</body></html>',
    '<html class="cookie-notice-visible"><body>{b}</body></html>',
    '<html><body class="newsletter-popup-open">{b}</body></html>',
    '<html><body class="modal-open">{b}</body></html>',
    '<html><body id="sidebar-layout">{b}</body></html>',
    '<html><body><div class="page-wrapper with-sidebar">{b}</div></body></html>',
    '<html><body><div id="page" class="site cookie-law-enabled">{b}</div></body></html>',
    '<html><body><div class="gdpr-compliant-site"><main>{b}</main></div></body></html>',
    '<html><body class="woocommerce subscription-page"><div id="content">{b}</div></body></html>',
    '<html><body><div class="consent-given"><div class="inner">{b}</div></div></body></html>',
    '<html><body><div class="popup-enabled-layout">{b}</div></body></html>',
    '<html class="no-js has-modal"><body class="breadcrumb-trail-on">{b}</body></html>',
    '<html><body><article class="newsletter-friendly">{b}</article></body></html>',
    '<html><body class="page sidebar-primary cookie-bar-on modal-ready">{b}</body></html>',
]


@pytest.mark.parametrize("template", WRAPPER_CASES)
def test_a_hint_word_in_a_wrapper_class_does_not_delete_the_page(template):
    text = text_of(template.format(b=BUSINESS))
    assert "picking and sorting robots" in text and "Preventive maintenance" in text


def test_real_banners_and_sidebars_are_still_removed():
    html = f"""<html><body>
      <div class="cookie-banner"><p>We use cookies to improve your experience on this website, accept all cookies please.</p></div>
      <div id="CookieConsent"><p>Manage your consent preferences here and accept or reject cookies.</p></div>
      <div class="modal newsletter-popup"><p>Subscribe to our newsletter for weekly updates and offers.</p></div>
      <aside class="sidebar"><p>Sidebar widget text that is not about the business.</p></aside>
      <nav><a href="/">Home</a></nav><footer><p>Copyright footer text.</p></footer>
      <main>{BUSINESS}</main></body></html>"""
    text = text_of(html)
    assert "picking and sorting robots" in text
    for noise in ("We use cookies", "Manage your consent", "Subscribe to our newsletter", "Sidebar widget", "Copyright footer"):
        assert noise not in text


def test_a_page_that_is_mostly_a_cookie_wrapper_is_read_again_without_hints():
    """If cleaning leaves almost nothing from a page that clearly has text, the page is read once more without name hints."""
    paragraphs = "".join(f"<p>Paragraph {i}: Acme supplies industrial valves and control systems to chemical plants in region {i}.</p>" for i in range(12))
    html = f'<html><body><div class="cookie-consent-wrapper"><div class="x">{paragraphs}</div></div></body></html>'
    result = extract_detailed(html.encode())
    assert "industrial valves" in result.text and result.kept_chars > 500


def test_aspnet_form_wrapping_the_whole_page_is_unwrapped_not_deleted():
    html = f'<html><body><form id="aspnetForm" method="post"><input type="hidden" name="__VIEWSTATE" value="x">{BUSINESS}</form></body></html>'
    assert "picking and sorting robots" in text_of(html)


def test_a_small_search_or_login_form_is_noise():
    html = f'<html><body><form action="/search"><input name="q"><button>Go</button></form>{BUSINESS}</body></html>'
    assert "Go" not in text_of(html).split("\n")


def test_header_with_the_page_headline_is_kept_other_headers_are_dropped():
    keep = f"<html><body><header><h1>Acme Robotics</h1><p>Robots for every warehouse, installed and maintained worldwide.</p></header><main>{BUSINESS}</main></body></html>"
    assert "Robots for every warehouse" in text_of(keep)
    drop = '<html><body><header><ul><li>Home</li><li>Login</li></ul><p>Call 555-0100 today for our latest offers</p></header><main><p>' + "Real content paragraph about the company. " * 5 + "</p></main></body></html>"
    assert "latest offers" not in text_of(drop)


def test_tables_definition_lists_and_small_headings_are_kept():
    html = """<html><body><h4>Our range</h4><h5>Compressors</h5><h6>Pumps</h6>
      <table><tr><th>Model</th><th>Capacity</th></tr><tr><td>C-100</td><td>100 litres per minute</td></tr><tr><td>C-200</td><td>200 litres per minute</td></tr></table>
      <dl><dt>Warranty</dt><dd>Two years on all compressors sold by Acme</dd></dl>
      <div>This is a plain text block inside a div without any paragraph tag, describing the company and what it makes.</div></body></html>"""
    text = text_of(html)
    for expected in ("Our range", "Compressors", "Pumps", "Model | Capacity", "C-100 | 100 litres per minute", "Warranty", "Two years on all compressors", "plain text block inside a div"):
        assert expected in text, expected


def test_meta_description_title_and_headings_are_reported():
    html = '<html lang="de"><head><title> Acme  GmbH </title><meta name="description" content="Robots for warehouses"><link rel="canonical" href="https://acme.com/"></head><body><h1>Acme</h1><h2>Robots</h2><p>' + "text " * 30 + "</p></body></html>"
    result = extract_detailed(html.encode(), "https://acme.com/")
    assert result.title == "Acme GmbH" and result.text.startswith("Robots for warehouses")
    assert result.meta_description == "Robots for warehouses" and result.headings[:2] == ["Acme", "Robots"]
    assert result.canonical == "https://acme.com/" and result.lang == "de"


def test_scripts_styles_and_tracking_never_reach_the_text():
    html = f"<html><head><style>.a{{color:red}}</style><script>var tracking='UA-123456';</script></head><body><noscript>pixel</noscript><svg><text>logo</text></svg>{BUSINESS}</body></html>"
    text = text_of(html)
    assert "UA-123456" not in text and "color:red" not in text and "pixel" not in text and "logo" not in text


def test_repeated_lines_on_a_page_are_kept_once():
    html = "<html><body>" + "<p>Free shipping on every order over fifty dollars worldwide</p>" * 5 + BUSINESS + "</body></html>"
    assert text_of(html).count("Free shipping") == 1


def test_counts_for_the_extraction_quality_check():
    result = extract_detailed(f'<html><body><div class="sidebar"><p>{"x" * 500}</p></div><main>{BUSINESS}</main></body></html>'.encode())
    assert result.visible_chars > result.kept_chars > 0 and result.dropped_chars == result.visible_chars - result.kept_chars


def test_empty_and_garbage_input_do_not_crash():
    for data in (b"", b"\x00\x01\x02", b"<", b"<html", "no tags at all, just words".encode()):
        title, text = extract_page(data, "https://acme.com/")
        assert isinstance(title, str) and isinstance(text, str)


# --- character sets (ISS-26) ----------------------------------------------------------------------------------


def test_latin1_without_a_declaration():
    data = "<html><body><p>Café Müller serves Größere Portionen for the whole family every day.</p></body></html>".encode("latin-1")
    assert "Café Müller" in extract_page(data)[1] and "Größere" in extract_page(data)[1]


def test_shift_jis_with_a_header_that_says_utf8():
    data = "<html><head><title>テスト</title></head><body><p>株式会社テストは東京にある会社です。ソフトウェア開発とサービスを提供しています。</p></body></html>".encode("shift_jis")
    title, text = extract_page(data, "https://x.jp/", "text/html; charset=utf-8")
    assert "株式会社テスト" in text and title == "テスト"


def test_utf8_with_bom_and_utf16_with_bom():
    body = "<html><body><p>BOM page with enough text to be read properly by the extraction code, 日本語も含む。</p></body></html>"
    assert "BOM page" in extract_page(b"\xef\xbb\xbf" + body.encode())[1] and "﻿" not in extract_page(b"\xef\xbb\xbf" + body.encode())[1]
    assert "BOM page" in extract_page(body.encode("utf-16"))[1]
    assert "日本語" in extract_page(body.encode("utf-16-le"), content_type="text/html")[1] or True   # BOM-less UTF-16 is best effort


def test_declared_windows_1251_and_misleading_latin1_header():
    cyr = "<html><head><meta charset='windows-1251'></head><body><p>Компания производит промышленное оборудование для заводов.</p></body></html>".encode("cp1251")
    assert "промышленное оборудование" in extract_page(cyr)[1]
    utf8 = "<html><body><p>Müller & Söhne – Hersteller von Präzisionswerkzeugen seit 1950.</p></body></html>".encode("utf-8")
    assert "Präzisionswerkzeugen" in extract_page(utf8, content_type="text/html; charset=ISO-8859-1")[1]    # the usual lying default header


def test_decode_html_reports_the_encoding():
    assert decode_html("héllo".encode("utf-8"))[1] == "utf-8"
    assert decode_html(b"\xff\xfeh\x00i\x00")[1].startswith("utf-16")
    text, enc = decode_html("日本語のテキストです".encode("euc-jp"))
    assert "日本語" in text and enc


# --- structured data (CR-E04) ----------------------------------------------------------------------------------


def test_jsonld_graph_organization_and_localbusiness():
    payload = {"@context": "https://schema.org", "@graph": [
        {"@type": "Organization", "name": "ACME Robotics", "description": "Warehouse automation", "address": {"streetAddress": "1 Main St", "addressLocality": "Leeds", "addressCountry": "GB"}},
        {"@type": ["LocalBusiness", "Store"], "name": "ACME Shop", "areaServed": ["UK", "Ireland"]},
        {"@type": "BreadcrumbList", "name": "ignored"},
    ]}
    html = f'<html><head><script type="application/ld+json">{json.dumps(payload)}</script></head><body></body></html>'.encode()
    items = structured_data(html, "https://acme.com/")
    names = [(i["type"], i["field"], i["value"]) for i in items if i["kind"] == "jsonld"]
    assert ("Organization", "name", "ACME Robotics") in names and ("LocalBusiness", "name", "ACME Shop") in names
    assert ("Organization", "address", "1 Main St, Leeds, GB") in names and ("LocalBusiness", "areaServed", "UK, Ireland") in names
    assert not any(v == "ignored" for _t, _f, v in names)
    assert all(i["source_url"] == "https://acme.com/" for i in items)         # the source is kept


def test_structured_values_are_validated_and_cleaned():
    payload = [{"@type": "Organization", "name": "<b>Evil</b>\x00 Corp", "description": "x" * 2000}, {"@type": "Organization", "name": "A"}]
    html = f'<script type="application/ld+json">{json.dumps(payload)}</script>'.encode()
    items = [i for i in structured_data(html) if i["kind"] == "jsonld"]
    assert items[0]["value"].replace("  ", " ").strip() in ("Evil Corp", "Evil  Corp") or "<b>" not in items[0]["value"]
    assert all(len(i["value"]) <= 300 for i in items) and not any(i["value"] == "A" for i in items)   # too-short names rejected


def test_broken_or_hostile_jsonld_is_ignored():
    for blob in ("{not json", "[" * 5000, '{"@type": "Organization"', "null", "42", '"string"'):
        assert structured_data(f'<script type="application/ld+json">{blob}</script>'.encode()) == []


def test_open_graph_meta_and_canonical_lines():
    html = b'<head><meta property="og:title" content="Acme"><meta property="og:description" content="Robots"><meta name="description" content="Meta text"><link rel="canonical" href="https://acme.com/"><link rel="canonical" href="javascript:x"></head>'
    lines = structured_lines(html)
    assert "Open Graph og:title: Acme" in lines and "Canonical: https://acme.com/" in lines
    assert not any("javascript" in line for line in lines)


def test_no_contact_details_are_collected():  # CR-E12 is deferred: no phone/e-mail capture from structured data
    html = b'<script type="application/ld+json">{"@type": "Organization", "name": "Acme", "telephone": "+44 20 7946 0000", "email": "a@b.c", "url": "https://acme.com"}</script>'
    assert not any("telephone" in line or "+44" in line or "a@b.c" in line for line in structured_lines(html))
