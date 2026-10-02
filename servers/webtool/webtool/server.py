"""webtool MCP server —— 把 webtool 的 search → rerank → fetch 管线暴露成 MCP 工具。

两种运行方式：
  python -m webtool.server                       # stdio，本机被 MCP 客户端拉起
  python -m webtool.server --transport http      # Streamable HTTP，部署给别人用（端点 /mcp）

HTTP 模式的环境变量（与 servers/office 保持同一套约定）：
  MCP_AUTH_TOKENS      逗号分隔的 Bearer token，至少一个；未设置则拒绝启动
  MCP_ALLOW_NO_AUTH=1  显式关闭鉴权（仅限本机调试）
  MCP_ALLOWED_HOSTS    逗号分隔，允许的 Host 头（防 DNS rebinding），例如 "mcp.example.com"
  MCP_ALLOWED_ORIGINS  逗号分隔，允许的 Origin 头
  HOST / PORT          监听地址，默认 127.0.0.1:8912
业务相关：
  WEBTOOL_PROXY        搜索 / plain 抓取使用的代理（未设置则直连）
  WEBTOOL_MAX_CONCURRENCY  同时进行的搜索任务数，默认 2（crawl4ai/playwright 很吃内存）
  WEBTOOL_PRELOAD=1    启动时预加载 cross-encoder，避免首个请求冷启动
"""
from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import os
import sys

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .core import DEFAULTS, run

mcp = MCPServer(
    "webtool",
    instructions=(
        "Web search + page fetch. Call `web_search` with a query; it searches, reranks the hits "
        "and returns the cleaned markdown of the top pages together with their URLs."
    ),
)

# 限制并发：每个请求都可能拉起浏览器 / 加载模型，不限制容易把机器打满
_SEM = asyncio.Semaphore(int(os.environ.get("WEBTOOL_MAX_CONCURRENCY", "2")))


@mcp.tool()
async def web_search(
    query: str,
    search_top: int = DEFAULTS["search_top"],
    rerank_k: int = DEFAULTS["rerank_k"],
    rerank: str = DEFAULTS["rerank"],
    fetch: str = DEFAULTS["fetch"],
    search_backend: str = DEFAULTS["search_backend"],
    max_chars_per_page: int = 8000,
) -> str:
    """Search the web, rerank the hits, fetch the top pages and return their content as markdown.

    Args:
        query: search query.
        search_top: how many search hits to retrieve (1-30).
        rerank_k: how many hits to keep after reranking and fetch (1-10).
        rerank: "cross" (cross-encoder, best), "lexical" (cheap) .
        fetch: "crawl4ai" (default), "playwright" (JS-heavy pages) or "plain" (fastest).
        search_backend: "duckduckgo", "searxng" or "brave".
        max_chars_per_page: truncate each page's content to this many characters.
    """
    # 参数校验：远程调用者的输入不可信
    if not query.strip():
        raise ToolError("query must not be empty")
    if not 1 <= search_top <= 30:
        raise ToolError("search_top must be in 1..30")
    if not 1 <= rerank_k <= 10:
        raise ToolError("rerank_k must be in 1..10")
    if rerank not in ("cross", "lexical"):
        raise ToolError("rerank must be 'cross' or 'lexical'")
    if fetch not in ("crawl4ai", "playwright", "plain"):
        raise ToolError("fetch must be crawl4ai | playwright | plain")
    if search_backend not in ("duckduckgo", "searxng", "brave"):
        raise ToolError("search_backend must be duckduckgo | searxng | brave")
    max_chars_per_page = max(500, min(max_chars_per_page, 50000))

    async with _SEM:
        # run() 是同步的，内部会 asyncio.run 抓取；放进线程，避免嵌套事件循环并且不阻塞服务
        result = await asyncio.to_thread(
            run, query,
            search_top=search_top, rerank_k=rerank_k, rerank=rerank, fetch=fetch,
            search_backend=search_backend, keep_content=True,
        )

    # 失败要让调用方（模型）看到：ToolError → MCP 返回 isError=true 且带消息
    if result.error:
        raise ToolError(result.error)
    if not result.pages:
        raise ToolError("search succeeded but no page could be fetched")

    parts = [f"# Results for: {query}\n"]
    for i, p in enumerate(result.pages, 1):
        content = p.get("content", "")
        truncated = len(content) > max_chars_per_page
        parts.append(f"## [{i}] {p['title'] or p['domain']}\nURL: {p['url']}\n")
        parts.append(content[:max_chars_per_page] + ("\n\n…[truncated]" if truncated else ""))
        parts.append("")
    return "\n".join(parts)


# ---------------------------------------------------------------- HTTP 部署


def _csv(name: str) -> list[str]:
    return [x.strip() for x in os.environ.get(name, "").split(",") if x.strip()]


class _AuthASGI:
    """纯 ASGI 中间件：/health 免鉴权，其余请求要求 `Authorization: Bearer <token>`。

    不用 BaseHTTPMiddleware，避免干扰 SSE 流式响应。token 用常量时间比较。
    """

    def __init__(self, app, tokens: list[str]):
        self.app, self.tokens = app, tokens

    async def _reply(self, send, status: int, body: dict, headers=()):
        raw = json.dumps(body).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), *headers]})
        await send({"type": "http.response.body", "body": raw})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if scope["path"] == "/health":
            return await self._reply(send, 200, {"ok": True, "server": "webtool"})
        if self.tokens:
            auth = dict(scope["headers"]).get(b"authorization", b"").decode()
            supplied = auth[7:] if auth.lower().startswith("bearer ") else ""
            if not any(hmac.compare_digest(supplied, t) for t in self.tokens):
                return await self._reply(send, 401, {"error": "unauthorized"},
                                         [(b"www-authenticate", b"Bearer")])
        return await self.app(scope, receive, send)


def build_http_app():
    """构造带鉴权 + Host/Origin 校验的 ASGI app（也供测试直接使用）。"""
    from mcp.server.transport_security import TransportSecuritySettings

    tokens = _csv("MCP_AUTH_TOKENS")
    if not tokens and os.environ.get("MCP_ALLOW_NO_AUTH") != "1":
        raise SystemExit("refusing to start HTTP server without auth: set MCP_AUTH_TOKENS "
                         "(or MCP_ALLOW_NO_AUTH=1 for local debugging)")

    hosts, origins = _csv("MCP_ALLOWED_HOSTS"), _csv("MCP_ALLOWED_ORIGINS")
    port = os.environ.get("PORT", "8912")
    # 本机访问始终放行；对外域名通过 MCP_ALLOWED_HOSTS 追加
    hosts += [f"127.0.0.1:{port}", f"localhost:{port}", "127.0.0.1", "localhost"]
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins)

    # stateless_http：多实例 / 反向代理后无需会话粘滞
    app = mcp.streamable_http_app(stateless_http=True, json_response=True, transport_security=security)
    return _AuthASGI(app, tokens)


def _warmup() -> None:
    """可选：预加载 cross-encoder（README 记录冷启动约 37s）。"""
    from .core import Reranker
    from sentence_transformers import CrossEncoder
    Reranker._CE = CrossEncoder(DEFAULTS["model"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="webtool.server")
    ap.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    args = ap.parse_args(argv)

    if os.environ.get("WEBTOOL_PRELOAD") == "1":
        _warmup()

    if args.transport == "stdio":
        mcp.run("stdio")
        return 0

    import uvicorn
    uvicorn.run(build_http_app(), host=os.environ.get("HOST", "127.0.0.1"),
                port=int(os.environ.get("PORT", "8912")), log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
