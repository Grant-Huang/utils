"""webtool.server 的单元测试：鉴权 / Host 校验 / 工具列表 / 工具调用。
用假的 run()，不联网、不加载浏览器或模型。"""
import pytest
from starlette.testclient import TestClient

import webtool.server as srv
from webtool.core import WebResult

HDRS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}


def rpc(client, method, params=None, id=1, **kw):
    return client.post("/mcp", json={"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}},
                       headers={**HDRS, **kw.pop("headers", {})}, **kw)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKENS", "secret-a,secret-b")
    monkeypatch.setenv("PORT", "8912")
    with TestClient(srv.build_http_app(), base_url="http://127.0.0.1:8912") as c:
        yield c


AUTH = {"authorization": "Bearer secret-a"}


def test_refuses_to_start_without_auth(monkeypatch):
    monkeypatch.delenv("MCP_AUTH_TOKENS", raising=False)
    monkeypatch.delenv("MCP_ALLOW_NO_AUTH", raising=False)
    with pytest.raises(SystemExit):
        srv.build_http_app()


def test_health_is_public(client):
    assert client.get("/health").json() == {"ok": True, "server": "webtool"}


@pytest.mark.parametrize("hdr", [{}, {"authorization": "Bearer wrong"}, {"authorization": "Basic secret-a"}])
def test_mcp_requires_valid_bearer(client, hdr):
    assert rpc(client, "tools/list", headers=hdr).status_code == 401


def test_second_token_also_works(client):
    r = rpc(client, "tools/list", headers={"authorization": "Bearer secret-b"})
    assert r.status_code == 200


def test_bad_host_rejected(client):
    r = rpc(client, "tools/list", headers={**AUTH, "host": "evil.example.com"})
    assert r.status_code in (400, 403, 421)


def test_tools_list(client):
    tools = rpc(client, "tools/list", headers=AUTH).json()["result"]["tools"]
    assert [t["name"] for t in tools] == ["web_search", "read_url"]
    assert "query" in tools[0]["inputSchema"]["required"]


def _fake_result():
    r = WebResult(query="q", search_backend="duckduckgo", search_top=10, rerank_method="lexical",
                  rerank_k=6, fetch_engine="plain")
    r.pages = [{"url": "https://a.test/x", "domain": "a.test", "title": "A", "snippet": "",
                "chars": 5000, "kw_hits": 0, "kw_total": 0, "content": "x" * 5000}]
    return r


def test_call_returns_markdown_and_truncates(client, monkeypatch):
    seen = {}
    def fake_run(query, **kw):
        seen.update(kw); return _fake_result()
    monkeypatch.setattr(srv, "run", fake_run)
    r = rpc(client, "tools/call", {"name": "web_search", "arguments": {"query": "q", "max_chars_per_page": 1000}},
            headers=AUTH).json()["result"]
    text = r["content"][0]["text"]
    assert not r.get("isError")
    assert "URL: https://a.test/x" in text and "…[truncated]" in text
    assert seen["keep_content"] is True          # MCP 层必须要正文


def test_error_is_reported_as_is_error(client, monkeypatch):
    res = _fake_result(); res.error = "search: boom"; res.pages = []
    monkeypatch.setattr(srv, "run", lambda q, **kw: res)
    r = rpc(client, "tools/call", {"name": "web_search", "arguments": {"query": "q"}}, headers=AUTH).json()["result"]
    assert r["isError"] is True and "boom" in r["content"][0]["text"]


def test_invalid_argument_is_error(client):
    r = rpc(client, "tools/call", {"name": "web_search", "arguments": {"query": "q", "fetch": "curl"}},
            headers=AUTH).json()["result"]
    assert r["isError"] is True


# ---------------------------------------------------------------- read_url
def _call_read_url(client, **args):
    return rpc(client, "tools/call", {"name": "read_url", "arguments": args}, headers=AUTH).json()["result"]


def test_tools_list_has_read_url(client):
    names = [t["name"] for t in rpc(client, "tools/list", headers=AUTH).json()["result"]["tools"]]
    assert names == ["web_search", "read_url"]


def test_read_url_returns_markdown_and_truncates(client, monkeypatch):
    monkeypatch.setattr(srv, "check_url", lambda u: u)                   # DNS 不在本测试范围
    seen = {}
    def fake(url, engine, guard):
        seen.update(url=url, engine=engine, guard=guard)
        return True, "x" * 5000, "https://a.test/final"
    monkeypatch.setattr(srv, "fetch_page_ex", fake)
    r = _call_read_url(client, url="https://a.test/x", max_chars=1000)
    text = r["content"][0]["text"]
    assert not r.get("isError") and text.startswith("URL: https://a.test/final") and "…[truncated]" in text
    assert seen["guard"] is True                                          # 必须开启逐跳校验


@pytest.mark.parametrize("url", ["http://127.0.0.1/admin", "http://169.254.169.254/latest/meta-data", "file:///etc/passwd",
                                 "http://localhost:6379/"])
def test_read_url_blocks_internal_targets_without_fetching(client, monkeypatch, url):
    called = []
    monkeypatch.setattr(srv, "fetch_page_ex", lambda *a, **k: called.append(a) or (True, "secret", url))
    r = _call_read_url(client, url=url)
    assert r["isError"] is True and not called                            # 根本没发起抓取


def test_read_url_discards_content_if_redirected_internally(client, monkeypatch):
    # 入口 URL 是公网，但浏览器类引擎被重定向到了内网：内容必须被丢弃
    monkeypatch.setattr(srv, "check_url", lambda u: u if "public" in u else (_ for _ in ()).throw(ValueError("non-public")))
    monkeypatch.setattr(srv, "fetch_page_ex", lambda u, e, g: (True, "INTERNAL SECRET PAGE", "http://10.0.0.5/admin"))
    r = _call_read_url(client, url="https://public.test/redirector")
    assert r["isError"] is True and "INTERNAL SECRET" not in r["content"][0]["text"]


def test_read_url_hides_internal_exception_details(client, monkeypatch):
    monkeypatch.setattr(srv, "check_url", lambda u: u)
    def boom(*a): raise RuntimeError("proxy http://corp-proxy.internal:3128 refused")
    monkeypatch.setattr(srv, "fetch_page_ex", boom)
    r = _call_read_url(client, url="https://a.test/")
    assert r["isError"] is True and "corp-proxy" not in r["content"][0]["text"]


def test_read_url_rejects_bad_engine(client):
    assert _call_read_url(client, url="https://a.test/", fetch="curl")["isError"] is True
