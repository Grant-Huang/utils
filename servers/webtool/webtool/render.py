"""Markdown visualization for WebResult — produces a single .md file."""
from __future__ import annotations
import math
from collections import Counter
from .core import WebResult


def entropy_bar(n: int, total: int, width: int = 20) -> str:
    if total == 0:
        return " " * width
    filled = round((n / total) * width)
    return "█" * filled + "░" * (width - filled)


def render(r: WebResult) -> str:
    """Return markdown content for a single WebResult."""
    out = []
    out.append(f"# Webtool Report\n")
    out.append(f"**Query**: `{r.query}`  ")
    out.append(f"**Generated**: {r.latency_ms:.0f}ms wallclock\n")

    # config table
    out.append("## Configuration\n")
    out.append("| Param | Value |")
    out.append("|---|---|")
    out.append(f"| Search backend | `{r.search_backend}` |")
    out.append(f"| Search N | {r.search_top} |")
    out.append(f"| Rerank | `{r.rerank_method}` ({r.rerank_ms:.0f}ms) |")
    out.append(f"| Rerank k | {r.rerank_k} |")
    out.append(f"| Fetch engine | `{r.fetch_engine}` |")
    out.append("")

    if r.error:
        out.append(f"## ❌ Error\n\n```\n{r.error}\n```\n")
        return "\n".join(out)

    if not r.pages:
        out.append("## ⚠️ No pages fetched\n")
        return "\n".join(out)

    # summary stats
    out.append("## Summary\n")
    out.append(f"- **Pages fetched**: {len(r.pages)} / {r.search_total} search hits")
    out.append(f"- **Total chars**: {r.total_chars:,}")
    out.append(f"- **Distinct domains**: **{r.distinct_doms}**")
    out.append(f"- **Top domain share**: {r.top_dom_share:.1%} (lower = more diverse)")
    out.append(f"- **Host diversity (Shannon, normalized)**: {r.host_diversity:.3f} (1.0 = perfect spread)")
    if r.kw_total:
        out.append(f"- **Keyword coverage**: {min(r.kw_hits, r.kw_total)}/{r.kw_total} = {r.kw_coverage:.1%}")
    out.append("")

    # domain distribution table (visual bars)
    domain_counts = Counter(p["domain"] for p in r.pages)
    out.append("## Domain Distribution\n")
    out.append(f"```\n{''.join(['─' * 60])}")
    out.append(f"{'Domain':<35} {'Pages':<8} Distribution")
    out.append(f"{''.join(['─' * 60])}")
    total = sum(domain_counts.values())
    for dom, count in domain_counts.most_common():
        bar = entropy_bar(count, total)
        out.append(f"{dom[:33]:<35} {count:<8} {bar}")
    out.append(f"{''.join(['─' * 60])}\n```\n")

    # per-page table
    out.append("## Pages\n")
    out.append("| # | Domain | Chars | KW | Title |")
    out.append("|---|---|---:|---|---|")
    for i, p in enumerate(r.pages, 1):
        title = (p["title"] or "(no title)").replace("|", "¦")[:60]
        out.append(f"| {i} | `{p['domain'][:30]}` | {p['chars']:,} | {p['kw_hits']}/{p['kw_total']} | {title} |")
    out.append("")

    # composite score (re-derive using benchmark weights)
    elapsed_s = r.latency_ms / 1000
    speed = max(0.0, min(1.0, 1.0 - (elapsed_s - 30) / 90))
    kw_hit_rate = r.kw_hits / max(1, r.kw_total) if r.kw_total else 0
    fetch_eff = min(1.0, (r.total_chars / max(1, len(r.pages))) / 50000)
    composite = (
        0.30 * kw_hit_rate
        + 0.20 * r.host_diversity
        + 0.15 * (1 - r.top_dom_share)
        + 0.15 * r.kw_coverage
        + 0.10 * speed
        + 0.10 * fetch_eff
    )
    out.append("## Composite Score\n")
    out.append(f"```\n{composite:.3f}\n```\n")
    out.append("| Component | Weight | Value |")
    out.append("|---|---:|---:|")
    out.append(f"| kw_hit_rate | 0.30 | {kw_hit_rate:.3f} |")
    out.append(f"| host_diversity | 0.20 | {r.host_diversity:.3f} |")
    out.append(f"| 1 - top_dom_share | 0.15 | {1 - r.top_dom_share:.3f} |")
    out.append(f"| kw_coverage | 0.15 | {r.kw_coverage:.3f} |")
    out.append(f"| speed | 0.10 | {speed:.3f} |")
    out.append(f"| fetch_efficiency | 0.10 | {fetch_eff:.3f} |")
    out.append(f"| **TOTAL** | 1.00 | **{composite:.3f}** |")
    out.append("")

    return "\n".join(out)
