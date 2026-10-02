"""E2E pipeline: SearchProvider (DDG) -> Crawl4AI primary, Playwright fallback.

Mirrors production: search returns URLs, fetch the top 3, prefer Crawl4AI,
escalate to Playwright if Crawl4AI returns < 200 chars (extraction failed
or JS-only page).
"""
from __future__ import annotations
import asyncio, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _fixtures import Probe, SEARCH_QUERIES, timed, keyword_score, save_results
from search_provider import build_provider
from test_crawl4ai import probe_crawl4ai
from test_playwright import probe_playwright

N_TOP = 3
ESCALATE_MIN_CHARS = 200


def run_pipeline(query: str, keywords: list, targets: list, case_id: str, provider_name: str = "duckduckgo") -> Probe:
    p = Probe(tool=f"pipeline({provider_name}->crawl4ai|playwright)", case_id=case_id)
    import time
    time.sleep(2.5)  # avoid DDG anti-bot hammering across cases

    # search fallback chain: DDG → SearXNG → Brave
    provider_used = None
    hits = []
    for prov in ["duckduckgo", "searxng", "brave"]:
        try:
            provider = build_provider(prov)
            h = provider.search(query, top_n=N_TOP + 2)
            if h:
                hits = h
                provider_used = prov
                break
        except Exception as e:
            continue
    if not hits:
        p.error = "search: all providers failed"
        return p
    if not hits:
        p.error = "no hits"
        return p
    p.n_results = len(hits)
    p.target_domain_hit = any(t in h.url for h in hits for t in targets) if targets else True

    best = (0, len(keywords))
    best_chars = 0
    primary_ok = 0
    escalated = 0
    for hit in hits[:N_TOP]:
        c = probe_crawl4ai(hit.url, keywords, case_id)
        if c.ok and c.chars_md >= ESCALATE_MIN_CHARS:
            primary_ok += 1
            if c.keyword_hits > best[0]:
                best = (c.keyword_hits, c.keyword_total)
                best_chars = c.chars_md
        else:
            escalated += 1
            w = probe_playwright(hit.url, keywords, case_id)
            if w.ok and w.keyword_hits > best[0]:
                best = (w.keyword_hits, w.keyword_total)
                best_chars = w.chars_md
    p.ok = primary_ok + escalated > 0
    p.keyword_hits = best[0]
    p.keyword_total = best[1]
    p.chars_md = best_chars
    p.raw = {"primary_ok": primary_ok, "escalated": escalated, "provider": provider_used}
    return p


def main():
    out = Path(__file__).parent.parent / "results" / "pipeline.json"
    results = []
    for cid, q, kws, targets in SEARCH_QUERIES:
        print(f"  [{cid}] {q[:40]:<40} ", end="", flush=True)
        probe = timed(lambda: run_pipeline(q, kws, targets, cid))
        results.append(probe)
        print(f"ok={probe.ok}  lat={probe.latency_ms:6.0f}ms  kw={probe.keyword_hits}/{probe.keyword_total}  primary={probe.raw.get('primary_ok', 0)}  esc={probe.raw.get('escalated', 0)}")
        if probe.error:
            print(f"        err: {probe.error[:100]}")
    save_results(results, str(out))
    return results


if __name__ == "__main__":
    main()
