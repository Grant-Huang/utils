"""真实浏览器（Chromium）里的 UI 测试。
运行：pip install playwright pytest -r site/requirements.txt ；浏览器路径用环境变量 CHROMIUM（默认 /opt/pw-browsers/chromium）。
不依赖任何运行中的 MCP 服务；实际调用面板的联调见 test_live.py（需要网关）。
"""
import functools
import http.server
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


@pytest.fixture(scope="module")
def dist(tmp_path_factory):
    out = tmp_path_factory.mktemp("dist")
    subprocess.run([sys.executable, str(ROOT / "site" / "build.py"), "--out", str(out)], check=True, capture_output=True)
    return out


@pytest.fixture(scope="module")
def base(dist):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(dist))
    handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/"
    srv.shutdown()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium"), args=["--no-sandbox"])
        yield b
        b.close()


@pytest.fixture
def page(browser, base):
    ctx = browser.new_context(accept_downloads=True)
    pg = ctx.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.on("console", lambda m: pg.errors.append(m.text) if m.type == "error" else None)
    yield pg
    ctx.close()


@pytest.fixture(scope="module")
def cat(dist):
    return json.loads((dist / "data" / "catalog.json").read_text(encoding="utf-8"))


def of(cat, type_):
    return [i for i in cat["items"] if i["type"] == type_]


def first(items, pred, why):
    found = [i for i in items if pred(i)]
    if not found:
        pytest.skip(why)
    return found[0]


def go(page, base, hash_=""):
    page.goto(base + hash_)
    page.wait_for_selector("#app h1, #app .empty")


def test_home_shows_counts_and_no_js_errors(page, base, cat):
    go(page, base)
    tiles = page.locator(".tile .n").all_inner_texts()
    assert tiles == [str(len(of(cat, "mcp"))), str(len(of(cat, "skill")))]
    assert "外部服务怎么用" in page.inner_text("#app")
    assert page.errors == []


def test_mcp_list_cards_and_category_tabs(page, base, cat):
    mcps = of(cat, "mcp")
    go(page, base, "#/mcp")
    assert page.locator(".card").count() == len(mcps)
    cats = sorted({i["category"] for i in mcps})
    for c in cats:                                                                    # 每个有项目的分类都有一个 tab，筛选结果与数据一致
        page.click(f'[data-cat="{c}"]')
        assert page.locator(".card").count() == len([i for i in mcps if i["category"] == c])
    page.click('[data-cat="all"]')
    assert page.locator(".card").count() == len(mcps)
    assert page.locator(".tabs .tab").count() == len(cats) + 1                       # 只显示有内容的分类 + “全部”


def test_search_risk_and_demo_filters(page, base, cat):
    mcps = of(cat, "mcp")
    go(page, base, "#/mcp")
    target = mcps[0]
    page.fill('input[type=search]', target["id"])                                    # 按 id 搜索必然命中它
    assert target["id"] in page.locator(".card").evaluate_all("els => els.map(e => e.dataset.id)")
    page.fill('input[type=search]', "zzz-no-such-item")
    assert page.locator(".card").count() == 0 and "没有符合条件" in page.inner_text("#app")
    page.fill('input[type=search]', "")
    for risk in sorted({i["risk"] for i in mcps}):
        page.select_option("select", risk)
        want = sorted(i["id"] for i in mcps if i["risk"] == risk)
        assert sorted(page.locator(".card").evaluate_all("els => els.map(e => e.dataset.id)")) == want
    page.select_option("select", "all")
    page.check("text=只看有 demo 的")
    ids = sorted(page.locator(".card").evaluate_all("els => els.map(e => e.dataset.id)"))
    assert ids == sorted(i["id"] for i in mcps if i["hasDemo"])


def test_live_badge_only_on_items_that_can_really_be_called(page, base, cat):
    go(page, base, "#/mcp")
    live = page.locator('.card:has-text("可实际调用")').evaluate_all("els => els.map(e => e.dataset.id)")
    assert sorted(live) == sorted(i["id"] for i in of(cat, "mcp") if i.get("live"))


def test_mcp_detail_has_three_tabs_with_demo(page, base, cat):
    item = first(of(cat, "mcp"), lambda i: i["hasDemo"], "没有带 demo 的 MCP")
    go(page, base, f"#/mcp/{item['id']}")
    assert page.locator("[data-tab-link]").all_inner_texts() == ["详情", "调用说明", "Demo"]
    n = len(item["tools"])
    assert f"工具清单（{n}）" in page.inner_text("#app")
    assert page.locator("details.tool-item").count() == n
    assert item["tools"][0]["name"] in page.inner_text("#app")
    assert page.errors == []


def test_item_without_demo_only_has_two_tabs_and_demo_url_falls_back(page, base, cat):
    item = first(of(cat, "mcp"), lambda i: not i["hasDemo"], "所有 MCP 都有 demo")
    go(page, base, f"#/mcp/{item['id']}")
    assert page.locator("[data-tab-link]").all_inner_texts() == ["详情", "调用说明"]
    page.goto(base + f"#/mcp/{item['id']}/demo")
    page.wait_for_selector("#app h1")
    assert page.locator("[data-tab]").first.get_attribute("data-tab") == "detail"     # 没有 demo 就回到详情


def test_usage_tab_uses_base_url_and_switches_snippets(page, base, cat):
    item = first(of(cat, "mcp"), lambda i: i["tokenScope"] == "default", "没有普通 token 的 MCP")
    go(page, base, f"#/mcp/{item['id']}/usage")
    assert f"{base.rstrip('/')}{item['endpoint']}" in page.inner_text("#app")        # 默认用当前站点 origin
    page.fill("#base-url", "https://mcp.example.com")
    page.dispatch_event("#base-url", "change")
    page.wait_for_selector(f"text=https://mcp.example.com{item['endpoint']}")
    page.click("button.tab:has-text('curl')")        # 输入框刚失焦：这次点击不能因为重绘而丢失
    assert "Authorization: Bearer $UTILS_MCP_TOKEN" in page.inner_text(".snip")
    page.click("button.tab:has-text('Python')")
    code = page.inner_text(".snip")
    assert 'TOKEN = os.environ["UTILS_MCP_TOKEN"]' in code and item["examples"]["calls"][0]["tool"] in code
    assert "{{" not in code                                                       # 模板占位符都被替换了
    assert "外部服务调用" in page.inner_text("#app")


def test_browser_mcp_uses_the_dedicated_token_variable(page, base, cat):
    item = first(of(cat, "mcp"), lambda i: i["tokenScope"] == "browser", "没有专用通道的 MCP")
    go(page, base, f"#/mcp/{item['id']}/usage")
    assert "UTILS_BROWSER_TOKEN" in page.inner_text("#app")
    assert "专用" in page.inner_text("#app")


def test_replay_shows_steps_and_playback_reveals_them(page, base, cat):
    item = first(of(cat, "mcp"), lambda i: i["recordings"], "没有带录制的 MCP")
    rec = item["recordings"][0]
    n = len(rec["steps"])
    go(page, base, f"#/mcp/{item['id']}/demo")
    assert "真实调用" in page.inner_text("#app")
    assert page.locator(".step").count() == n
    assert page.locator(".step.tool_result.err").count() == len([s for s in rec["steps"] if s["type"] == "tool_result" and s["isError"]])
    page.click("button.primary:has-text('回放')")
    assert page.locator(".step:visible").count() < n                                # 回放开始后逐步显示
    page.click("button:has-text('全部显示')")
    assert page.locator(".step:visible").count() == n


def test_skill_replay_shows_the_skill_call(page, base, cat):
    item = first(of(cat, "skill"), lambda i: i["recordings"], "没有带录制的 Skill")
    go(page, base, f"#/skills/{item['id']}/demo")
    assert "真实的模型会话" in page.inner_text("#app")
    want = [s["tool"] for s in item["recordings"][0]["steps"] if s["type"] == "tool_call"]
    assert page.locator(".step.tool_call .who code").all_inner_texts() == want


def test_demo_tabs_for_item_with_replay_and_live(page, base, cat):
    item = first(of(cat, "mcp"), lambda i: i["recordings"] and i.get("live"), "没有同时有录制和实际调用的 MCP")
    go(page, base, f"#/mcp/{item['id']}/demo")
    assert page.locator("button[data-pane]").all_inner_texts() == ["录制回放", "实际调用"]
    page.click("button[data-pane=live]")
    assert page.locator("textarea").input_value().strip().startswith("{")
    assert page.locator("input[type=password]").count() == 1


def test_item_with_only_replay_has_no_live_pane(page, base, cat):
    item = first(of(cat, "mcp"), lambda i: i["recordings"] and not i.get("live"), "没有只有录制的 MCP")
    go(page, base, f"#/mcp/{item['id']}/demo")
    assert page.locator("button[data-pane]").all_inner_texts() == ["录制回放"]


def test_skill_without_recordings_has_no_demo_tab(page, base, cat):
    item = first(of(cat, "skill"), lambda i: not i["recordings"], "所有 Skill 都有录制")
    go(page, base, f"#/skills/{item['id']}")
    assert page.locator("[data-tab-link]").all_inner_texts() == ["详情", "调用说明"]
    assert "验证状态" in page.inner_text("#app")


def test_skill_usage_has_downloads_and_dependency_config(page, base, cat):
    item = first(of(cat, "skill"), lambda i: i["dependsOn"], "没有声明依赖的 Skill")
    go(page, base, f"#/skills/{item['id']}/usage")
    links = page.locator("a[download]").evaluate_all("els => els.map(e => e.getAttribute('href'))")
    assert links == [item["downloads"]["skill"]["file"], item["downloads"]["plugin"]["file"]]
    text = page.inner_text("#app")
    assert f".claude/skills/{item['skillName']}/SKILL.md" in text
    for dep in item["dependsOn"]:                                                     # 每个依赖的连接配置都给出
        assert next(i for i in cat["items"] if i["id"] == dep)["endpoint"] in text
    with page.expect_download() as d:
        page.click("a[download]:has-text('Skill 包')")
    assert d.value.suggested_filename == item["downloads"]["skill"]["file"].split("/")[-1]


def test_skill_detail_links_to_dependencies_and_shows_description(page, base, cat):
    item = first(of(cat, "skill"), lambda i: i["dependsOn"], "没有声明依赖的 Skill")
    dep = next(i for i in cat["items"] if i["id"] == item["dependsOn"][0])
    go(page, base, f"#/skills/{item['id']}")
    assert item["skillDescription"][:40] in page.inner_text("#app")
    page.click(f".chip[href='#/mcp/{dep['id']}']")
    page.wait_for_selector(f"h1:has-text('{dep['title']}')")
    assert "被这些 Skill 使用" in page.inner_text("#app")


def test_xss_in_data_is_not_executed(page, base, dist, cat):
    victim = of(cat, "mcp")[0]["id"]
    # 把一个恶意标题/描述写进构建出的数据，页面必须把它当文本
    p = dist / "data" / "catalog.json"
    original = p.read_text(encoding="utf-8")
    cat = json.loads(original)
    evil = '<img src=x onerror="window.__pwned=1">'
    for it in cat["items"]:
        if it["id"] == victim:
            it["title"] = evil
            it["summary"] = evil
            it["tools"][0]["description"] = evil
    p.write_text(json.dumps(cat, ensure_ascii=False), encoding="utf-8")
    try:
        go(page, base, "#/mcp")
        go(page, base, f"#/mcp/{victim}")
        assert page.evaluate("window.__pwned") is None
        assert evil in page.inner_text("#app")                                       # 作为文本显示
    finally:
        p.write_text(original, encoding="utf-8")          # 还原，避免影响其他测试


def test_unknown_route_shows_not_found(page, base):
    go(page, base, "#/mcp/does-not-exist")
    assert "没有找到" in page.inner_text("#app")
