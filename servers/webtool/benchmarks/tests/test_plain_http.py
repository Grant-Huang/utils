"""Plain-HTTP fetch probe — baseline / lowest-overhead path.

Used as the cheap fallback before escalating to Crawl4AI or Playwright.
Trafilatura handles Markdown extraction (Apache-2.0, BSD-2-Clause dual).
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _fixtures import Probe, FETCH_URLS, timed, keyword_score, save_results
from _http import make_client

try:
    import trafilatura
    HAS_TRAF = True
except ImportError:
    HAS_TRAF = False


def probe_plain(url: str, keywords: list[str], case_id: str) -> Probe:
    p = Probe(tool="plain-http(trafilatura)", case_id=case_id)
    if not HAS_TRAF:
        p.error = "trafilatura not installed"
        return p
    client = make_client(timeout=12)
    try:
        resp = client.get(url)
        if resp.status_code != 200:
            p.error = f"HTTP {resp.status_code}"
            return p
        md = trafilatura.extract(resp.text, include_comments=False, include_tables=True, output_format="markdown") or ""
        p.ok = bool(md) and len(md) >= 80
        hits, total = keyword_score(md, keywords)
        p.keyword_hits = hits
        p.keyword_total = total
        p.chars_md = len(md)
        p.bytes_out = len(resp.content)
        if not p.ok and not p.error:
            p.error = "extraction too short (<80 chars)"
    except Exception as e:
        p.error = f"{type(e).__name__}: {str(e)[:120]}"
    finally:
        client.close()
    return p


def main():
    out = Path(__file__).parent.parent / "results" / "plain_http.json"
    results = []
    for cid, url, kws, _ in FETCH_URLS:
        print(f"  [{cid}] {url[:50]:<50} ", end="", flush=True)
        probe = timed(lambda: probe_plain(url, kws, cid))
        results.append(probe)
        print(f"ok={probe.ok}  lat={probe.latency_ms:6.0f}ms  chars={probe.chars_md:6d}  kw={probe.keyword_hits}/{probe.keyword_total}")
        if probe.error:
            print(f"        err: {probe.error[:100]}")
    save_results(results, str(out))
    return results


if __name__ == "__main__":
    main()
