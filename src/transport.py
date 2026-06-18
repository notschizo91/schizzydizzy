"""
Single outbound HTTP transport layer.

All callers (harvester, rank tracker) use make_client() instead of
constructing httpx.Client directly. Proxy, UA rotation, and throttle
live here so callers inherit them for free.

.env keys:
  PROXY_URL   — optional. e.g. http://user:pass@host:port
                Empty or absent = direct connection.

make_client() kwargs:
  sticky (bool, default False) — if True and PROXY_URL is set, pin the
      same proxy URL for the lifetime of the client (Decodo sticky
      sessions are handled at the URL level, so the caller should
      construct one client per keyword and close it when done).
      Rotating mode (default) builds a fresh transport per-request
      if the proxy rotates at the URL level, or just re-uses the same
      URL with Amazon's session randomness.
"""

import os
import random
import time
from contextlib import contextmanager

import httpx
from dotenv import load_dotenv

load_dotenv()

_PROXY_URL: str | None = os.getenv("PROXY_URL") or None

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

_BASE_HEADERS = {
    "Accept-Encoding": "gzip",
    "Accept-Language": "en-US,en;q=0.9",
}


def _random_ua() -> str:
    return random.choice(_USER_AGENTS)


def make_client(sticky: bool = False) -> httpx.Client:
    """
    Return a configured httpx.Client.

    sticky=False (default): rotating mode — UA is randomized per-client.
        Each request within the client shares one UA; callers that want
        per-request UA rotation should call make_client() again per request
        or use the throttled_get() helper.

    sticky=True: same proxy URL pinned for the client's lifetime. Use one
        client per keyword in the rank tracker.
    """
    proxy = _PROXY_URL if _PROXY_URL else None
    headers = {**_BASE_HEADERS, "User-Agent": _random_ua()}
    return httpx.Client(
        proxy=proxy,
        headers=headers,
        timeout=15,
        follow_redirects=True,
    )


@contextmanager
def client_session(sticky: bool = False):
    """Context manager that closes the client on exit."""
    client = make_client(sticky=sticky)
    try:
        yield client
    finally:
        client.close()


def throttled_get(
    client: httpx.Client,
    url: str,
    *,
    params: dict | None = None,
    extra_headers: dict | None = None,
    rotate_ua: bool = True,
    throttle: bool = True,
) -> httpx.Response:
    """
    GET with optional UA rotation and randomized 0.5–2s throttle.

    rotate_ua=True  — picks a fresh UA before each call (good for harvester).
    rotate_ua=False — keeps the client's UA stable (good for sticky rank tracker).
    throttle=False  — skip sleep (unit tests, one-shot calls).
    """
    if rotate_ua:
        client.headers["User-Agent"] = _random_ua()

    headers = {**(extra_headers or {})}
    resp = client.get(url, params=params, headers=headers)
    resp.raise_for_status()

    if throttle:
        time.sleep(random.uniform(0.5, 2.0))

    return resp


def proxy_configured() -> bool:
    return _PROXY_URL is not None
