"""Spike v2: N x rerank_k factorial — 8 variants, real metrics.

Variants:
  N in {10, 20} × k in {4, 6, 8, 10}

For each variant, per case:
- search N URLs (DDG; sleep 8s between cases to avoid anti-bot)
- lexical Jaccard rerank
- fetch top k
- collect: per-URL chars, domain, kw hits → compute diversity/quality metrics
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


# (search_top, rerank_k)
VARIANTS = [
    (10, 4), (10, 6), (10, 8), (10, 10),
    (20, 4), (20, 6), (20, 8), (20, 10),
]


STOP = set("""a an and are as at be by for from has have he her his in is it its of on or
              that the to was were will with i you your we our they them this those
              not no but if so do does did doing than then there here what when where
              which who whom how why all any some most more less very can could should would
              about above after again against all also among because before below between""".split())


def tokenize(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", (s or "").lower()) if w not in STOP and len(w) > 2}


def rerank(query: str, hits: list, top_k: int) -> list:
    q_tokens = tokenize(query)
    if not q_tokens or not hits:
        return hits[:top_k]
    scored = []
    for h in hits:
        doc_tokens = tokenize((h.title or "") + " " + (h.snippet or ""))
        if not doc_tokens:
            scored.append((0.0, 0, h))
            continue
        inter = q_tokens & doc_tokens
        union = q_tokens | doc_tokens
        score = len(inter) / len(union) if union else 0.0
        scored.append((score, id(h), h))  # stable on tie
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [h for _, _, h in scored[:top_k]]


def shannon_entropy(counts: dict) -> float:
    """Higher = more even domain distribution. Returns nats."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return -sum((c/total) * math.log(c/total) for c in counts.values() if c > 0)


def normalize_entropy(counts: dict) -> float:
    """Shannon entropy normalized to [0, 1] by max possible = log(N)."""
    n = len(counts)
    if n <= 1:
        return 0.0
    h = shannon_entropy(counts)
    return h / math.log(n) if n > 1 else 0.0


def run_variant(search_top: int, rerank_k: int,
                query: str, keywords: list, case_id: str) -> Probe:
    """Fetch URLs, compute diversity/quality metrics."""
    p = Probe(tool=f"pipeline(N{search_top}_k{rerank_k})", case_id=case_id)
    t0 = time.perf_counter()

    # search
    try:
        provider = build_provider("duckduckgo")
        hits = provider.search(query, top_n=search_top)
    except Exception as e:
        p.error = f"search: {e}"
        p.latency_ms = (time.perf_counter() - t0) * 1000
        return p

    search_total = len(hits)
    if not hits:
        p.error = "no hits"
        p.latency_ms = (time.perf_counter() - t0) * 1000
        return p

    # rerank
    if rerank_k <= search_total:
        chosen = rerank(query, hits, top_k=rerank_k)
    else:
        chosen = hits[:rerank_k]  # fallback if search returned fewer

    # fetch each
    per_url = []  # [(url, domain, chars, kw_hits)]
    q_kws = [k.lower() for k in keywords]
    for h in chosen:
        c = probe_crawl4ai(h.url, keywords, case_id)
        if c.ok:
            dom = urlparse(h.url).netloc
            text_lower = (c.raw.get("text") or "").lower() if isinstance(c.raw, dict) else ""
            # if crawl4ai didn't save text in raw, we can't compute per-page kw
            # fallback: use chars_md and assume the saved kw_hits is best-per-page
            per_url.append({
                "url": h.url,
                "domain": dom,
                "chars": c.chars_md,
                "kw_hits": c.keyword_hits,
                "kw_total": c.keyword_total,
            })

    if not per_url:
        p.error = "all fetches failed"
        p.latency_ms = (time.perf_counter() - t0) * 1000
        return p

    # ---- metrics ----
    domains = [u["domain"] for u in per_url]
    domain_counts = {}
    for d in domains:
        domain_counts[d] = domain_counts.get(d, 0) + 1

    total_chars = sum(u["chars"] for u in per_url)
    distinct_doms = len(domain_counts)
    top_dom_share = max(domain_counts.values()) / sum(domain_counts.values())

    # kw coverage: how many of the expected kws appeared across ALL pages
    # (since per-page kw tracking is best-effort, we use total kw_hits as proxy)
    kw_hits_total = sum(u["kw_hits"] for u in per_url)
    kw_total_total = sum(u["kw_total"] for u in per_url)
    kw_hit_rate = kw_hits_total / max(1, kw_total_total)

    # unique kw coverage: try to extract kws from per_url (we don't have text saved)
    # proxy: fraction of expected kws that got at least 1 hit somewhere
    # since we only have counts not which kws, use kw_hits_total capped at len(keywords)
    unique_kws_hit = min(kw_hits_total, len(keywords))
    kw_coverage = unique_kws_hit / max(1, len(keywords))

    # info density: chars per domain (lower = better per-domain signal)
    info_density = total_chars / distinct_doms

    # Shannon entropy (normalized)
    host_div = normalize_entropy(domain_counts)

    # speed score
    elapsed_s = (time.perf_counter() - t0)
    speed = max(0.0, min(1.0, 1.0 - (elapsed_s - 30) / 90))  # 30s=1.0, 120s=0.0

    # fetch efficiency: chars per fetched URL (50K is "good" baseline)
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
    p.n_results = search_total
    p.latency_ms = elapsed_s * 1000
    p.chars_md = total_chars
    p.keyword_hits = kw_hits_total
    p.keyword_total = kw_total_total
    p.raw = {
        "fetched": len(per_url),
        "distinct_doms": distinct_doms,
        "top_dom_share": top_dom_share,
        "host_diversity": host_div,
        "info_density": info_density,
        "kw_coverage": kw_coverage,
        "fetch_eff": fetch_eff,
        "speed": speed,
        "score": score,
        "domains": dict(sorted(domain_counts.items(), key=lambda x: -x[1])[:5]),
        "search_total": search_total,
    }
    return p


def main():
    out = Path(__file__).parent.parent / "results" / "pipeline_n_k_factorial.json"
    results = []
    total_cases = len(SEARCH_QUERIES) * len(VARIANTS)
    case_i = 0
    for search_top, rerank_k in VARIANTS:
        print(f"\n--- N={search_top} rerank_k={rerank_k} ---", flush=True)
        for cid, q, kws, targets in SEARCH_QUERIES:
            case_i += 1
            print(f"  [{case_i}/{total_cases}] {cid} N{search_top}_k{rerank_k}  {q[:30]:<30} ", end="", flush=True)
            time.sleep(8)  # DDG anti-bot cooldown
            probe = run_variant(search_top, rerank_k, q, kws, cid)
            results.append(probe)
            if probe.ok:
                r = probe.raw
                print(f"score={r['score']:.2f} lat={probe.latency_ms/1000:.0f}s "
                      f"fetched={r['fetched']}/{r['search_total']} dom={r['distinct_doms']} "
                      f"top_share={r['top_dom_share']:.2f} kw={probe.keyword_hits}/{probe.keyword_total}")
            else:
                print(f"err={probe.error[:60]}")
    save_results(results, str(out))


if __name__ == "__main__":
    main()
