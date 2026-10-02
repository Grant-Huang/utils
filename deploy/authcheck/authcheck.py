"""authcheck —— 给第三方 MCP server 做统一入口鉴权（供 Caddy forward_auth 调用）。

第三方 server（markitdown / docling / excel / chart / duckdb / playwright / time）自己不带或不可靠地带鉴权，
所以在 Caddy 前置一层：每个请求先转给本服务，返回 2xx 才放行，否则原样把 401/403/429 返回给调用方。
只用标准库，没有第三方依赖。

环境变量（与 office / webtool 同一套约定）：
  MCP_AUTH_TOKENS      逗号分隔的 Bearer token；未设置则拒绝启动
  MCP_ALLOWED_ORIGINS  逗号分隔；请求带 Origin 头时必须在其中（防浏览器跨站调用）
  MCP_BROWSER_TOKENS   专用通道 scope=browser 的 token（Playwright 这类高权限工具）；
                       与 MCP_AUTH_TOKENS 互不通用，未设置则该通道一律 403
  RATE_LIMIT_PER_MIN   每个 token 每分钟请求数，默认 120
  PORT                 默认 9000

Caddy 通过 `forward_auth authcheck:9000 { uri /check?scope=browser }` 选择 scope，默认 scope 为 default。
"""
import hmac
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


def csv(name):
    return [x.strip() for x in os.environ.get(name, "").split(",") if x.strip()]


class Checker:
    """纯逻辑，便于单测：给定请求头 → (状态码, 原因)。"""

    def __init__(self, tokens, origins, limit_per_min, scopes=None):
        # scopes: {"browser": [token, ...]}；default scope 用 tokens。不同 scope 的 token 互不通用
        self.scopes = {"default": tokens, **(scopes or {})}
        self.origins, self.limit = origins, limit_per_min
        self._win = {}                 # token -> (分钟序号, 计数)
        self._lock = threading.Lock()

    def check(self, headers, now=None, scope="default"):
        if scope not in self.scopes:
            return 403, "unknown scope"
        origin = headers.get("Origin")
        if origin and origin not in self.origins:
            return 403, "origin not allowed"
        auth = headers.get("Authorization", "")
        supplied = auth[7:] if auth.lower().startswith("bearer ") else ""
        # 逐个常量时间比较，找出匹配的 token（同时用作限流的 key）
        matched = next((t for t in self.scopes[scope] if hmac.compare_digest(supplied, t)), None)
        if matched is None:
            return 401, "unauthorized"
        minute = int((now if now is not None else time.time()) // 60)
        with self._lock:
            key = (scope, matched)
            m, n = self._win.get(key, (minute, 0))
            n = n + 1 if m == minute else 1
            self._win[key] = (minute, n)
        if n > self.limit:
            return 429, "rate limit exceeded"
        return 200, "ok"


def make_handler(checker):
    class H(BaseHTTPRequestHandler):
        def _reply(self, code, body, extra=()):
            raw = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(raw)))
            for k, v in extra:
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(raw)

        def handle_any(self):
            if urlparse(self.path).path == "/health":
                return self._reply(200, {"ok": True, "server": "authcheck"})
            scope = parse_qs(urlparse(self.path).query).get("scope", ["default"])[0]
            code, why = checker.check(self.headers, scope=scope)
            extra = [("www-authenticate", "Bearer")] if code == 401 else [("retry-after", "60")] if code == 429 else []
            self._reply(code, {"ok": code == 200, "error": None if code == 200 else why}, extra)

        do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = do_OPTIONS = handle_any

        def log_message(self, fmt, *args):      # 日志里不能出现 Authorization，只记状态
            sys.stderr.write("authcheck %s %s\n" % (self.command, args[1] if len(args) > 1 else ""))
    return H


def main():
    tokens = csv("MCP_AUTH_TOKENS")
    if not tokens:
        raise SystemExit("refusing to start: set MCP_AUTH_TOKENS")
    checker = Checker(tokens, csv("MCP_ALLOWED_ORIGINS"), int(os.environ.get("RATE_LIMIT_PER_MIN", "120")),
                      scopes={"browser": csv("MCP_BROWSER_TOKENS")})
    port = int(os.environ.get("PORT", "9000"))
    ThreadingHTTPServer(("0.0.0.0", port), make_handler(checker)).serve_forever()


if __name__ == "__main__":
    main()
