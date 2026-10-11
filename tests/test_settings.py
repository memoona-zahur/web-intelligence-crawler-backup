"""Settings: production contact rule, test contact only for local hosts, robots policy, database URL (CR-F02, F01, K03, H01)."""

import pytest

from app import settings
from app.settings import ContactPolicyError, SettingsError


def test_production_refuses_to_run_without_a_contact(monkeypatch):
    monkeypatch.setenv("CRAWLER_MODE", "production")
    monkeypatch.delenv("CRAWLER_CONTACT_URL", raising=False)
    with pytest.raises(SettingsError, match="CRAWLER_CONTACT_URL is required"):
        settings.user_agent()


@pytest.mark.parametrize("contact", ["test@example.invalid", "mailto:test@example.invalid", "https://example.com/bot", "https://crawler.example.test/x"])
def test_production_refuses_placeholder_contacts(monkeypatch, contact):
    monkeypatch.setenv("CRAWLER_MODE", "production")
    monkeypatch.setenv("CRAWLER_CONTACT_URL", contact)
    with pytest.raises(SettingsError, match="placeholder"):
        settings.user_agent()


def test_production_accepts_a_real_contact(monkeypatch):
    monkeypatch.setenv("CRAWLER_MODE", "production")
    monkeypatch.setenv("CRAWLER_CONTACT_URL", "https://www.acme-research.org/crawler")
    assert settings.user_agent() == "WebsiteIntelligenceBot/2.0 (+https://www.acme-research.org/crawler)"
    settings.check_contact_for_host("www.some-company.com")  # a real contact may go to any host


@pytest.mark.parametrize("mode", ["dev", "test"])
def test_dev_and_test_mode_default_to_the_marked_test_contact(monkeypatch, mode):
    monkeypatch.setenv("CRAWLER_MODE", mode)
    monkeypatch.delenv("CRAWLER_CONTACT_URL", raising=False)
    assert settings.user_agent() == "WebsiteIntelligenceBot/2.0 (+test@example.invalid)"


def test_unknown_mode_is_an_error(monkeypatch):
    monkeypatch.setenv("CRAWLER_MODE", "staging")
    with pytest.raises(SettingsError):
        settings.mode()


@pytest.mark.parametrize("host", ["example.com", "www.acme.com", "93.184.216.34", "crawl-eval-dead-1.invalid", "httpbin.org", None])
def test_test_contact_is_refused_for_every_non_local_host(monkeypatch, host):
    monkeypatch.setenv("CRAWLER_MODE", "dev")
    monkeypatch.delenv("CRAWLER_CONTACT_URL", raising=False)
    with pytest.raises(ContactPolicyError, match="placeholder"):
        settings.check_contact_for_host(host)


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "localhost", "site.localhost", "::1", "[::1]"])
def test_test_contact_is_allowed_for_local_hosts(monkeypatch, host):
    monkeypatch.setenv("CRAWLER_MODE", "test")
    monkeypatch.delenv("CRAWLER_CONTACT_URL", raising=False)
    settings.check_contact_for_host(host)


def test_explicit_placeholder_contact_is_refused_for_non_local_hosts_too(monkeypatch):
    monkeypatch.setenv("CRAWLER_MODE", "dev")
    monkeypatch.setenv("CRAWLER_CONTACT_URL", "https://example.com/crawler")
    with pytest.raises(ContactPolicyError):
        settings.check_contact_for_host("acme.com")


def test_robots_policy_default_is_rfc_strict_and_configurable(monkeypatch):
    monkeypatch.delenv("ROBOTS_5XX_POLICY", raising=False)
    assert settings.robots_5xx_policy() == "disallow"
    monkeypatch.setenv("ROBOTS_5XX_POLICY", "ALLOW")
    assert settings.robots_5xx_policy() == "allow"
    monkeypatch.setenv("ROBOTS_5XX_POLICY", "maybe")
    with pytest.raises(SettingsError):
        settings.robots_5xx_policy()


def test_database_url_defaults_to_sqlite_and_accepts_postgres(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert settings.database_url().startswith("sqlite:///")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/web")
    assert settings.database_url() == "postgresql+psycopg://u:p@localhost:5432/web"
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@localhost/web")
    assert settings.database_url().startswith("postgresql+psycopg://")


def test_raw_html_is_off_by_default(monkeypatch):
    monkeypatch.delenv("RAW_HTML_RETENTION_DAYS", raising=False)
    assert settings.raw_html_retention_days() == 0
    monkeypatch.setenv("RAW_HTML_RETENTION_DAYS", "30")
    assert settings.raw_html_retention_days() == 30
    monkeypatch.setenv("RAW_HTML_RETENTION_DAYS", "abc")
    assert settings.raw_html_retention_days() == 0


def test_limits_see_the_environment_and_default_to_a_60k_list(monkeypatch):
    from app import limits

    monkeypatch.delenv("MAX_IMPORT_CHARS", raising=False)
    assert limits.max_import_chars() >= 5_000_000  # ISS-17: a 60,000-line list is 2-3 MB
    monkeypatch.setenv("CRAWL_CONCURRENCY", "3")
    assert limits.crawl_concurrency() == 3
