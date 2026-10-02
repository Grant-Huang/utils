"""Shared fixtures: queries, URLs, scoring helpers."""
from __future__ import annotations
import re, time, json, statistics, os
from dataclasses import dataclass, field, asdict
from typing import Callable
import httpx

# Fetch URLs — covers static / dynamic / SPA / heavy / anti-bot
FETCH_URLS = [
    # (id, url, expected_keywords, expect_min_chars)
    ("F1", "https://lilianweng.github.io/posts/2023-06-23-agent/", ["agent", "LLM", "reasoning"], 8000),
    ("F2", "https://docs.python.org/3/library/asyncio-task.html", ["asyncio", "task", "cancel"], 5000),
    ("F3", "https://news.ycombinator.com/", ["Hacker News", "ycombinator"], 1500),
    ("F4", "https://www.baidu.com/", ["百度"], 500),
    ("F5", "https://en.wikipedia.org/wiki/Large_language_model", ["language model", "transformer"], 5000),
    ("F6", "https://vercel.com/docs", ["Vercel", "deploy"], 1000),       # SPA — JS 渲染
    ("F7", "https://github.com/unclecode/crawl4ai", ["crawl4ai", "scrape"], 1000),  # SPA-ish
]

# Search queries for SearchProvider adapter
SEARCH_QUERIES = [
    ("Q1", "OpenAI news this week September 2026", ["openai"], ["openai.com"]),
    ("Q2", "Python asyncio task cancellation documentation", ["asyncio", "cancel"], ["docs.python.org"]),
    ("Q3", "武汉 天气 2026年10月", ["武汉", "天气"], []),
    ("Q4", "Hermes Agent desktop runtime debugpy pdb", ["hermes", "debugpy"], ["github.com"]),
    ("Q5", "LLM agent survey arxiv 2026", ["survey", "agent"], ["arxiv.org"]),
]


@dataclass
class Probe:
    tool: str
    case_id: str
    ok: bool = False
    error: str = ""
    latency_ms: float = 0.0
    chars_md: int = 0
    keyword_hits: int = 0
    keyword_total: int = 0
    n_results: int = 0
    target_domain_hit: bool = False
    bytes_out: int = 0
    raw: dict = field(default_factory=dict)

    def quality(self) -> float:
        if not self.ok:
            return 0.0
        if self.keyword_total == 0:
            return 1.0
        return min(1.0, self.keyword_hits / self.keyword_total)


def timed(fn: Callable[[], Probe]) -> Probe:
    t0 = time.perf_counter()
    p = fn()
    p.latency_ms = (time.perf_counter() - t0) * 1000
    return p


def keyword_score(text: str, kws: list[str]) -> tuple[int, int]:
    if not text or not kws:
        return (0, len(kws))
    low = text.lower()
    hits = sum(1 for k in kws if k.lower() in low)
    return (hits, len(kws))


def domain_hit(urls: list[str], targets: list[str]) -> bool:
    if not targets:
        return True
    for u in urls:
        for t in targets:
            if t in u:
                return True
    return False


def percentile(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    k = (len(s) - 1) * p
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def save_results(results: list[Probe], path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2, default=str)


def load_results(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)
