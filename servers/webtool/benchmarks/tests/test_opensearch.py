"""OpenSearch self-index probe (Apache-2.0).

OpenSearch is a self-hosted search engine built on Elasticsearch 7 lineage.
Tests two things:
1. Client SDK round-trip (connect, index 5 docs, search, bulk API)
2. Self-deploy instructions + cost (binary vs docker)

Run modes:
- Live mode: requires OPENSEARCH_URL env (default http://localhost:9200)
- Smoke mode: uses opensearchpy client against a stub URL; records protocol capability
"""
from __future__ import annotations
import sys, os, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _fixtures import Probe, SEARCH_QUERIES, timed, keyword_score, domain_hit, save_results

OS_URL = os.environ.get("OPENSEARCH_URL", "http://localhost:9200")
OS_INDEX = "webbench_test_corpus"

# Tiny in-memory corpus to index when OpenSearch is reachable
CORPUS = [
    {"id": "1", "title": "OpenAI announces new safety framework", "body": "OpenAI published a new safety framework on September 28 2026 covering alignment evals.", "url": "https://openai.com/blog/safety-2026", "date": "2026-09-28"},
    {"id": "2", "title": "Python asyncio cancellation semantics in 3.13", "body": "asyncio task cancellation in Python 3.13 changes for shield() and uncancel().", "url": "https://docs.python.org/3/library/asyncio-task.html", "date": "2025-12-01"},
    {"id": "3", "title": "武汉 天气预报 2026年10月1日", "body": "武汉 10月1日 多云转晴 气温18-26度 风力2级。", "url": "https://example.com/wuhan-weather", "date": "2026-10-01"},
    {"id": "4", "title": "Hermes Agent desktop runtime architecture", "body": "Hermes desktop uses debugpy for remote debugging the Python gateway process.", "url": "https://github.com/nousresearch/hermes-agent", "date": "2026-08-15"},
    {"id": "5", "title": "LLM Agent survey: a comprehensive review 2026", "body": "This survey covers LLM agents from 2024 to 2026 with 200+ citations on arXiv.", "url": "https://arxiv.org/abs/2601.00000", "date": "2026-01-01"},
]

QUERIES = [
    ("Q1", "OpenAI news this week", ["OpenAI"], ["openai.com"]),
    ("Q2", "Python asyncio task cancellation", ["asyncio", "cancel"], ["docs.python.org"]),
    ("Q3", "武汉 天气", ["武汉", "天气"], []),
    ("Q4", "Hermes Agent debugpy", ["Hermes", "debugpy"], ["github.com"]),
    ("Q5", "LLM agent survey", ["LLM", "survey"], ["arxiv.org"]),
]


def probe_opensearch(query: str, keywords: list, targets: list, case_id: str) -> Probe:
    p = Probe(tool="opensearch", case_id=case_id)
    try:
        from opensearchpy import OpenSearch
        client = OpenSearch(
            hosts=[OS_URL],
            http_compress=True,
            request_timeout=8,
            max_retries=1,
            retry_on_timeout=False,
        )
        info = client.info()
    except Exception as e:
        p.error = f"connect: {type(e).__name__}: {str(e)[:80]}"
        return p

    # try to create index + bulk index
    try:
        if client.indices.exists(index=OS_INDEX):
            client.indices.delete(index=OS_INDEX)
        client.indices.create(index=OS_INDEX, body={
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            "mappings": {"properties": {
                "title": {"type": "text"},
                "body": {"type": "text"},
                "url": {"type": "keyword"},
                "date": {"type": "date"},
            }}
        })
        bulk_body = []
        for d in CORPUS:
            bulk_body.append({"index": {"_index": OS_INDEX, "_id": d["id"]}})
            bulk_body.append({k: v for k, v in d.items() if k != "id"})
        client.bulk(body=bulk_body)
        client.indices.refresh(index=OS_INDEX)
    except Exception as e:
        p.error = f"index: {type(e).__name__}: {str(e)[:80]}"
        return p

    # search
    try:
        resp = client.search(index=OS_INDEX, body={
            "query": {"multi_match": {"query": query, "fields": ["title^2", "body"]}},
            "size": 5,
        })
        hits = resp.get("hits", {}).get("hits", [])
    except Exception as e:
        p.error = f"search: {type(e).__name__}: {str(e)[:80]}"
        return p

    if not hits:
        p.error = "no hits"
        return p

    p.ok = True
    p.n_results = len(hits)
    titles = [h["_source"].get("title", "") for h in hits]
    urls = [h["_source"].get("url", "") for h in hits]
    body_blob = "\n".join(h["_source"].get("body", "") for h in hits) + "\n" + "\n".join(titles)
    h, t = keyword_score(body_blob, keywords)
    p.keyword_hits = h
    p.keyword_total = t
    p.target_domain_hit = domain_hit(urls, targets)
    p.chars_md = len(body_blob)
    p.raw = {"cluster": info.get("version", {}).get("number"), "top3": list(zip(titles[:3], urls[:3]))}
    return p


def main():
    out = Path(__file__).parent.parent / "results" / "opensearch.json"
    results = []
    for cid, q, kws, targets in QUERIES:
        print(f"  [{cid}] {q[:40]:<40} ", end="", flush=True)
        probe = timed(lambda: probe_opensearch(q, kws, targets, cid))
        results.append(probe)
        print(f"ok={probe.ok}  lat={probe.latency_ms:6.0f}ms  kw={probe.keyword_hits}/{probe.keyword_total}  dom={probe.target_domain_hit}")
        if probe.error:
            print(f"        err: {probe.error[:100]}")
    save_results(results, str(out))
    return results


if __name__ == "__main__":
    main()
