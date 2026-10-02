"""Scrapy batch-crawl probe (BSD-3-Clause).

Runs ONE case per subprocess because Twisted reactor can't be restarted.
Measures: per-page latency, extraction quality on a fixed seed.
"""
from __future__ import annotations
import sys, warnings, subprocess, json
warnings.filterwarnings("ignore")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _fixtures import Probe, save_results

# Tiny corpus for single-page Scrapy crawl
CORPUS = [
    ("F1", "https://lilianweng.github.io/posts/2023-06-23-agent/", ["agent", "LLM"]),
    ("F2", "https://docs.python.org/3/library/asyncio-task.html", ["asyncio", "cancel"]),
    ("F3", "https://news.ycombinator.com/", ["Hacker", "ycombinator"]),
    ("F4", "https://www.baidu.com/", ["百度"]),
    ("F5", "https://en.wikipedia.org/wiki/Large_language_model", ["language", "transformer"]),
    ("F6", "https://vercel.com/docs", ["Vercel", "deploy"]),
    ("F7", "https://github.com/unclecode/crawl4ai", ["crawl4ai", "scrape"]),
]


def _worker(cid: str, url: str, kws: list, out_path: str):
    """Single-process Scrapy runner."""
    import scrapy, time
    from scrapy.crawler import CrawlerProcess
    t0 = time.perf_counter()

    class ProbeSpider(scrapy.Spider):
        name = "probe"
        custom_settings = {
            "ROBOTSTXT_OBEY": False,
            "CONCURRENT_REQUESTS": 1,
            "DOWNLOAD_TIMEOUT": 12,
            "LOG_LEVEL": "ERROR",
            "USER_AGENT": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        }
        def start_requests(self):
            yield scrapy.Request(url, dont_filter=True, meta={"case_id": cid, "kws": kws})
        def parse(self, response):
            text = " ".join(response.css("h1::text, h2::text, p::text, li::text").getall())
            yield {"case_id": response.meta["case_id"], "text": text}

    process = CrawlerProcess(ProbeSpider.custom_settings)
    results = []
    collector = []

    class CollectorSpider(ProbeSpider):
        def parse(self, response):
            text = " ".join(response.css("h1::text, h2::text, p::text, li::text").getall())
            collector.append({"case_id": response.meta["case_id"], "text": text, "url": response.url})

    process.crawl(CollectorSpider)
    process.start()  # blocking
    elapsed_ms = (time.perf_counter() - t0) * 1000

    # write
    from _fixtures import keyword_score, Probe
    p = Probe(tool="scrapy", case_id=cid)
    if not collector:
        p.error = "no pages crawled"
    else:
        text = "\n".join(c["text"] for c in collector)
        hits, total = keyword_score(text, kws)
        p.ok = True
        p.keyword_hits = hits
        p.keyword_total = total
        p.chars_md = len(text)
        p.bytes_out = len(text.encode())
        p.n_results = len(collector)
    p.latency_ms = elapsed_ms
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps([{
        "tool": p.tool, "case_id": p.case_id, "ok": p.ok, "error": p.error,
        "latency_ms": p.latency_ms, "chars_md": p.chars_md, "keyword_hits": p.keyword_hits,
        "keyword_total": p.keyword_total, "n_results": p.n_results, "bytes_out": p.bytes_out,
    }], default=str))


def main():
    results = []
    for cid, url, kws in CORPUS:
        out = Path(__file__).parent.parent / "results" / f"scrapy_{cid}.json"
        print(f"  [{cid}] {url[:50]:<50} ", end="", flush=True)
        # run in subprocess so Twisted reactor is fresh
        code = f"""
import sys
sys.path.insert(0, {str(Path(__file__).parent)!r})
from test_scrapy import _worker
_worker({cid!r}, {url!r}, {kws!r}, {str(out)!r})
"""
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
                           env={**__import__('os').environ, "HTTPS_PROXY": "http://127.0.0.1:7897", "HTTP_PROXY": "http://127.0.0.1:7897"})
        if r.returncode != 0:
            print(f"err: subprocess exit {r.returncode}: {r.stderr[:100]}")
            results.append(Probe(tool="scrapy", case_id=cid, error=f"subprocess: {r.stderr[:80]}"))
            continue
        try:
            data = json.loads(out.read_text())[0]
            p = Probe(**{k: data.get(k, "") if k == "error" else data.get(k, 0) for k in ["tool","case_id","ok","error","latency_ms","chars_md","keyword_hits","keyword_total","n_results","bytes_out"]})
            # safer: rebuild from dict
            from dataclasses import asdict
            p = Probe(
                tool=data["tool"], case_id=data["case_id"], ok=data["ok"],
                error=data.get("error",""), latency_ms=data.get("latency_ms",0),
                chars_md=data.get("chars_md",0), keyword_hits=data.get("keyword_hits",0),
                keyword_total=data.get("keyword_total",0), n_results=data.get("n_results",0),
                bytes_out=data.get("bytes_out",0),
            )
            print(f"ok={p.ok}  lat={p.latency_ms:6.0f}ms  chars={p.chars_md:6d}  kw={p.keyword_hits}/{p.keyword_total}")
            results.append(p)
            if p.error:
                print(f"        err: {p.error[:100]}")
        except Exception as e:
            print(f"parse err: {e}")
            results.append(Probe(tool="scrapy", case_id=cid, error=str(e)[:80]))

    save_results(results, str(Path(__file__).parent.parent / "results" / "scrapy.json"))


if __name__ == "__main__":
    main()
