"""CLI entry point."""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(
        prog="webtool",
        description="Configurable web search + fetch. Defaults = benchmark winners.",
    )
    ap.add_argument("query", help="Search query")
    ap.add_argument("--keywords", help="Comma-separated expected keywords (for quality scoring)")
    ap.add_argument("--search-top", type=int, default=10, help="Number of search hits to retrieve (default: 10)")
    ap.add_argument("--rerank-k", type=int, default=6, help="Number of URLs to keep after rerank (default: 6)")
    ap.add_argument("--rerank", choices=["cross", "lexical", "none"], default="cross", help="Rerank method (default: cross)")
    ap.add_argument("--fetch", choices=["crawl4ai", "playwright", "plain"], default="crawl4ai", help="Fetch engine (default: crawl4ai)")
    ap.add_argument("--search-backend", choices=["duckduckgo", "searxng", "brave"], default="duckduckgo", help="Search backend (default: duckduckgo)")
    ap.add_argument("--model", default="cross-encoder/ms-marco-MiniLM-L-6-v2", help="Cross-encoder model name")
    ap.add_argument("--no-rerank", action="store_true", help="Skip rerank (use top-k of search results)")
    ap.add_argument("--out-md", help="Write markdown report to this path")
    ap.add_argument("--out-json", help="Write JSON result to this path")
    args = ap.parse_args()

    # Resolve rerank to "none" if --no-rerank
    if args.no_rerank:
        args.rerank = "lexical"  # we still need some ranking; lexical is cheap and deterministic
        # Actually, let's interpret --no-rerank as "use search order verbatim"
        # To do that, override rerank_k to search_top and use lexical with identity behavior
        args.rerank_k = args.search_top

    keywords = [k.strip() for k in (args.keywords or "").split(",") if k.strip()] or None

    from webtool.core import run
    print(f"[webtool] query={args.query!r}", flush=True)
    print(f"[webtool] cfg: search_top={args.search_top} rerank_k={args.rerank_k} "
          f"rerank={args.rerank} fetch={args.fetch} backend={args.search_backend}", flush=True)

    result = run(
        args.query,
        keywords=keywords,
        search_top=args.search_top,
        rerank_k=args.rerank_k,
        rerank=args.rerank,
        fetch=args.fetch,
        search_backend=args.search_backend,
        model=args.model,
    )

    # console summary
    print(f"\n[webtool] done in {result.latency_ms:.0f}ms", flush=True)
    if result.error:
        print(f"[webtool] error: {result.error}", flush=True)
    else:
        print(f"[webtool] {len(result.pages)} pages, "
              f"{result.distinct_doms} domains, "
              f"{result.total_chars:,} chars", flush=True)

    # write outputs
    if args.out_md:
        from webtool.render import render
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_md).write_text(render(result))
        print(f"[webtool] markdown → {args.out_md}")
    if args.out_json:
        from webtool.core import to_dict
        Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_json).write_text(json.dumps(to_dict(result), indent=2, default=str))
        print(f"[webtool] json → {args.out_json}")

    return 0 if not result.error else 1


if __name__ == "__main__":
    sys.exit(main())
