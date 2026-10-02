"""最小的 MCP over HTTP 客户端（只用标准库）：供快照、录制脚本共用。

兼容两种响应：application/json 与 text/event-stream；兼容有状态服务（Mcp-Session-Id）。
不做任何"帮你修正"：服务返回什么就原样返回，录制脚本要靠它保证真实。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

PROTOCOL_VERSION = "2025-06-18"


class McpHttpError(RuntimeError):
    pass


def _parse(body: bytes, content_type: str):
    text = body.decode("utf-8", "replace")
    if "text/event-stream" in content_type:
        for line in text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:])
        raise McpHttpError("event-stream response without data line")
    return json.loads(text) if text.strip() else {}


class McpClient:
    def __init__(self, url: str, token: str | None = None, timeout: float = 60.0, extra_headers: dict | None = None):
        self.url, self.timeout = url, timeout
        self.headers = {"content-type": "application/json", "accept": "application/json, text/event-stream"}
        if token:
            self.headers["authorization"] = f"Bearer {token}"
        self.headers.update(extra_headers or {})
        self._id = 0
        self.server_info: dict = {}
        self.protocol_version: str | None = None

    def _post(self, payload: dict):
        req = urllib.request.Request(self.url, json.dumps(payload).encode(), self.headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                sid = r.headers.get("mcp-session-id")
                if sid:
                    self.headers["mcp-session-id"] = sid
                body = r.read()
                return _parse(body, r.headers.get("content-type", "")) if body else {}
        except urllib.error.HTTPError as e:
            raise McpHttpError(f"HTTP {e.code} from {self.url}: {e.read()[:200].decode('utf-8', 'replace')}") from None
        except urllib.error.URLError as e:
            raise McpHttpError(f"cannot reach {self.url}: {e.reason}") from None

    def request(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            msg["params"] = params
        out = self._post(msg)
        if "error" in out:
            raise McpHttpError(f"{method}: {out['error']}")
        return out.get("result", {})

    def initialize(self) -> dict:
        res = self.request("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                          "clientInfo": {"name": "market-tools", "version": "1"}})
        self.server_info = res.get("serverInfo", {})
        self.protocol_version = res.get("protocolVersion")
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return res

    def list_tools(self) -> list[dict]:
        tools, cursor = [], None
        while True:
            res = self.request("tools/list", {"cursor": cursor} if cursor else {})
            tools += res.get("tools", [])
            cursor = res.get("nextCursor")
            if not cursor:
                return tools

    def call_tool(self, name: str, arguments: dict) -> dict:
        return self.request("tools/call", {"name": name, "arguments": arguments})
