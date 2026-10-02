"""Playwright single-page fetch probe (Apache-2.0).

Uses Chromium headless to fully render JS-heavy pages, then extracts
visible text and converts to Markdown-lite format.

For complex pages, Playwright is the fallback when Crawl4AI's
extraction misses something or hits anti-bot measures.
"""
from __future__ import annotations
import asyncio, sys, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _fixtures import Probe, FETCH_URLS, timed, keyword_score, save_results
from markdownify import markdownify as md


async def _render(url: str, timeout_ms: int = 20000) -> tuple[bool, str]:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = await browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_timeout(800)  # let JS settle
            html = await page.content()
        finally:
            await ctx.close()
            await browser.close()
    # extract main text as markdown
    text = md(html, strip=["script", "style", "noscript", "nav", "footer", "aside"], heading_style="ATX")
    return True, text


def probe_playwright(url: str, keywords: list[str], case_id: str) -> Probe:
    p = Probe(tool="playwright", case_id=case_id)
    try:
        ok, text = asyncio.run(_render(url))
    except Exception as e:
        p.error = f"{type(e).__name__}: {str(e)[:120]}"
        return p
    if not ok:
        p.error = "playwright render failed"
        return p
    p.ok = True
    hits, total = keyword_score(text, keywords)
    p.keyword_hits = hits
    p.keyword_total = total
    p.chars_md = len(text)
    p.bytes_out = len(text.encode())
    return p


def main():
    out = Path(__file__).parent.parent / "results" / "playwright.json"
    results = []
    for cid, url, kws, _ in FETCH_URLS:
        print(f"  [{cid}] {url[:50]:<50} ", end="", flush=True)
        probe = timed(lambda: probe_playwright(url, kws, cid))
        results.append(probe)
        print(f"ok={probe.ok}  lat={probe.latency_ms:6.0f}ms  chars={probe.chars_md:6d}  kw={probe.keyword_hits}/{probe.keyword_total}")
        if probe.error:
            print(f"        err: {probe.error[:100]}")
    save_results(results, str(out))
    return results


if __name__ == "__main__":
    main()
