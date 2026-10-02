"""Spike: Pipeline variants with N=3 vs N=20 fetch, with/without rerank.

Variants:
- A: N=3  (current baseline)
- B: N=20 fetch all, no rerank
- C: N=20 fetch all + rerank (cosine sim with title+snippet)

Metrics: per-case latency, chars, keyword hits, source diversity (distinct domains).
"""
from __future__ import annotations
import sys, time, warnings, re
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _fixtures import Probe, SEARCH_QUERIES, timed, keyword_score, domain_hit, save_results
from search_provider import build_provider
from test_crawl4ai import probe_crawl4ai


N_VARIANTS = [
    ("A_N3", 3, 3, False),    # baseline: fetch top 3
    ("B_N20_all", 20, 20, False),  # fetch all top 20, no rerank
    ("C_N20_rerank10", 20, 10, True),  # fetch top 20, rerank, keep top 10
]


def _tokenize(s: str) -> set[str]:
    """Crude tokenizer: lowercase + split on non-alpha, drop stopwords."""
    STOP = set("""a an and are as at be by for from has have he her his in is it its of on or
                  that the to was were will with i you your we our they them this those""".split())
    return {w for w in re.findall(r"[a-z]+", (s or "").lower()) if w not in STOP and len(w) > 2}


def rerank(query: str, hits: list, top_k: int) -> list:
    """Lexical Jaccard rerank (cheap; ~ms not seconds).

    score = |Q ∩ D| / |Q ∪ D|  on title+snippet tokens.
    Falls back to original order on ties.
    """
    q_tokens = _tokenize(query)
    if not q_tokens or not hits:
        return hits[:top_k]
    scored = []
    for h in hits:
        doc_tokens = _tokenize((h.title or "") + " " + (h.snippet or ""))
        if not doc_tokens:
            scored.append((0.0, h))
            continue
        inter = q_tokens & doc_tokens
        union = q_tokens | doc_tokens
        score = len(inter) / len(union) if union else 0.0
        # tiebreak by URL order in original list (preserve index)
        scored.append((score, h))
    # sort desc by score, stable
    scored.sort(key=lambda x: x[0], reverse=True)
    return [h for _, h in scored[:top_k]]


def run_variant(name: str, search_top: int, fetch_top: int, do_rerank: bool,
                query: str, keywords: list, targets: list, case_id: str) -> Probe:
    p = Probe(tool=f"pipeline-{name}", case_id=case_id)
    t0 = time.perf_counter()
    try:
        provider = build_provider("duckduckgo")
        hits = provider.search(query, top_n=search_top)
    except Exception as e:
        p.error = f"search: {e}"
        p.latency_ms = (time.perf_counter() - t0) * 1000
        return p
    if not hits:
        p.error = "no hits"
        p.latency_ms = (time.perf_counter() - t0) * 1000
        return p
    if do_rerank:
        hits = rerank(query, hits, top_k=fetch_top)
    else:
        hits = hits[:fetch_top]
    p.n_results = len(hits)
    p.target_domain_hit = domain_hit([h.url for h in hits], targets)
    # fetch each
    best_hits = (0, len(keywords))
    best_chars = 0
    total_chars = 0
    domains = set()
    fetched = 0
    for h in hits:
        c = probe_crawl4ai(h.url, keywords, case_id)
        if c.ok:
            fetched += 1
            total_chars += c.chars_md
            # domain
            try:
                from urllib.parse import urlparse
                domains.add(urlparse(h.url).netloc)
            except Exception:
                pass
            if c.keyword_hits > best_hits[0]:
                best_hits = (c.keyword_hits, c.keyword_total)
                best_chars = c.chars_md
    p.ok = fetched > 0
    p.keyword_hits = best_hits[0]
    p.keyword_total = best_hits[1]
    p.chars_md = total_chars  # sum across all fetched pages
    p.raw = {"fetched": fetched, "domains": len(domains), "best_chars": best_chars}
    p.latency_ms = (time.perf_counter() - t0) * 1000
    return p


def main():
    out = Path(__file__).parent.parent / "results" / "pipeline_n_variants.json"
    results = []
    for vname, s_top, f_top, do_rr in N_VARIANTS:
        print(f"\n--- {vname} (search_top={s_top} fetch_top={f_top} rerank={do_rr}) ---")
        for cid, q, kws, targets in SEARCH_QUERIES:
            print(f"  [{cid}] {q[:35]:<35} ", end="", flush=True)
            time.sleep(8)  # avoid DDG anti-bot across cases
            probe = timed(lambda: run_variant(vname, s_top, f_top, do_rr, q, kws, targets, cid))
            results.append(probe)
            doms = probe.raw.get("domains", 0) if probe.raw else 0
            print(f"ok={probe.ok} lat={probe.latency_ms:6.0f}ms chars={probe.chars_md:6d} kw={probe.keyword_hits}/{probe.keyword_total} dom_hit={probe.target_domain_hit} distinct_dom={doms}")
            if probe.error:
                print(f"        err: {probe.error[:80]}")
    save_results(results, str(out))


if __name__ == "__main__":
    main()
