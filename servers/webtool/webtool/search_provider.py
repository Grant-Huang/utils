"""SearchProvider 适配层 — 抽象后端接口，3 个内置实现。

设计动机：商用项目需要把 search 后端抽象掉，方便替换 / 灰度 / 多路聚合。
后端实现：
- DuckDuckGoHTMLProvider   — 免费，无 key，但反爬敏感
- SearXNGProvider          — AGPL-3.0 (⚠️ 自托管可商用注意义务)，需自部署
- BraveSearchProvider      — 商业 API (本测试无 key 仅占位)

未来可以加 Google CSE / Bing / Tavily / 自建 OpenSearch 等。
"""
from __future__ import annotations
import abc, json, re, sys, os, time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

PROXY = os.environ.get("WEBTOOL_PROXY") or os.environ.get("WEBBENCH_PROXY") or None  # 不再硬编码；未设置则直连
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

DEFAULT_TIMEOUT = 8.0


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str = ""

    def to_dict(self) -> dict:
        return {"title": self.title, "url": self.url, "snippet": self.snippet}


class SearchProvider(abc.ABC):
    """通用 search 后端接口。所有实现返回 SearchHit 列表，调用方零感知。"""
    name: str = "abstract"
    license: str = "—"

    @abc.abstractmethod
    def search(self, query: str, top_n: int = 10, language: str = "auto") -> list[SearchHit]:
        ...


class DuckDuckGoHTMLProvider(SearchProvider):
    """DuckDuckGo HTML 接口。无 key；bot 检测敏感。"""
    name = "duckduckgo-html"
    license = "DuckDuckGo ToS (no public OSS license)"

    def __init__(self, proxy: Optional[str] = PROXY):
        self.proxy = proxy

    def search(self, query, top_n=10, language="auto"):
        kw = dict(
            timeout=httpx.Timeout(DEFAULT_TIMEOUT, connect=8.0),
            follow_redirects=True,
            proxy=self.proxy,
            headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,zh;q=0.8",
                "Origin": "https://html.duckduckgo.com",
                "Referer": "https://html.duckduckgo.com/",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "navigate",
            },
        )
        with httpx.Client(**kw) as client:
            client.get("https://html.duckduckgo.com/")  # warm
            r = client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query, "kl": "us-en" if language == "en" else "wt-wt"},
            )
            if r.status_code != 200:
                raise RuntimeError(f"DDG HTTP {r.status_code}")
            return _parse_ddg_html(r.text, top_n)


def _parse_ddg_html(html: str, top_n: int) -> list[SearchHit]:
    out = []
    # DDG HTML result blocks
    for m in re.finditer(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        html, re.S,
    ):
        url, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        out.append(SearchHit(title=title, url=url))
        if len(out) >= top_n:
            break
    return out


class SearXNGProvider(SearchProvider):
    """SearXNG 自托管实例。⚠️ SearXNG 是 AGPL-3.0；自托管可商用但需保留源码 / 注明修改。"""
    name = "searxng"
    license = "AGPL-3.0 (⚠️ commercial obligation)"

    def __init__(self, base_url: str = "http://localhost:8888", proxy: Optional[str] = PROXY):
        self.base_url = base_url.rstrip("/")
        self.proxy = proxy

    def search(self, query, top_n=10, language="auto"):
        kw = dict(
            timeout=httpx.Timeout(DEFAULT_TIMEOUT, connect=8.0),
            follow_redirects=True,
            proxy=self.proxy,
            headers={"User-Agent": UA, "Accept": "application/json"},
        )
        with httpx.Client(**kw) as client:
            r = client.get(
                f"{self.base_url}/search",
                params={"q": query, "format": "json", "language": language, "safesearch": 0},
            )
            if r.status_code != 200:
                raise RuntimeError(f"SearXNG HTTP {r.status_code}")
            data = r.json()
            results = data.get("results", [])[:top_n]
            return [
                SearchHit(title=h.get("title", ""), url=h.get("url", ""), snippet=h.get("content", ""))
                for h in results
            ]


class BraveSearchProvider(SearchProvider):
    """Brave Search API。需 BRAVE_API_KEY；5000 req/月免费层，超出 $3/1000 req。"""
    name = "brave-api"
    license = "Brave ToS (proprietary)"

    def __init__(self, api_key: Optional[str] = None, proxy: Optional[str] = PROXY):
        self.api_key = api_key or os.environ.get("BRAVE_API_KEY", "")
        self.proxy = proxy

    def search(self, query, top_n=10, language="auto"):
        if not self.api_key:
            raise RuntimeError("BRAVE_API_KEY not set")
        kw = dict(
            timeout=httpx.Timeout(DEFAULT_TIMEOUT, connect=8.0),
            follow_redirects=True,
            proxy=self.proxy,
            headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
        )
        with httpx.Client(**kw) as client:
            r = client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": top_n},
            )
            if r.status_code != 200:
                raise RuntimeError(f"Brave HTTP {r.status_code}")
            data = r.json()
            results = (data.get("web") or {}).get("results", [])[:top_n]
            return [
                SearchHit(title=h.get("title", ""), url=h.get("url", ""), snippet=h.get("description", ""))
                for h in results
            ]


def build_provider(name: str, **kw) -> SearchProvider:
    """Factory — by name."""
    if name == "duckduckgo":
        return DuckDuckGoHTMLProvider(**kw)
    if name == "searxng":
        return SearXNGProvider(**kw)
    if name == "brave":
        return BraveSearchProvider(**kw)
    raise ValueError(f"unknown provider: {name}")


if __name__ == "__main__":
    # smoke test
    p = DuckDuckGoHTMLProvider()
    hits = p.search("python asyncio", top_n=3)
    for h in hits:
        print(h.title[:60], "->", h.url[:60])
