"""The one place that builds the HTTP client used for crawling.

- no cookies are kept (CR-F08);
- every request passes the contact policy: a placeholder contact (such as the test contact) is never sent to a non-local host.
"""

from __future__ import annotations

from http.cookiejar import DefaultCookiePolicy

import httpx

import app.settings as settings


async def _contact_policy_hook(request: httpx.Request) -> None:
    settings.check_contact_for_host(request.url.host)


def new_client(transport: httpx.AsyncBaseTransport | None = None, **kwargs) -> httpx.AsyncClient:
    """AsyncClient for crawling. `transport` lets tests inject a mock transport; the policy hook still runs."""
    hooks = {"request": [_contact_policy_hook]}
    kwargs.setdefault("limits", httpx.Limits(max_connections=60, max_keepalive_connections=20))
    client = httpx.AsyncClient(transport=transport, event_hooks=hooks, **kwargs)
    client.cookies.jar.set_policy(DefaultCookiePolicy(allowed_domains=[]))  # accept no cookies at all
    return client
