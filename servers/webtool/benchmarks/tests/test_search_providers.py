"""Test the SearchProvider 适配层 — try each backend, summarise."""
from __future__ import annotations
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _fixtures import Probe, SEARCH_QUERIES, timed, keyword_score, domain_hit, save_results
from search_provider import build_provider


def probe_query(provider_name: str, query: str, keywords: list, targets: list, case_id: str) -> Probe:
    p = Probe(tool=f"search:{provider_name}", case_id=case_id)
    try:
        provider = build_provider(provider_name)
    except Exception as e:
        p.error = f"init: {e}"
        return p
    try:
        hits = provider.search(query, top_n=5)
    except Exception as e:
        p.error = f"{type(e).__name__}: {str(e)[:120]}"
        return p
    if not hits:
        p.error = "no hits"
        return p
    p.ok = True
    p.n_results = len(hits)
    blob = "\n".join(h.title for h in hits) + "\n" + "\n".join(h.snippet for h in hits)
    h, t = keyword_score(blob, keywords)
    p.keyword_hits = h
    p.keyword_total = t
    p.target_domain_hit = domain_hit([h.url for h in hits], targets)
    p.chars_md = len(blob)
    p.raw = {"hits": [h.to_dict() for h in hits[:3]]}
    return p


def main():
    out = Path(__file__).parent.parent / "results" / "search_providers.json"
    results = []
    providers = [
        "duckduckgo",   # works without setup
        "searxng",      # requires local docker
        "brave",        # requires BRAVE_API_KEY
    ]
    for provider_name in providers:
        print(f"\n--- {provider_name} ---")
        for cid, q, kws, targets in SEARCH_QUERIES:
            print(f"  [{cid}] {q[:40]:<40} ", end="", flush=True)
            probe = timed(lambda: probe_query(provider_name, q, kws, targets, cid))
            results.append(probe)
            print(f"ok={probe.ok}  lat={probe.latency_ms:6.0f}ms  kw={probe.keyword_hits}/{probe.keyword_total}  dom={probe.target_domain_hit}")
            if probe.error:
                print(f"        err: {probe.error[:100]}")
    save_results(results, str(out))
    return results


if __name__ == "__main__":
    main()
