"""“实际调用”面板的联调：浏览器从站点同源调用网关后面的真实 MCP 服务。
需要一个运行中的网关（Caddy + authcheck + office/time 服务），并提供环境变量：
  MARKET_E2E_BASE=http://localhost:18080/market/   MARKET_E2E_TOKEN=<MCP_AUTH_TOKENS 里的一个>
没设置时整个文件跳过。
"""
import os

import pytest
from playwright.sync_api import sync_playwright

BASE = os.environ.get("MARKET_E2E_BASE")
TOKEN = os.environ.get("MARKET_E2E_TOKEN")
pytestmark = pytest.mark.skipif(not (BASE and TOKEN), reason="需要 MARKET_E2E_BASE 和 MARKET_E2E_TOKEN")


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium"), args=["--no-sandbox"])
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context()
    pg = ctx.new_page()
    yield pg
    ctx.close()


def open_live(page, item):
    page.goto(f"{BASE}#/mcp/{item}/demo")
    page.wait_for_selector("button[data-pane=live]")
    page.click("button[data-pane=live]")


def run(page, token):
    page.fill("input[type=password]", token)
    page.click("button.primary:has-text('运行')")


def test_time_live_call_through_the_gateway(page):
    open_live(page, "mcp-time")
    run(page, TOKEN)
    page.wait_for_selector(".out .note.ok")
    out = page.inner_text(".out")
    assert "成功" in out and "Asia/Shanghai" in out and "datetime" in out


def test_wrong_token_is_reported_not_swallowed(page):
    open_live(page, "mcp-time")
    run(page, "definitely-wrong")
    page.wait_for_selector(".out .note.bad")
    assert "401" in page.inner_text(".out")


def test_empty_token_and_bad_json_are_caught_before_calling(page):
    open_live(page, "mcp-time")
    page.click("button.primary:has-text('运行')")
    assert "请先填写 token" in page.inner_text(".out")
    page.fill("input[type=password]", TOKEN)
    page.fill("textarea", "{not json")
    page.click("button.primary:has-text('运行')")
    assert "合法 JSON" in page.inner_text(".out")


def test_office_live_call_returns_a_working_download_link(page):
    open_live(page, "mcp-office")
    run(page, TOKEN)
    page.wait_for_selector(".out .note.ok")
    link = page.locator(".out a:has-text('下载')")
    assert link.count() == 1
    href = link.get_attribute("href")
    data = page.request.get(href).body()
    assert data[:2] == b"PK" and len(data) > 1000                    # 真的是一个 xlsx（zip）


def test_token_is_kept_in_session_storage_only(page):
    open_live(page, "mcp-time")
    run(page, TOKEN)
    page.wait_for_selector(".out .note.ok")
    assert page.evaluate("sessionStorage.getItem('market.token')") == TOKEN
    assert page.evaluate("localStorage.length") == 0 or TOKEN not in str(page.evaluate("JSON.stringify(Object.entries(localStorage))"))
