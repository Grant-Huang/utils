"""authcheck 单测：纯逻辑 + 真实 HTTP 往返。运行：cd deploy/authcheck && pytest"""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import authcheck as ac


def chk(**kw):
    return ac.Checker(kw.get("tokens", ["tok-a", "tok-b"]), kw.get("origins", []), kw.get("limit", 3))


def test_valid_tokens_pass():
    assert chk().check({"Authorization": "Bearer tok-a"})[0] == 200
    assert chk().check({"Authorization": "bearer tok-b"})[0] == 200      # scheme 大小写不敏感


@pytest.mark.parametrize("h", [{}, {"Authorization": "Bearer nope"}, {"Authorization": "Basic tok-a"}, {"Authorization": "Bearer "}])
def test_bad_credentials_rejected(h):
    assert chk().check(h)[0] == 401


def test_origin_must_be_allowed_when_present():
    c = chk(origins=["https://app.example.com"])
    ok = {"Authorization": "Bearer tok-a"}
    assert c.check({**ok, "Origin": "https://evil.example"})[0] == 403
    assert c.check({**ok, "Origin": "https://app.example.com"})[0] == 200
    assert c.check(ok)[0] == 200                                         # 无 Origin（非浏览器）放行


def test_same_origin_is_allowed_but_cross_site_is_not():
    c = chk()                                   # 白名单为空
    ok = {"Authorization": "Bearer tok-a"}
    same = {**ok, "Origin": "https://mcp.example.com", "Host": "mcp.example.com"}
    assert c.check(same)[0] == 200                                               # 站点和 MCP 同域
    assert c.check({**ok, "Origin": "https://mcp.example.com", "X-Forwarded-Host": "mcp.example.com"})[0] == 200
    assert c.check({**ok, "Origin": "https://evil.example", "Host": "mcp.example.com"})[0] == 403
    assert c.check({**ok, "Origin": "https://mcp.example.com.evil.example", "Host": "mcp.example.com"})[0] == 403
    assert c.check({**ok, "Origin": "https://mcp.example.com"})[0] == 403          # 拿不到 Host 就不放行


def test_rate_limit_is_per_token_and_per_minute():
    c = chk(limit=2)
    a = {"Authorization": "Bearer tok-a"}
    assert [c.check(a, now=0)[0] for _ in range(3)] == [200, 200, 429]
    assert c.check({"Authorization": "Bearer tok-b"}, now=0)[0] == 200  # 另一个 token 不受影响
    assert c.check(a, now=60)[0] == 200                                  # 下一分钟重置


def test_browser_scope_is_separate_from_default_tokens():
    c = ac.Checker(["tok-a"], [], 100, scopes={"browser": ["br-1"]})
    assert c.check({"Authorization": "Bearer tok-a"}, scope="browser")[0] == 401   # 普通 token 不能进专用通道
    assert c.check({"Authorization": "Bearer br-1"}, scope="browser")[0] == 200
    assert c.check({"Authorization": "Bearer br-1"})[0] == 401                     # 专用 token 也不能进普通通道
    assert c.check({"Authorization": "Bearer tok-a"}, scope="nope")[0] == 403


def test_browser_scope_closed_when_no_browser_tokens():
    c = ac.Checker(["tok-a"], [], 100, scopes={"browser": []})
    assert c.check({"Authorization": "Bearer tok-a"}, scope="browser")[0] == 401
    assert c.check({"Authorization": "Bearer "}, scope="browser")[0] == 401        # 空 token 不能匹配空列表


def test_http_roundtrip_and_no_token_in_response():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), ac.make_handler(chk()))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        req = urllib.request.Request(base + "/check", headers={"Authorization": "Bearer tok-a"})
        assert urllib.request.urlopen(req).status == 200
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(urllib.request.Request(base + "/check"))
        assert e.value.code == 401 and e.value.headers["www-authenticate"] == "Bearer"
        assert json.load(urllib.request.urlopen(base + "/health"))["ok"] is True
        with pytest.raises(urllib.error.HTTPError) as e2:                          # scope 经查询串传入
            urllib.request.urlopen(urllib.request.Request(base + "/check?scope=browser", headers={"Authorization": "Bearer tok-a"}))
        assert e2.value.code == 403
    finally:
        srv.shutdown()


def test_refuses_to_start_without_tokens(monkeypatch):
    monkeypatch.delenv("MCP_AUTH_TOKENS", raising=False)
    with pytest.raises(SystemExit):
        ac.main()
