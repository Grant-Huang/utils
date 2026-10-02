"""Crawl4AI single-page fetch probe (Apache-2.0).

Uses real crawl4ai AsyncWebCrawler with Playwright Chromium.
Returns clean Markdown + extracted metadata.
"""
from __future__ import annotations
import asyncio, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _fixtures import Probe, FETCH_URLS, timed, keyword_score, save_results


async def _crawl_one(url: str) -> tuple[bool, str]:
    from crawl4ai import AsyncWebCrawler
    async with AsyncWebCrawler(verbose=False) as c:
        r = await c.arun(url=url)
        if not r.success:
            return False, ""
        return True, (r.markdown or "")


def probe_crawl4ai(url: str, keywords: list[str], case_id: str) -> Probe:
    p = Probe(tool="crawl4ai", case_id=case_id)
    try:
        ok, md = asyncio.run(_crawl_one(url))
    except Exception as e:
        p.error = f"{type(e).__name__}: {str(e)[:120]}"
        return p
    if not ok:
        p.error = "crawl4ai returned success=False"
        return p
    p.ok = True
    hits, total = keyword_score(md, keywords)
    p.keyword_hits = hits
    p.keyword_total = total
    p.chars_md = len(md)
    p.bytes_out = len(md.encode())
    p.raw = {"url": url, "text_sample": md[:200], "md_len": len(md)}
    return p


def main():
    out = Path(__file__).parent.parent / "results" / "crawl4ai.json"
    results = []
    for cid, url, kws, _ in FETCH_URLS:
        print(f"  [{cid}] {url[:50]:<50} ", end="", flush=True)
        probe = timed(lambda: probe_crawl4ai(url, kws, cid))
        results.append(probe)
        print(f"ok={probe.ok}  lat={probe.latency_ms:6.0f}ms  chars={probe.chars_md:6d}  kw={probe.keyword_hits}/{probe.keyword_total}")
        if probe.error:
            print(f"        err: {probe.error[:100]}")
    save_results(results, str(out))
    return results


if __name__ == "__main__":
    main()
