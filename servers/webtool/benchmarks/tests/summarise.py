"""Summarise all results/*.json into a markdown report + CSV.

Tracks: license, role, AND diversity/quality metrics (distinct_domains,
top_domain_share, Shannon entropy, kw_coverage) so the report can answer
"what's the right N×k tradeoff" not just "which tool wins".
"""
from __future__ import annotations
import json, csv, sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _fixtures import percentile

RESULTS_DIR = Path(__file__).parent.parent / "results"

# Single-tool probes (license + role)
TOOLS = [
    ("plain_http",      "Plain HTTP (httpx + trafilatura)",  "Apache-2.0 / BSD-2", "baseline",          0.95),
    ("crawl4ai",        "Crawl4AI",                            "Apache-2.0",         "default fetch",     0.55),
    ("playwright",      "Playwright",                          "Apache-2.0",         "JS-render fallback",0.50),
    ("scrapy",          "Scrapy",                              "BSD-3-Clause",       "batch crawl",       0.70),
    ("search_providers","SearchProvider (DDG/SearXNG/Brave)",  "varies",             "search adapter",    0.80),
    ("opensearch",      "OpenSearch",                          "Apache-2.0",         "self-hosted index", 0.30),
    ("pipeline",        "Pipeline: Search→Crawl4AI|Playwright","composite",         "end-to-end",        0.55),
    # N×k factorial — uses raw.* diversity fields
    ("pipeline_n_k_factorial", "Pipeline N×k factorial (8 variants)", "varies",       "N×k tradeoff",      0.50),
]


def load(name: str) -> list[dict]:
    p = RESULTS_DIR / f"{name}.json"
    if not p.exists():
        return []
    return json.loads(p.read_text())


def summarise(records: list[dict]) -> dict:
    if not records:
        return {"n": 0}
    n = len(records)
    ok = sum(1 for r in records if r["ok"])
    lats = [r["latency_ms"] for r in records if r["latency_ms"] > 0]
    chars = [r["chars_md"] for r in records if r["chars_md"] > 0]
    hits = [r["keyword_hits"] for r in records]
    tot = [r["keyword_total"] for r in records if r["keyword_total"] > 0]
    out = {
        "n": n, "ok": ok, "ok_rate": ok / n,
        "lat_p50_ms": percentile(lats, 0.5),
        "lat_p95_ms": percentile(lats, 0.95),
        "chars_avg": sum(chars) / max(1, len(chars)),
        "chars_total": sum(chars),
        "kw_hits": sum(hits), "kw_total": sum(tot),
        "kw_rate": sum(hits) / max(1, sum(tot)),
    }
    # Pull diversity from raw if present (N×k factorial output)
    divs = [r.get("raw", {}).get("host_diversity") for r in records if r["ok"] and r.get("raw")]
    divs = [d for d in divs if d is not None]
    if divs:
        out["host_diversity"] = sum(divs) / len(divs)
    shares = [r.get("raw", {}).get("top_dom_share") for r in records if r["ok"] and r.get("raw")]
    shares = [s for s in shares if s is not None]
    if shares:
        out["top_dom_share"] = sum(shares) / len(shares)
    doms = [r.get("raw", {}).get("distinct_doms") for r in records if r["ok"] and r.get("raw")]
    doms = [d for d in doms if d is not None]
    if doms:
        out["distinct_doms"] = sum(doms) / len(doms)
    cov = [r.get("raw", {}).get("kw_coverage") for r in records if r["ok"] and r.get("raw")]
    cov = [c for c in cov if c is not None]
    if cov:
        out["kw_coverage"] = sum(cov) / len(cov)
    return out


def score(s: dict, deploy_ease: float = 0.5) -> float:
    if s.get("n", 0) == 0:
        return 0.0
    ok = s["ok_rate"]
    quality = s.get("kw_rate", 0.0)
    speed = max(0.0, min(1.0, 1.0 - (s["lat_p50_ms"] / 1000 - 3) / 27))
    robust = ok
    return 0.30 * ok + 0.25 * quality + 0.20 * speed + 0.15 * robust + 0.10 * deploy_ease


def factorial_breakdown(name: str) -> list[tuple]:
    """Per-variant aggregation for the N×k factorial results."""
    recs = load(name)
    by_var = {}
    for r in recs:
        v = r["tool"]
        by_var.setdefault(v, []).append(r)
    out = []
    for v, cases in by_var.items():
        ok = [c for c in cases if c["ok"]]
        if not ok:
            out.append((v, 0, len(cases), 0, 0, 0, 0, 0))
            continue
        lats = [c["latency_ms"] / 1000 for c in ok if c["latency_ms"] > 0]
        p50 = percentile(lats, 0.5) if lats else 0
        doms = [c["raw"]["distinct_doms"] for c in ok]
        shares = [c["raw"]["top_dom_share"] for c in ok]
        divs = [c["raw"]["host_diversity"] for c in ok]
        scores = [c["raw"]["score"] for c in ok]
        out.append((v, len(ok), len(cases), p50,
                    sum(doms) / len(doms),
                    sum(shares) / len(shares),
                    sum(divs) / len(divs),
                    sum(scores) / len(scores)))
    return out


def main():
    print("=" * 80)
    print("MAIN TOOLS")
    print("=" * 80)
    print("{:<40} {:<25} {:<8} {:<10} {:<8} {:<8} {:<6}".format(
        "Tool", "License", "OK", "P50(ms)", "chars", "kw%", "score"))
    print("-" * 110)
    rows = []
    for k, label, lic, role, deploy in TOOLS:
        s = summarise(load(k))
        sc = score(s, deploy) if s.get("n", 0) > 0 else 0.0
        if s.get("n", 0) == 0:
            print("{:<40} {:<25} {:<8} {:<10} {:<8} {:<8} {:.2f}".format(
                label, lic, "-", "-", "-", "-", sc))
        else:
            print("{:<40} {:<25} {:<8} {:<10.0f} {:<8.0f} {:<7.1f}% {:.2f}".format(
                label, lic, "{}/{}".format(s["ok"], s["n"]),
                s["lat_p50_ms"], s["chars_avg"], s["kw_rate"] * 100, sc))
        rows.append((k, label, lic, role, deploy, s, sc))

    # N×k factorial breakdown
    print("\n" + "=" * 80)
    print("PIPELINE N×K FACTORIAL BREAKDOWN")
    print("=" * 80)
    print("{:<22} {:<6} {:<8} {:<6} {:<10} {:<6}".format(
        "Variant", "OK", "P50(s)", "dom", "top_share", "score"))
    print("-" * 70)
    for v, ok_n, total, p50, doms, share, div, sc in factorial_breakdown("pipeline_n_k_factorial"):
        print("{:<22} {:<6} {:<8.1f} {:<6.1f} {:<10.2f} {:.2f}".format(
            v, "{}/{}".format(ok_n, total), p50, doms, share, sc))

    # CSV (main tools)
    with open(RESULTS_DIR / "summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["json", "label", "license", "role", "deploy_ease", "n", "ok",
                    "ok_rate", "lat_p50_ms", "lat_p95_ms", "chars_avg", "chars_total",
                    "kw_hits", "kw_total", "kw_rate", "host_diversity", "top_dom_share",
                    "distinct_doms", "kw_coverage", "score"])
        for k, label, lic, role, deploy, s, sc in rows:
            w.writerow([k, label, lic, role, deploy, s.get("n", 0), s.get("ok", 0),
                        f"{s.get('ok_rate', 0):.3f}",
                        f"{s.get('lat_p50_ms', 0):.0f}",
                        f"{s.get('lat_p95_ms', 0):.0f}",
                        f"{s.get('chars_avg', 0):.0f}",
                        s.get("chars_total", 0),
                        s.get("kw_hits", 0), s.get("kw_total", 0),
                        f"{s.get('kw_rate', 0):.3f}",
                        f"{s.get('host_diversity', 0):.3f}",
                        f"{s.get('top_dom_share', 0):.3f}",
                        f"{s.get('distinct_doms', 0):.1f}",
                        f"{s.get('kw_coverage', 0):.3f}",
                        f"{sc:.3f}"])
    # CSV (factorial)
    with open(RESULTS_DIR / "summary_factorial.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["variant", "ok", "total", "p50_s", "distinct_doms",
                    "top_dom_share", "host_diversity", "score"])
        for v, ok_n, total, p50, doms, share, div, sc in factorial_breakdown("pipeline_n_k_factorial"):
            w.writerow([v, ok_n, total, f"{p50:.1f}", f"{doms:.1f}",
                        f"{share:.3f}", f"{div:.3f}", f"{sc:.3f}"])
    print(f"\nWrote: {RESULTS_DIR / 'summary.csv'}, {RESULTS_DIR / 'summary_factorial.csv'}")


if __name__ == "__main__":
    main()
