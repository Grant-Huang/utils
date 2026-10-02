# Webtool

可配置的 web search + fetch CLI，参数由 N×k factorial benchmark 调优。

## 默认值（= benchmark 最佳配置）

| 参数 | 默认 | 来源 |
|---|---|---|
| `search_top` | 10 | DDG HTML 翻页失败，只能稳定拿 ~10 |
| `rerank` | cross | `cross-encoder/ms-marco-MiniLM-L-6-v2`，score +0.01 over lexical |
| `rerank_k` | 6 | 甜区：score 0.87，P50 24s，多样性 5.2 |
| `fetch` | crawl4ai | Apache-2.0，7/7 通过，chars 干净 |
| `search_backend` | duckduckgo | 无 key；CN 网络需设置 `WEBTOOL_PROXY` |

## 用法

```bash
# 默认（最佳配置）
python -m webtool "Python asyncio task cancellation" --keywords asyncio,cancel

# 调整参数
python -m webtool "武汉 天气" \
  --search-top 10 \
  --rerank-k 6 \
  --rerank cross \
  --fetch crawl4ai \
  --search-backend duckduckgo \
  --out-md report.md \
  --out-json report.json

# 跳过 rerank（用 search 原序）
python -m webtool "query" --no-rerank

# 切换 fetch 引擎
python -m webtool "query" --fetch playwright   # JS-heavy 页
python -m webtool "query" --fetch plain         # 最快，纯 HTML

# 切换 rerank 模型
python -m webtool "query" --model cross-encoder/ms-marco-MiniLM-L-12-v2
```

## 输出

### Markdown (`--out-md report.md`)
包含：
- 配置 + summary
- **Domain distribution 可视化条形图**
- Pages 表格
- **Composite score 6 维拆解**（kw / diversity / speed / efficiency）

### JSON (`--out-json report.json`)
完整结构化数据，含每页的 url / domain / title / snippet / chars / kw_hits。

## 代理

代理**不再硬编码**，由环境变量提供（未设置则直连）：

```bash
export WEBTOOL_PROXY=http://127.0.0.1:7897   # 兼容旧名 WEBBENCH_PROXY
```

作用于搜索（DuckDuckGo / SearXNG / Brave）和 `--fetch plain`；`crawl4ai` / `playwright` 目前不走该代理。

## MCP server

```bash
pip install ".[rerank,crawl4ai]"                  # 重依赖按需装，见 pyproject.toml
python -m webtool.server                          # stdio
MCP_AUTH_TOKENS=$(openssl rand -hex 32) python -m webtool.server --transport http   # http://127.0.0.1:8912/mcp
```

工具 `web_search(query, search_top, rerank_k, rerank, fetch, search_backend, max_chars_per_page)`：搜索 → rerank → 抓取，返回前 k 个页面的 markdown 正文和 URL。失败以 `isError` 返回。
HTTP 模式没有 token 会拒绝启动；`MCP_ALLOWED_HOSTS` / `MCP_ALLOWED_ORIGINS` / `HOST` / `PORT` 约定与 office 相同，另有 `WEBTOOL_MAX_CONCURRENCY`、`WEBTOOL_PRELOAD`。
`GET /health` 公开。运行测试：`pip install -e ".[dev]" && pytest`。

## 项目结构

```
servers/webtool/
├── pyproject.toml
├── webtool/
│   ├── __main__.py         # CLI
│   ├── server.py           # MCP server（stdio / Streamable HTTP）
│   ├── core.py             # WebResult, Reranker, run()
│   ├── search_provider.py  # 搜索后端适配层（DDG / SearXNG / Brave）
│   └── render.py           # markdown 可视化
├── tests/test_server.py    # MCP 层单元测试
└── benchmarks/             # N×k factorial benchmark 的脚本与结果（非运行时）
```

## 依赖

核心：`mcp`, `httpx`, `uvicorn`, `trafilatura`, `markdownify`。可选 extras：`crawl4ai`、`playwright`、`rerank`（sentence-transformers）、`all`。

## 局限

1. **DDG HTML 只能稳定拿 10 条**：要 N=20+ 需换 Brave API 或 SearXNG 自部署
2. **rerank 模型冷启动 37s**（首次下载 ~90MB），之后 warm 状态
3. **跨页关键词覆盖是 best-effort**：需要 `--keywords` 显式指定才会算 coverage 指标
4. **CJK query 需要 proxy**：DDG 在 CN 直连不可用（设置 `WEBTOOL_PROXY`）
5. 抓取目前是串行的（每个 URL 一次 `asyncio.run`），延迟主要来自这里；MCP 层用线程池隔离，但没有并发抓取

## 复现 / 调参建议

- 想「快」：加 `--no-rerank --rerank-k 4`
- 想「深」：`--rerank-k 10 --fetch crawl4ai`
- 想「便宜」：`--rerank lexical --fetch plain`
- 想要 Brave：`--search-backend brave`（需 `BRAVE_API_KEY`）
