"""集市的数据层：读取仓库里的插件，校验，生成 catalog。build.py 和 `--check` 都用它。

单一数据源是仓库本身：
  .claude-plugin/marketplace.json          收录哪些插件
  plugins/<name>/.claude-plugin/plugin.json  名称、版本、dependencies、metadata.market（分类/风险等结构化字段）
  plugins/<name>/.mcp.json                 MCP 插件的连接配置
  plugins/<name>/skills/<skill>/SKILL.md   Skill 插件的正文
  plugins/<name>/market/                   站点专用内容：detail.md、examples.json、tools.json、recordings/*.json
字段规范见 .claude/skills/add-market-item/reference.md。

load_catalog() 返回 (catalog, errors, warnings)；errors 非空时 build 会失败。
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "market"))
import recording as REC  # noqa: E402

# html=False：Markdown 里的原始 HTML 一律转义，不会被浏览器当作标签执行
_md = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SECRET_RE = re.compile(r"Bearer\s+(?!\$|<|\{)[A-Za-z0-9._~+/=-]{8,}")
ORIGINS = {"self", "third-party"}
TOKEN_SCOPES = {"default", "browser"}


def render_md(text: str) -> str:
    return _md.render(text)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def parse_frontmatter(text: str) -> dict:
    """只支持简单的 `key: value`（单行）。SKILL.md 的 name / description 都是单行。"""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    out: dict = {}
    if m:
        for line in m.group(1).splitlines():
            k, sep, v = line.partition(":")
            if sep:
                out[k.strip()] = v.strip()
    return out


def deterministic_zip(files: list[tuple[str, bytes]]) -> bytes:
    """同样的输入得到同样的字节（固定时间戳、排序、固定权限），便于对比和缓存。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files):
            zi = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            zi.external_attr = 0o644 << 16
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, data)
    return buf.getvalue()


def collect_files(base: Path, rel_to: Path, prefix: str = "", skip_dirs: tuple[str, ...] = ()) -> list[tuple[str, bytes]]:
    out = []
    for p in sorted(base.rglob("*")):
        if p.is_file() and not any(part in skip_dirs for part in p.relative_to(base).parts):
            out.append((prefix + p.relative_to(rel_to).as_posix(), p.read_bytes()))
    return out


def load_catalog(root: Path = ROOT, build_downloads: bool = False):
    errors: list[str] = []
    warnings: list[str] = []
    err = lambda where, msg: errors.append(f"{where}: {msg}")          # noqa: E731
    warn = lambda where, msg: warnings.append(f"{where}: {msg}")       # noqa: E731

    taxonomy = read_json(root / "site" / "taxonomy.json")
    config = read_json(root / "site" / "config.json")
    market_file = root / ".claude-plugin" / "marketplace.json"
    marketplace = read_json(market_file)
    listed = {p["name"]: p for p in marketplace.get("plugins", [])}

    plugin_dirs = {d.name: d for d in sorted((root / "plugins").iterdir()) if d.is_dir()}
    for n in plugin_dirs:
        if n not in listed:
            err(f"plugins/{n}", "目录存在但没有列入 .claude-plugin/marketplace.json")
    for n in listed:
        if n not in plugin_dirs:
            err(f"marketplace.json:{n}", "列入了集市但 plugins/ 下没有这个目录")

    items: dict[str, dict] = {}
    downloads: dict[str, bytes] = {}          # 文件名 → 内容

    for name, d in plugin_dirs.items():
        where = f"plugins/{name}"
        pj_path = d / ".claude-plugin" / "plugin.json"
        if not pj_path.exists():
            err(where, "缺少 .claude-plugin/plugin.json")
            continue
        pj = read_json(pj_path)
        if pj.get("name") != name:
            err(where, f"plugin.json 的 name（{pj.get('name')}）必须与目录名一致")
        if name in listed and listed[name].get("name") != pj.get("name"):
            err(where, "marketplace.json 里的 name 必须与 plugin.json 一致")
        mk = (pj.get("metadata") or {}).get("market")
        if not isinstance(mk, dict):
            err(where, "plugin.json 缺少 metadata.market")
            continue

        typ = mk.get("type")
        if typ not in ("mcp", "skill"):
            err(where, "metadata.market.type 必须是 mcp 或 skill")
            continue
        if typ == "mcp" and not name.startswith("mcp-"):
            warn(where, "MCP 插件建议以 mcp- 开头")
        if typ == "skill" and not name.startswith("skill-"):
            warn(where, "Skill 插件建议以 skill- 开头")
        for k in ("title", "summary", "category"):
            if not isinstance(mk.get(k), str) or not mk[k].strip():
                err(where, f"metadata.market.{k} 必填")
        cats = {c["key"] for c in taxonomy[typ]}
        if mk.get("category") not in cats:
            err(where, f"category {mk.get('category')!r} 不在 taxonomy.json 的 {typ} 分类里：{sorted(cats)}")
        if not isinstance(mk.get("tags", []), list):
            err(where, "tags 必须是数组")

        market_dir = d / "market"
        detail_md = market_dir / "detail.md"
        if not detail_md.exists():
            err(where, "缺少 market/detail.md（详情页内容）")
        ex_path = market_dir / "examples.json"
        examples = read_json(ex_path) if ex_path.exists() else {}
        if not ex_path.exists():
            err(where, "缺少 market/examples.json")

        item = {
            "id": name, "type": typ, "title": mk.get("title"), "summary": mk.get("summary"),
            "category": mk.get("category"), "tags": mk.get("tags", []), "version": pj.get("version"),
            "description": pj.get("description"),
            "detailHtml": render_md(detail_md.read_text(encoding="utf-8")) if detail_md.exists() else "",
            "dependsOn": [], "usedBy": [], "recordings": [],
        }
        usage_extra = market_dir / "usage.md"
        item["usageExtraHtml"] = render_md(usage_extra.read_text(encoding="utf-8")) if usage_extra.exists() else ""

        # ---------------- MCP 专属 ----------------
        if typ == "mcp":
            risks = {r["key"] for r in taxonomy["risk"]}
            if mk.get("origin") not in ORIGINS:
                err(where, f"origin 必须是 {sorted(ORIGINS)}")
            if mk.get("risk") not in risks:
                err(where, f"risk 必须是 {sorted(risks)}")
            if not mk.get("riskNote"):
                err(where, "riskNote 必填（一句话说明风险和缓解）")
            if mk.get("tokenScope") not in TOKEN_SCOPES:
                err(where, f"tokenScope 必须是 {sorted(TOKEN_SCOPES)}")
            ep = mk.get("endpoint", "")
            if not (ep.startswith("/") and ep.endswith("/mcp")):
                err(where, "endpoint 形如 /office/mcp")
            if mk.get("origin") == "third-party":
                up = mk.get("upstream") or {}
                for k in ("name", "version", "license", "url"):
                    if not up.get(k):
                        err(where, f"第三方 MCP 的 upstream.{k} 必填（版本用我们钉死的包版本，不用服务自报的）")
            # .mcp.json 与 endpoint / token 范围一致
            mcp_path = d / ".mcp.json"
            if not mcp_path.exists():
                err(where, "缺少 .mcp.json")
            else:
                servers = read_json(mcp_path).get("mcpServers", {})
                if len(servers) != 1:
                    err(where, ".mcp.json 必须恰好定义一个服务")
                for sname, sc in servers.items():
                    if sc.get("url") != "${UTILS_MCP_URL}" + ep:
                        err(where, f".mcp.json 的 url 应为 ${{UTILS_MCP_URL}}{ep}，实际 {sc.get('url')!r}")
                    want = "UTILS_BROWSER_TOKEN" if mk.get("tokenScope") == "browser" else "UTILS_MCP_TOKEN"
                    if sc.get("headers", {}).get("Authorization") != "Bearer ${%s}" % want:
                        err(where, f".mcp.json 的 Authorization 应为 Bearer ${{{want}}}（token 只放环境变量）")
                    item["serverName"] = sname
            item.update({k: mk.get(k) for k in ("origin", "risk", "riskNote", "endpoint", "tokenScope", "upstream", "live")})
            item["toolPrefix"] = f"mcp__plugin_{name}_{item.get('serverName', '')}__"

            tools_path = market_dir / "tools.json"
            tools: dict[str, dict] = {}
            if not tools_path.exists():
                err(where, "缺少 market/tools.json（用 scripts/market/snapshot_tools.py 从真实服务生成）")
            else:
                snap = read_json(tools_path)
                tools = {t["name"]: t for t in snap.get("tools", [])}
                if not tools:
                    err(where, "tools.json 里没有工具")
                item["tools"] = snap.get("tools", [])
                item["snapshot"] = {"at": snap.get("snapshotAt"), "server": snap.get("server"),
                                    "protocolVersion": snap.get("protocolVersion")}
            calls = examples.get("calls", [])
            if not calls:
                err(where, "examples.json 至少要有一个 calls 示例")
            for i, c in enumerate(calls):
                t = tools.get(c.get("tool"))
                if tools and t is None:
                    err(where, f"examples.calls[{i}] 的工具 {c.get('tool')!r} 不在 tools.json 里")
                elif t is not None:
                    try:
                        jsonschema.validate(c.get("arguments", {}), t.get("inputSchema", {}))
                    except jsonschema.ValidationError as e:
                        err(where, f"examples.calls[{i}]（{c['tool']}）的参数不符合工具 schema：{e.message[:120]}")
            item["examples"] = {"calls": calls}
            live = mk.get("live")
            if live:
                idx = live.get("example")
                if not isinstance(idx, int) or not (0 <= idx < len(calls)):
                    err(where, "live.example 必须是 examples.calls 的下标")
                elif calls[idx].get("tool") != live.get("tool"):
                    err(where, "live.tool 必须与 live.example 指向的示例工具一致")

        # ---------------- Skill 专属 ----------------
        else:
            deps = [(x if isinstance(x, str) else x.get("name")) for x in pj.get("dependencies", [])]
            item["dependsOn"] = deps
            if not deps:
                warn(where, "Skill 没有声明依赖的 MCP（dependencies）")
            sk_dirs = sorted(p for p in (d / "skills").glob("*") if p.is_dir()) if (d / "skills").is_dir() else []
            if len(sk_dirs) != 1:
                err(where, "Skill 插件必须在 skills/ 下恰好有一个 Skill 目录")
            else:
                skill_md = sk_dirs[0] / "SKILL.md"
                if not skill_md.exists():
                    err(where, f"缺少 {skill_md.relative_to(root)}")
                else:
                    text = skill_md.read_text(encoding="utf-8")
                    fm = parse_frontmatter(text)
                    if fm.get("name") != sk_dirs[0].name:
                        err(where, f"SKILL.md 的 name（{fm.get('name')}）必须与目录名（{sk_dirs[0].name}）一致")
                    if not fm.get("description"):
                        err(where, "SKILL.md 缺少 description（模型靠它决定是否触发，要写清楚何时使用）")
                    item["skillName"] = sk_dirs[0].name
                    item["skillFullName"] = f"{name}:{sk_dirs[0].name}"
                    item["skillDescription"] = fm.get("description", "")
                    item["skillSource"] = text
                    if build_downloads:
                        skill_zip = deterministic_zip(collect_files(sk_dirs[0], sk_dirs[0].parent))
                        plugin_zip = deterministic_zip(collect_files(d, d, skip_dirs=("market",)))
                        for kind, blob in (("skill", skill_zip), ("plugin", plugin_zip)):
                            fname = f"{name}-{kind}.zip"
                            downloads[fname] = blob
                            item.setdefault("downloads", {})[kind] = {
                                "file": f"downloads/{fname}", "bytes": len(blob),
                                "sha256": hashlib.sha256(blob).hexdigest()}
            prompts = examples.get("prompts", [])
            if not prompts:
                err(where, "examples.json 至少要有一个 prompts 示例提问")
            item["examples"] = {"prompts": prompts}

        # ---------------- 录制 ----------------
        rec_dir = market_dir / "recordings"
        seen = set()
        for rp in sorted(rec_dir.glob("*.json")) if rec_dir.is_dir() else []:
            rwhere = f"{where}/market/recordings/{rp.name}"
            try:
                rec = read_json(rp)
            except json.JSONDecodeError as e:
                err(rwhere, f"不是合法 JSON：{e}")
                continue
            for e in REC.validate(rec):
                err(rwhere, e)
            if rec.get("id") != rp.stem:
                err(rwhere, "录制的 id 必须与文件名一致")
            if rec.get("id") in seen:
                err(rwhere, "录制 id 重复")
            seen.add(rec.get("id"))
            if rec.get("kind") != typ:
                err(rwhere, f"录制的 kind（{rec.get('kind')}）与项目类型（{typ}）不一致")
            if typ == "mcp":
                known = set(item.get("tools") and [t["name"] for t in item["tools"]] or [])
                for s in rec.get("steps", []):
                    if s.get("type") == "tool_call" and known and s.get("tool") not in known:
                        err(rwhere, f"录制里调用的工具 {s.get('tool')!r} 不在 tools.json 里")
            elif typ == "skill":
                if not any(s.get("type") == "tool_call" and s.get("tool") == "Skill" for s in rec.get("steps", [])):
                    warn(rwhere, "这份 Skill 录制里模型没有调用 Skill 工具——它没有展示这个 Skill，建议不要作为演示")
            raw = rp.read_text(encoding="utf-8")
            if SECRET_RE.search(raw):
                err(rwhere, "录制里疑似出现明文 token（Bearer 后面跟了真实字符串）")
            item["recordings"].append(rec)

        for f in sorted(market_dir.rglob("*")) if market_dir.is_dir() else []:
            if f.is_file() and f.suffix in (".md", ".json") and SECRET_RE.search(f.read_text(encoding="utf-8")):
                err(f"{where}/market/{f.relative_to(market_dir)}", "疑似出现明文 token")
        # 脚手架生成的占位符必须全部填完：不允许把 TODO( 提交上线
        for f in sorted(d.rglob("*")):
            rel = f.relative_to(d).parts
            if f.is_file() and f.suffix in (".md", ".json") and rel[:2] != ("market", "recordings") and f.name != "tools.json":
                if "TODO(" in f.read_text(encoding="utf-8"):
                    err(f"{where}/{'/'.join(rel)}", "还有没填完的 TODO( 占位符")
        item["hasDemo"] = bool(item["recordings"]) or bool(item.get("live"))
        items[name] = item

    # 依赖关系：dependsOn 必须是存在的 MCP 插件；反向填 usedBy
    for name, it in items.items():
        for dep in it["dependsOn"]:
            target = items.get(dep)
            if target is None:
                err(f"plugins/{name}", f"依赖的 {dep!r} 不在集市里")
            elif target["type"] != "mcp":
                err(f"plugins/{name}", f"依赖的 {dep!r} 不是 MCP 插件")
            else:
                target["usedBy"].append(name)
    for it in items.values():
        it["usedBy"].sort()

    snippets = {"python": (root / "site" / "snippets" / "python_client.py.tmpl").read_text(encoding="utf-8")}
    catalog = {
        "snippets": snippets,
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config": config, "taxonomy": taxonomy,
        "marketplace": {"name": marketplace.get("name"), "description": marketplace.get("description")},
        "items": sorted(items.values(), key=lambda x: (x["type"], x["category"] or "", x["id"])),
    }
    return catalog, errors, warnings, downloads
