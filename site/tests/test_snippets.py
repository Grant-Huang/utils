"""页面上展示给外部服务的 Python 调用示例，必须是真的能跑的。
把站点的模板填好（和前端 app.js 里同样的替换），真的对一个 office 服务跑一遍。
"""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from catalog import ROOT, load_catalog  # noqa: E402


def render_snippet(url, env, tool, args):
    """与 site/src/app.js 里 mcpUsage() 的替换保持一致。"""
    tmpl = (ROOT / "site" / "snippets" / "python_client.py.tmpl").read_text(encoding="utf-8")
    args_json = json.dumps(args, indent=2).replace("\n", "\n" + " " * 26)
    return tmpl.replace("{{URL}}", url).replace("{{TOKEN_ENV}}", env).replace("{{TOOL}}", tool).replace("{{ARGS_JSON}}", args_json)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def office():
    port = free_port()
    env = {**os.environ, "PORT": str(port), "MCP_AUTH_TOKENS": "snippet-token"}
    p = subprocess.Popen(["node", "src/http/bridge.js"], cwd=ROOT / "servers" / "office", env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.2)
    else:
        p.kill()
        pytest.fail("office 服务没有起来")
    yield f"http://127.0.0.1:{port}/mcp"
    p.kill()


def run_snippet(code, token):
    r = subprocess.run([sys.executable, "-c", code], env={**os.environ, "UTILS_MCP_TOKEN": token}, capture_output=True, text=True, timeout=60)
    return r


def test_python_snippet_really_works_against_a_server(office):
    catalog, errs, _, _ = load_catalog(ROOT)
    item = next(i for i in catalog["items"] if i["id"] == "mcp-office")
    call = item["examples"]["calls"][0]
    r = run_snippet(render_snippet(office, "UTILS_MCP_TOKEN", call["tool"], call["arguments"]), "snippet-token")
    assert r.returncode == 0, r.stderr
    result = json.loads(r.stdout)["result"]
    assert not result.get("isError")
    assert any(c["type"] == "resource_link" for c in result["content"])             # 返回下载链接


def test_python_snippet_fails_clearly_with_a_wrong_token(office):
    r = run_snippet(render_snippet(office, "UTILS_MCP_TOKEN", "render_xlsx", {"document": {}}), "wrong")
    assert r.returncode != 0 and "401" in r.stderr


def test_python_snippet_needs_the_token_env_variable(office):
    code = render_snippet(office, "UTILS_MCP_TOKEN", "render_xlsx", {"document": {}})
    r = subprocess.run([sys.executable, "-c", code], env={k: v for k, v in os.environ.items() if k != "UTILS_MCP_TOKEN"}, capture_output=True, text=True)
    assert r.returncode != 0 and "UTILS_MCP_TOKEN" in r.stderr                      # token 只从环境变量读


@pytest.mark.skipif(not os.environ.get("MARKET_E2E_TOKEN"), reason="需要网关")
def test_snippet_parses_sse_responses_from_the_gateway():
    """time 服务（经 mcp-proxy）可能以 SSE 返回，示例代码要能处理。"""
    base = os.environ.get("MARKET_E2E_GATEWAY", "http://localhost:18080")
    code = render_snippet(base + "/time/mcp", "UTILS_MCP_TOKEN", "get_current_time", {"timezone": "Asia/Shanghai"})
    r = run_snippet(code, os.environ["MARKET_E2E_TOKEN"])
    assert r.returncode == 0, r.stderr
    assert "Asia/Shanghai" in r.stdout
