"""Webtool — configurable web search + fetch CLI.

Defaults are the values that won the N×k factorial benchmark:
  search_top = 10        (DDG HTML max practical)
  rerank_k   = 6         (sweet spot — score 0.87)
  rerank     = "cross"   (cross-encoder/ms-marco-MiniLM-L-6-v2, +0.01 over lexical)
  fetch      = "crawl4ai" (Apache-2.0, 7/7 in earlier probe)

Usage:
  python -m webtool "your query here"
  python -m webtool "q" --search-top 20 --rerank-k 10 --rerank lexical --fetch playwright
"""
from __future__ import annotations
import argparse, asyncio, json, math, os, re, sys, time, warnings
warnings.filterwarnings("ignore")
from dataclasses import dataclass, field, asdict
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional


# Defaults from the benchmark
DEFAULTS = {
    "search_top": 10,
    "rerank_k": 6,
    "rerank": "cross",        # "lexical" | "cross"
    "fetch": "crawl4ai",      # "crawl4ai" | "playwright" | "plain"
    "search_backend": "duckduckgo",  # "duckduckgo" | "searxng" | "brave"
    # 代理不再硬编码：由环境变量 WEBTOOL_PROXY（兼容 WEBBENCH_PROXY）提供，未设置则直连
    "proxy": os.environ.get("WEBTOOL_PROXY") or os.environ.get("WEBBENCH_PROXY") or None,
    "model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    "keep_content": False,    # True 时 pages[i]["content"] 带上抓取到的 markdown 正文
}


STOP = set("""a an and are as at be by for from has have he her his in is it its of on or
              that the to was were will with i you your we our they them this those
              not no but if so do does did doing than then there here what when where
              which who whom how why all any some most more less very can could should would
              about above after again against all also among because before below between""".split())


@dataclass
class WebResult:
    query: str
    search_backend: str
    search_top: int
    rerank_method: str
    rerank_k: int
    fetch_engine: str
    search_total: int = 0
    rerank_ms: float = 0.0
    latency_ms: float = 0.0
    pages: list = field(default_factory=list)   # list of {url, domain, title, snippet, chars, kw_hits}
    error: str = ""

    # Aggregates (computed in finish())
    distinct_doms: int = 0
    top_dom_share: float = 0.0
    host_diversity: float = 0.0   # Shannon, normalized
    kw_hits: int = 0
    kw_total: int = 0
    kw_coverage: float = 0.0
    total_chars: int = 0

    def finish(self):
        if not self.pages:
            return
        domain_counts = {}
        for p in self.pages:
            domain_counts[p["domain"]] = domain_counts.get(p["domain"], 0) + 1
        self.distinct_doms = len(domain_counts)
        self.top_dom_share = max(domain_counts.values()) / sum(domain_counts.values())
        # Shannon
        n = self.distinct_doms
        total = sum(domain_counts.values())
        if n > 1:
            h = -sum((c/total) * math.log(c/total) for c in domain_counts.values() if c > 0)
            self.host_diversity = h / math.log(n)
        self.kw_hits = sum(p["kw_hits"] for p in self.pages)
        self.kw_total = sum(p["kw_total"] for p in self.pages)
        self.kw_coverage = min(self.kw_hits, 0)  # set by caller
        self.total_chars = sum(p["chars"] for p in self.pages)


# ---------- tokenize & rerank ----------

def tokenize(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", (s or "").lower()) if w not in STOP and len(w) > 2}


class Reranker:
    """Lazy-loaded rerankers."""

    _CE = None

    @classmethod
    def lexical(cls, query: str, hits: list, top_k: int) -> tuple[list, float]:
        q = tokenize(query)
        if not q:
            return hits[:top_k], 0.0
        t0 = time.perf_counter()
        scored = []
        for h in hits:
            d = tokenize((h.title or "") + " " + (h.snippet or ""))
            if not d:
                scored.append((0.0, id(h), h))
                continue
            scored.append((len(q & d) / len(q | d), id(h), h))
        scored.sort(key=lambda x: (-x[0], x[1]))
        elapsed = (time.perf_counter() - t0) * 1000
        return [h for _, _, h in scored[:top_k]], elapsed

    @classmethod
    def cross(cls, query: str, hits: list, top_k: int, model: str) -> tuple[list, float]:
        if cls._CE is None:
            from sentence_transformers import CrossEncoder
            cls._CE = CrossEncoder(model)
        pairs = [(query, (h.title or "") + " " + (h.snippet or "")) for h in hits]
        t0 = time.perf_counter()
        scores = cls._CE.predict(pairs)
        indexed = sorted(enumerate(scores), key=lambda x: -x[1])
        elapsed = (time.perf_counter() - t0) * 1000
        return [hits[i] for i, _ in indexed[:top_k]], elapsed


# ---------- fetch ----------

async def _fetch_crawl4ai(url: str) -> tuple[bool, str]:
    from crawl4ai import AsyncWebCrawler
    async with AsyncWebCrawler(verbose=False) as c:
        r = await c.arun(url=url)
        return (r.success, r.markdown or "")


async def _fetch_playwright(url: str, timeout_ms: int = 20000) -> tuple[bool, str]:
    from playwright.async_api import async_playwright
    from markdownify import markdownify as md
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = await browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_timeout(800)
            html = await page.content()
        finally:
            await ctx.close()
            await browser.close()
    return True, md(html, strip=["script", "style", "noscript", "nav", "footer", "aside"], heading_style="ATX")


async def _fetch_plain(url: str) -> tuple[bool, str]:
    import httpx, trafilatura
    UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    proxy = DEFAULTS["proxy"]  # 可能为 None（直连）
    kw = dict(timeout=12, follow_redirects=True, proxy=proxy,
              headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9,zh;q=0.8"})
    async with httpx.AsyncClient(**kw) as c:
        r = await c.get(url)
    if r.status_code != 200:
        return False, ""
    md = trafilatura.extract(r.text, include_comments=False, include_tables=True, output_format="markdown") or ""
    return bool(md), md


def fetch_page(url: str, engine: str) -> tuple[bool, str]:
    if engine == "crawl4ai":
        return asyncio.run(_fetch_crawl4ai(url))
    if engine == "playwright":
        return asyncio.run(_fetch_playwright(url))
    if engine == "plain":
        return asyncio.run(_fetch_plain(url))
    raise ValueError(f"unknown fetch engine: {engine}")


# ---------- main pipeline ----------

def run(query: str, keywords: Optional[list] = None, **overrides) -> WebResult:
    cfg = {**DEFAULTS, **overrides}
    result = WebResult(
        query=query,
        search_backend=cfg["search_backend"],
        search_top=cfg["search_top"],
        rerank_method=cfg["rerank"],
        rerank_k=cfg["rerank_k"],
        fetch_engine=cfg["fetch"],
    )
    t0 = time.perf_counter()

    # 1. search
    from .search_provider import build_provider
    provider = build_provider(cfg["search_backend"])
    try:
        hits = provider.search(query, top_n=cfg["search_top"])
    except Exception as e:
        result.error = f"search: {e}"
        result.latency_ms = (time.perf_counter() - t0) * 1000
        return result
    result.search_total = len(hits)
    if not hits:
        result.error = "no hits"
        result.latency_ms = (time.perf_counter() - t0) * 1000
        return result

    # 2. rerank
    if cfg["rerank"] == "lexical":
        chosen, result.rerank_ms = Reranker.lexical(query, hits, cfg["rerank_k"])
    elif cfg["rerank"] == "cross":
        chosen, result.rerank_ms = Reranker.cross(query, hits, cfg["rerank_k"], cfg["model"])
    else:
        raise ValueError(f"unknown rerank: {cfg['rerank']}")

    # 3. fetch each
    if keywords is None:
        keywords = tokenize(query)  # fallback: use query tokens as expected kws
    for h in chosen:
        ok, md = fetch_page(h.url, cfg["fetch"])
        if not ok or len(md) < 200:  # skip empty/placeholder responses
            continue
        text_low = (md or "").lower()
        kw_hits = sum(1 for k in keywords if k.lower() in text_low)
        result.pages.append({
            "url": h.url,
            "domain": urlparse(h.url).netloc,
            "title": h.title,
            "snippet": h.snippet,
            "chars": len(md),
            "kw_hits": kw_hits,
            "kw_total": len(keywords),
            **({"content": md} if cfg["keep_content"] else {}),
        })

    result.finish()
    if keywords:
        result.kw_coverage = min(result.kw_hits, len(keywords)) / max(1, len(keywords))
    result.latency_ms = (time.perf_counter() - t0) * 1000
    return result


def to_dict(r: WebResult) -> dict:
    d = asdict(r)
    return d
