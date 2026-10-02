"""Cross-encoder rerank vs lexical Jaccard — head-to-head on N=10.

We rerun the SAME queries with TWO rerankers at the SAME k values,
holding everything else constant. The only variable is the reranker.
"""
from __future__ import annotations
import sys, time, warnings, re, math
warnings.filterwarnings("ignore")
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0, str(Path(__file__).parent))
from _fixtures import Probe, SEARCH_QUERIES, save_results
from search_provider import build_provider
from test_crawl4ai import probe_crawl4ai

# Lazy load cross-encoder (37s cold start)
_CE = None


def get_ce():
    global _CE
    if _CE is None:
        from sentence_transformers import CrossEncoder
        _CE = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _CE


STOP = set("""a an and are as at be by for from has have he her his in is it its of on or
              that the to was were will with i you your we our they them this those
              not no but if so do does did doing than then there here what when where
              which who whom how why all any some most more less very can could should would
              about above after again against all also among because before below between""".split())


def tokenize(s):
    return {w for w in re.findall(r"[a-z]+", (s or "").lower()) if w not in STOP and len(w) > 2}


def rerank_lexical(query: str, hits: list, top_k: int) -> list:
    q = tokenize(query)
    if not q or not hits:
        return hits[:top_k]
    scored = []
    for h in hits:
        d = tokenize((h.title or "") + " " + (h.snippet or ""))
        if not d:
            scored.append((0.0, id(h), h))
            continue
        inter = q & d
        union = q | d
        scored.append((len(inter) / len(union), id(h), h))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [h for _, _, h in scored[:top_k]]


def rerank_cross(query: str, hits: list, top_k: int) -> list:
    ce = get_ce()
    pairs = [(query, (h.title or "") + " " + (h.snippet or "")) for h in hits]
    scores = ce.predict(pairs)
    # stable sort: keep original order on tie
    indexed = list(enumerate(scores))
    indexed.sort(key=lambda x: -x[1])
    return [hits[i] for i, _ in indexed[:top_k]]


def shannon_norm(counts):
    n = len(counts)
    if n <= 1:
        return 0.0
    total = sum(counts.values())
    h = -sum((c/total) * math.log(c/total) for c in counts.values() if c > 0)
    return h / math.log(n)


# Variants: (search_top, rerank_k, rerank_method)
VARIANTS = [
    (10, 4, "lexical"),
    (10, 6, "lexical"),
    (10, 6, "cross"),       # sweet spot x 2 rerankers
    (10, 10, "lexical"),
    (10, 10, "cross"),      # max-k x 2 rerankers
]


def run_variant(search_top, rerank_k, method, query, keywords, case_id):
    p = Probe(tool=f"pipeline(N{search_top}_k{rerank_k}_{method})", case_id=case_id)
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

    rerank_fn = rerank_lexical if method == "lexical" else rerank_cross
    rerank_t0 = time.perf_counter()
    chosen = rerank_fn(query, hits, top_k=rerank_k)
    rerank_ms = (time.perf_counter() - rerank_t0) * 1000

    per_url = []
    for h in chosen:
        c = probe_crawl4ai(h.url, keywords, case_id)
        if c.ok:
            per_url.append({
                "domain": urlparse(h.url).netloc,
                "chars": c.chars_md,
                "kw_hits": c.keyword_hits,
                "kw_total": c.keyword_total,
            })

    if not per_url:
        p.error = "all fetches failed"
        p.latency_ms = (time.perf_counter() - t0) * 1000
        return p

    domain_counts = {}
    for u in per_url:
        domain_counts[u["domain"]] = domain_counts.get(u["domain"], 0) + 1

    total_chars = sum(u["chars"] for u in per_url)
    distinct_doms = len(domain_counts)
    top_dom_share = max(domain_counts.values()) / sum(domain_counts.values())
    kw_hits_total = sum(u["kw_hits"] for u in per_url)
    kw_total_total = sum(u["kw_total"] for u in per_url)
    kw_hit_rate = kw_hits_total / max(1, kw_total_total)
    kw_coverage = min(kw_hits_total, len(keywords)) / max(1, len(keywords))
    host_div = shannon_norm(domain_counts)

    elapsed_s = (time.perf_counter() - t0)
    speed = max(0.0, min(1.0, 1.0 - (elapsed_s - 30) / 90))
    fetch_eff = min(1.0, (total_chars / max(1, len(per_url))) / 50000)

    score = (
        0.30 * kw_hit_rate
        + 0.20 * host_div
        + 0.15 * (1 - top_dom_share)
        + 0.15 * kw_coverage
        + 0.10 * speed
        + 0.10 * fetch_eff
    )

    p.ok = True
    p.n_results = len(hits)
    p.latency_ms = elapsed_s * 1000
    p.chars_md = total_chars
    p.keyword_hits = kw_hits_total
    p.keyword_total = kw_total_total
    p.raw = {
        "fetched": len(per_url),
        "distinct_doms": distinct_doms,
        "top_dom_share": top_dom_share,
        "host_diversity": host_div,
        "kw_coverage": kw_coverage,
        "fetch_eff": fetch_eff,
        "speed": speed,
        "score": score,
        "rerank_ms": rerank_ms,
    }
    return p


def main():
    out = Path(__file__).parent.parent / "results" / "pipeline_rerank_compare.json"
    # warm the cross-encoder ONCE outside timing
    print("warming cross-encoder model...", flush=True)
    t0 = time.perf_counter()
    get_ce()
    print(f"  warm load: {(time.perf_counter()-t0)*1000:.0f}ms")

    results = []
    total = len(VARIANTS) * len(SEARCH_QUERIES)
    i = 0
    for st, rk, method in VARIANTS:
        print(f"\n--- N={st} k={rk} rerank={method} ---", flush=True)
        for cid, q, kws, targets in SEARCH_QUERIES:
            i += 1
            print(f"  [{i}/{total}] {cid} {q[:30]:<30} ", end="", flush=True)
            time.sleep(8)  # DDG anti-bot cooldown
            probe = run_variant(st, rk, method, q, kws, cid)
            results.append(probe)
            if probe.ok:
                r = probe.raw
                print(f"score={r['score']:.2f} lat={probe.latency_ms/1000:.0f}s "
                      f"fetched={r['fetched']}/{probe.n_results} dom={r['distinct_doms']} "
                      f"top={r['top_dom_share']:.2f} kw={probe.keyword_hits}/{probe.keyword_total} "
                      f"rerank={r['rerank_ms']:.0f}ms")
            else:
                print(f"err={probe.error[:60]}")
    save_results(results, str(out))


if __name__ == "__main__":
    main()
