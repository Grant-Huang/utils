"""模拟编程工具新增项目的完整流程：脚手架 → 校验必须失败（TODO / 缺文件）→ 补全 → 校验通过。"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from catalog import ROOT, load_catalog  # noqa: E402

SCRIPT = ROOT / "scripts" / "market" / "new_item.py"


@pytest.fixture
def repo(tmp_path):
    for rel in ("plugins", ".claude-plugin", "site/taxonomy.json", "site/config.json", "site/snippets"):
        src, dst = ROOT / rel, tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree if src.is_dir() else shutil.copy2)(src, dst)
    return tmp_path


def scaffold(repo, *args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], env={"MARKET_ROOT": str(repo), "PATH": "/usr/bin:/bin"}, capture_output=True, text=True)


def errors(repo):
    return load_catalog(repo)[1]


MCP_ARGS = ["mcp", "mcp-echo", "--title", "Echo 服务", "--summary", "回显一段文字", "--category", "utility", "--origin", "third-party",
            "--risk", "low", "--risk-note", "只做回显，无副作用", "--endpoint", "/echo/mcp", "--server-name", "echo",
            "--upstream-name", "echo-mcp", "--upstream-version", "1.0.0", "--upstream-license", "MIT", "--upstream-url", "https://example.com/echo"]


def test_new_mcp_is_rejected_until_it_is_really_filled_in(repo):
    r = scaffold(repo, *MCP_ARGS)
    assert r.returncode == 0, r.stderr
    errs = errors(repo)
    assert any("TODO(" in e for e in errs)                                            # 占位符没填
    assert any("tools.json" in e for e in errs)                                       # 没有从真实服务生成的工具清单
    assert not any("marketplace.json" in e or "没有列入" in e for e in errs)           # 已自动加入集市

    # "编程工具"补全内容：工具清单应来自真实服务；这里借用 mcp-time 的快照代表"已经跑过 snapshot_tools.py"
    pdir = repo / "plugins" / "mcp-echo"
    snap = json.loads((repo / "plugins/mcp-time/market/tools.json").read_text(encoding="utf-8"))
    (pdir / "market" / "tools.json").write_text(json.dumps(snap), encoding="utf-8")
    (pdir / "market" / "detail.md").write_text("## 它能做什么\n\n回显文字。\n\n## 实测结果\n\n未实测。\n", encoding="utf-8")
    (pdir / "market" / "examples.json").write_text(json.dumps({"calls": [
        {"title": "查时间", "tool": "get_current_time", "arguments": {"timezone": "UTC"}}]}), encoding="utf-8")
    assert errors(repo) == []
    catalog = load_catalog(repo)[0]
    item = next(i for i in catalog["items"] if i["id"] == "mcp-echo")
    assert item["endpoint"] == "/echo/mcp" and item["upstream"]["version"] == "1.0.0" and not item["hasDemo"]


def test_new_skill_depends_on_existing_mcp_and_gets_downloads(repo):
    assert scaffold(repo, *MCP_ARGS).returncode == 0
    r = scaffold(repo, "skill", "skill-echo-helper", "--title", "Echo 助手", "--summary", "教模型用 echo", "--category", "research", "--depends", "mcp-echo")
    assert r.returncode == 0, r.stderr
    assert any("TODO(" in e for e in errors(repo))
    sk = repo / "plugins/skill-echo-helper"
    assert (sk / "skills/echo-helper/SKILL.md").exists()                              # skill 名 = 插件名去掉 skill- 前缀
    (sk / "skills/echo-helper/SKILL.md").write_text(
        "---\nname: echo-helper\ndescription: Use when the user wants text echoed back. Use the echo MCP tools.\n---\n\n# Echo\n\n回显。\n", encoding="utf-8")
    (sk / "market/detail.md").write_text("## 验证状态\n\n尚未验证。\n", encoding="utf-8")
    (sk / "market/examples.json").write_text(json.dumps({"prompts": ["把这句话回显给我"]}), encoding="utf-8")
    # 依赖的 mcp-echo 还没补全 → 校验仍然失败；补全后才通过
    assert any("mcp-echo" in e for e in errors(repo))
    pdir = repo / "plugins/mcp-echo"
    shutil.copy2(repo / "plugins/mcp-time/market/tools.json", pdir / "market/tools.json")
    (pdir / "market/detail.md").write_text("## x\n\n已填。\n", encoding="utf-8")
    (pdir / "market/examples.json").write_text(json.dumps({"calls": [{"title": "t", "tool": "get_current_time", "arguments": {"timezone": "UTC"}}]}), encoding="utf-8")
    catalog, errs, _, downloads = load_catalog(repo, build_downloads=True)
    assert errs == []
    assert "skill-echo-helper-skill.zip" in downloads
    assert next(i for i in catalog["items"] if i["id"] == "mcp-echo")["usedBy"] == ["skill-echo-helper"]


@pytest.mark.parametrize("patch, expect", [
    (["--category", "nope"], "category"),
    (["--origin", "self", "--upstream-version", ""], None),            # 自研不要求 upstream，应当成功（下面单独断言）
])
def test_scaffold_rejects_bad_category(repo, patch, expect):
    args = list(MCP_ARGS)
    for i in range(0, len(patch), 2):
        args[args.index(patch[i]) + 1] = patch[i + 1]
    r = scaffold(repo, *args)
    if expect:
        assert r.returncode != 0 and expect in r.stderr
    else:
        assert r.returncode == 0                                       # origin=self 时不需要 upstream


def test_scaffold_rejects_bad_names_and_missing_pieces(repo):
    bad_name = MCP_ARGS.copy(); bad_name[1] = "echo"
    assert "mcp-" in scaffold(repo, *bad_name).stderr                    # 必须以 mcp- 开头
    reserved = MCP_ARGS.copy(); reserved[1] = "claude-echo"
    assert scaffold(repo, *reserved).returncode != 0                     # 保留名
    no_up = [a for a in MCP_ARGS if a not in ("--upstream-version", "1.0.0")]
    r = scaffold(repo, *no_up)
    assert r.returncode != 0 and "upstream" in r.stderr                  # 第三方必须给出钉死的版本
    no_note = [a for a in MCP_ARGS if a not in ("--risk-note", "只做回显，无副作用")]
    assert scaffold(repo, *no_note).returncode != 0
    assert scaffold(repo, *MCP_ARGS).returncode == 0
    assert "已存在" in scaffold(repo, *MCP_ARGS).stderr                  # 不覆盖已有插件
