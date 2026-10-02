"""数据层测试：真实仓库必须零错误；每条校验规则都用"故意写错"的反向用例证明它真的会拦住。
运行：pip install -r site/requirements.txt pytest && pytest site/tests/test_catalog.py
"""
import hashlib
import json
import shutil
import sys
import zipfile
import io
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from catalog import ROOT, load_catalog  # noqa: E402


@pytest.fixture
def repo(tmp_path):
    """真实仓库里与集市有关的部分的副本，可以随意改。"""
    for rel in ("plugins", ".claude-plugin", "site/taxonomy.json", "site/config.json", "site/snippets"):
        src, dst = ROOT / rel, tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree if src.is_dir() else shutil.copy2)(src, dst)
    return tmp_path


def errors_of(repo):
    _, errs, _, _ = load_catalog(repo)
    return errs


def edit_json(path: Path, fn):
    data = json.loads(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_real_repo_has_no_errors():
    catalog, errs, warns, _ = load_catalog(ROOT)
    assert errs == [], errs
    for w in warns:                                   # 警告不让测试失败（新增项目可能有合理的警告），但要让人看见
        print("警告:", w)
    assert {i["type"] for i in catalog["items"]} == {"mcp", "skill"}


def test_unlisted_plugin_directory_is_an_error(repo):
    edit_json(repo / ".claude-plugin/marketplace.json", lambda d: d["plugins"].pop())
    assert any("没有列入" in e for e in errors_of(repo))


def test_listed_but_missing_directory_is_an_error(repo):
    shutil.rmtree(repo / "plugins/mcp-time")
    assert any("没有这个目录" in e for e in errors_of(repo))


def test_unknown_category(repo):
    edit_json(repo / "plugins/mcp-time/.claude-plugin/plugin.json", lambda d: d["metadata"]["market"].update(category="nope"))
    assert any("category" in e and "taxonomy" in e for e in errors_of(repo))


def test_missing_required_market_fields(repo):
    edit_json(repo / "plugins/mcp-time/.claude-plugin/plugin.json", lambda d: d["metadata"]["market"].pop("riskNote"))
    assert any("riskNote" in e for e in errors_of(repo))


def test_third_party_requires_pinned_upstream_version(repo):
    edit_json(repo / "plugins/mcp-time/.claude-plugin/plugin.json", lambda d: d["metadata"]["market"]["upstream"].pop("version"))
    assert any("upstream.version" in e for e in errors_of(repo))


def test_example_arguments_are_validated_against_the_tool_schema(repo):
    # get_current_time 要求 timezone；去掉它必须被发现，防止示例和真实工具脱节
    edit_json(repo / "plugins/mcp-time/market/examples.json", lambda d: d["calls"][0]["arguments"].clear())
    assert any("不符合工具 schema" in e for e in errors_of(repo))


def test_example_for_unknown_tool(repo):
    edit_json(repo / "plugins/mcp-time/market/examples.json", lambda d: d["calls"][0].update(tool="no_such_tool"))
    assert any("不在 tools.json" in e for e in errors_of(repo))


def test_mcp_json_must_match_endpoint(repo):
    p = repo / "plugins/mcp-time/.mcp.json"
    p.write_text(p.read_text(encoding="utf-8").replace("/time/mcp", "/wrong/mcp"), encoding="utf-8")
    assert any(".mcp.json 的 url" in e for e in errors_of(repo))


def test_hardcoded_token_in_mcp_json_is_rejected(repo):
    p = repo / "plugins/mcp-time/.mcp.json"
    p.write_text(p.read_text(encoding="utf-8").replace("${UTILS_MCP_TOKEN}", "abcdef123456"), encoding="utf-8")
    assert any("token 只放环境变量" in e for e in errors_of(repo))


def test_browser_scope_requires_the_browser_token_variable(repo):
    p = repo / "plugins/mcp-browser/.mcp.json"
    p.write_text(p.read_text(encoding="utf-8").replace("UTILS_BROWSER_TOKEN", "UTILS_MCP_TOKEN"), encoding="utf-8")
    assert any("UTILS_BROWSER_TOKEN" in e for e in errors_of(repo))


def test_missing_detail_and_tools(repo):
    (repo / "plugins/mcp-time/market/detail.md").unlink()
    (repo / "plugins/mcp-time/market/tools.json").unlink()
    errs = errors_of(repo)
    assert any("detail.md" in e for e in errs) and any("tools.json" in e for e in errs)


def test_skill_dependency_must_exist_and_be_mcp(repo):
    edit_json(repo / "plugins/skill-web-research/.claude-plugin/plugin.json", lambda d: d.update(dependencies=["mcp-nope"]))
    assert any("不在集市里" in e for e in errors_of(repo))
    edit_json(repo / "plugins/skill-web-research/.claude-plugin/plugin.json", lambda d: d.update(dependencies=["skill-office-reports"]))
    assert any("不是 MCP 插件" in e for e in errors_of(repo))


def test_skill_name_must_match_directory_and_have_description(repo):
    p = repo / "plugins/skill-web-research/skills/web-research/SKILL.md"
    text = p.read_text(encoding="utf-8")
    p.write_text(text.replace("name: web-research", "name: other", 1), encoding="utf-8")
    assert any("必须与目录名" in e for e in errors_of(repo))
    p.write_text("\n".join(l for l in text.split("\n") if not l.startswith("description:")), encoding="utf-8")
    assert any("description" in e for e in errors_of(repo))


def test_recording_with_unknown_tool_or_bad_schema(repo):
    rp = repo / "plugins/mcp-time/market/recordings/shanghai-and-convert.json"
    edit_json(rp, lambda d: d["steps"][0].update(tool="ghost"))
    assert any("ghost" in e for e in errors_of(repo))
    edit_json(rp, lambda d: d.update(schema=2))
    assert any("schema 必须是 1" in e for e in errors_of(repo))


def test_recording_must_not_contain_a_token(repo):
    rp = repo / "plugins/mcp-time/market/recordings/shanghai-and-convert.json"
    edit_json(rp, lambda d: d["steps"][1]["content"].append({"type": "text", "text": "Authorization: Bearer sk-live-1234567890abcdef"}))
    assert any("明文 token" in e for e in errors_of(repo))


def test_recording_kind_must_match_item_type(repo):
    edit_json(repo / "plugins/mcp-time/market/recordings/shanghai-and-convert.json", lambda d: d.update(kind="skill"))
    assert any("不一致" in e for e in errors_of(repo))


def test_unpaired_tool_result_is_rejected(repo):
    edit_json(repo / "plugins/mcp-time/market/recordings/shanghai-and-convert.json", lambda d: d["steps"].pop(0))
    assert any("没有对应的 tool_call" in e for e in errors_of(repo))


def test_skill_recording_without_skill_call_warns(repo):
    rp = repo / "plugins/skill-office-reports/market/recordings/xlsx-with-colors.json"
    edit_json(rp, lambda d: d.update(steps=[s for s in d["steps"] if not (s["type"] == "tool_call" and s["tool"] == "Skill")]))
    # 去掉 Skill 调用后 tool_result 配对会错位；这里只关心"没展示 Skill"的提示
    _, _, warns, _ = load_catalog(repo)
    assert any("没有调用 Skill" in w for w in warns)


def test_markdown_raw_html_is_escaped(repo):
    (repo / "plugins/mcp-time/market/detail.md").write_text("## x\n\n<script>alert(1)</script> [bad](javascript:alert(1)) **ok**", encoding="utf-8")
    catalog, errs, _, _ = load_catalog(repo)
    item = next(i for i in catalog["items"] if i["id"] == "mcp-time")
    assert "<script" not in item["detailHtml"]
    assert 'href="javascript:' not in item["detailHtml"]
    assert "<strong>ok</strong>" in item["detailHtml"]


def test_dependency_back_references(repo):
    catalog, _, _, _ = load_catalog(repo)
    by = {i["id"]: i for i in catalog["items"]}
    for skill in (i for i in catalog["items"] if i["type"] == "skill"):
        for dep in skill["dependsOn"]:
            assert skill["id"] in by[dep]["usedBy"]
    for mcp in (i for i in catalog["items"] if i["type"] == "mcp"):
        assert mcp["usedBy"] == sorted(s["id"] for s in catalog["items"] if mcp["id"] in s["dependsOn"])


def test_downloads_are_deterministic_and_well_formed(repo):
    a, errs, _, dl1 = load_catalog(repo, build_downloads=True)
    assert errs == []
    _, _, _, dl2 = load_catalog(repo, build_downloads=True)
    assert {k: hashlib.sha256(v).hexdigest() for k, v in dl1.items()} == {k: hashlib.sha256(v).hexdigest() for k, v in dl2.items()}
    names = zipfile.ZipFile(io.BytesIO(dl1["skill-web-research-skill.zip"])).namelist()
    assert names == ["web-research/SKILL.md"]                      # 解压到 .claude/skills/ 即可用
    plugin = zipfile.ZipFile(io.BytesIO(dl1["skill-web-research-plugin.zip"])).namelist()
    assert ".claude-plugin/plugin.json" in plugin and "skills/web-research/SKILL.md" in plugin
    assert not any(n.startswith("market/") for n in plugin)       # 站点专用内容不进插件包
    item = next(i for i in a["items"] if i["id"] == "skill-web-research")
    assert item["downloads"]["skill"]["sha256"] == hashlib.sha256(dl1["skill-web-research-skill.zip"]).hexdigest()
