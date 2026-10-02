"""Common HTTP client with proxy + timeout handling."""
from __future__ import annotations
import os, httpx

PROXY = os.environ.get("WEBBENCH_PROXY")  # e.g. http://127.0.0.1:7897
TIMEOUT = httpx.Timeout(15.0, connect=8.0)

# Per-tool headers — some servers reject generic UA
UA_CHROME = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


def make_client(proxy: str | None = PROXY, headers: dict | None = None, timeout: float = 15.0) -> httpx.Client:
    kw = dict(
        timeout=httpx.Timeout(timeout, connect=8.0),
        follow_redirects=True,
        headers={"User-Agent": UA_CHROME, "Accept-Language": "en-US,en;q=0.9,zh;q=0.8", **(headers or {})},
    )
    if proxy:
        kw["proxy"] = proxy   # httpx ≥0.28 uses 'proxy' (singular)
    return httpx.Client(**kw)


def with_timing(client: httpx.Client, method: str, url: str, **kw):
    """Issue a request, return (response, ttfb_ms, total_ms)."""
    import time
    t0 = time.perf_counter()
    resp = client.request(method, url, **kw)
    ttfb = (time.perf_counter() - t0) * 1000  # best-effort; httpx doesn't expose TTFB pre-body
    return resp, ttfb, ttfb
