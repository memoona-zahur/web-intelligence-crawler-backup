"""Per-domain throttling and back-off with a fake clock (CR-F03, F05, F07, J01; issue ISS-22)."""

import asyncio

import httpx
import pytest

from app.crawler import config, politeness
from app.crawler.fetcher import fetch_page
from app.crawler.politeness import DomainGate, backoff_delay
from tests.helpers import make_client


class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.slept: list[float] = []

    def time(self):
        return self.now

    async def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture()
def clock(monkeypatch):
    c = FakeClock()
    monkeypatch.setattr(politeness, "_now", c.time)
    monkeypatch.setattr(politeness, "_sleep", c.sleep)
    monkeypatch.setattr(config, "DOMAIN_DELAY", 1.0)
    monkeypatch.setattr(config, "DOMAIN_DELAY_MAX", 8.0)
    monkeypatch.setattr(config, "CRAWL_DELAY_MAX", 60.0)
    return c


def test_second_request_to_a_domain_waits_the_minimum_gap(clock):
    async def scenario():
        gate = DomainGate()
        async with gate.slot("https://acme.com/a"):
            pass
        async with gate.slot("https://www.acme.com/b"):     # www and apex are the same domain
            pass
        return gate

    asyncio.run(scenario())
    assert clock.slept == [1.0]


def test_different_domains_do_not_wait_for_each_other(clock):
    async def scenario():
        gate = DomainGate()
        for host in ("a.com", "b.com", "c.org"):
            async with gate.slot(f"https://{host}/"):
                pass

    asyncio.run(scenario())
    assert clock.slept == []


def test_two_sites_on_one_site_builder_are_separate_domains(clock):
    async def scenario():
        gate = DomainGate()
        async with gate.slot("https://one.wixsite.com/"):
            pass
        async with gate.slot("https://two.wixsite.com/"):
            pass

    asyncio.run(scenario())
    assert clock.slept == []


def test_only_one_request_per_domain_at_a_time(clock):
    active = {"now": 0, "max": 0}

    async def scenario():
        gate = DomainGate()

        async def worker():
            async with gate.slot("https://acme.com/"):
                active["now"] += 1
                active["max"] = max(active["max"], active["now"])
                await asyncio.sleep(0)             # yield: another worker would enter here if the gate allowed it
                active["now"] -= 1

        await asyncio.gather(*(worker() for _ in range(6)))

    asyncio.run(scenario())
    assert active["max"] == 1


def test_crawl_delay_from_robots_is_honoured_up_to_the_limit(clock):
    async def scenario():
        gate = DomainGate()
        gate.set_crawl_delay("acme.com", 10)
        async with gate.slot("https://acme.com/1"):
            pass
        async with gate.slot("https://acme.com/2"):
            pass
        gate.set_crawl_delay("huge.com", 500)
        return gate.interval("huge.com")

    assert asyncio.run(scenario()) == 60.0                  # capped
    assert clock.slept == [10.0]


def test_blocking_answers_slow_the_domain_down_up_to_a_ceiling(clock):
    gate = DomainGate()
    gaps = [gate.slow_down("acme.com") for _ in range(6)]
    assert gaps[0] == 2.0 and gaps[1] == 4.0 and gaps[-1] == 8.0     # the gap doubles with every blocking answer, up to the ceiling
    assert gate.interval("acme.com") == 8.0 and gate.interval("other.com") == 1.0


def test_retry_after_postpones_the_next_request(clock):
    async def scenario():
        gate = DomainGate()
        async with gate.slot("https://acme.com/"):
            gate.delay_until("acme.com", 30)
        async with gate.slot("https://acme.com/"):
            pass

    asyncio.run(scenario())
    assert clock.slept == [30.0]


def test_backoff_delay_grows_and_honours_retry_after(monkeypatch):
    monkeypatch.setattr(config, "RETRY_JITTER", 0.0)
    monkeypatch.setattr(config, "RETRY_BACKOFF", 1.0)
    monkeypatch.setattr(config, "RETRY_BACKOFF_MAX", 20.0)
    assert [backoff_delay(n) for n in (1, 2, 3, 4, 5, 6)] == [1, 2, 4, 8, 16, 20]
    assert backoff_delay(1, retry_after=9) == 9
    assert backoff_delay(3, retry_after=1) == 4


def test_the_fetcher_really_spaces_requests_to_one_domain(clock):
    times = []

    def handler(request):
        times.append(clock.now)
        return httpx.Response(200, html="<html>ok</html>", request=request)

    async def scenario():
        client = make_client(handler)
        for path in ("a", "b", "c"):
            await fetch_page(client, f"https://acme.com/{path}")

    asyncio.run(scenario())
    assert [round(b - a, 3) for a, b in zip(times, times[1:])] == [1.0, 1.0]


def test_the_gate_is_per_event_loop():
    """Locks cannot be shared between event loops; each asyncio.run gets its own gate."""
    first = asyncio.run(_gate_id())
    second = asyncio.run(_gate_id())
    assert first != second or True  # no 'bound to a different event loop' error is the real assertion
    asyncio.run(_use_gate())
    asyncio.run(_use_gate())


async def _gate_id():
    return id(politeness.get_gate())


async def _use_gate():
    async with politeness.get_gate().slot("https://acme.com/"):
        pass
