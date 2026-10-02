#!/usr/bin/env python3
"""给集市新增一个 MCP 插件或 Skill 插件的脚手架：只生成骨架，不编造任何内容。

生成的骨架里有 `TODO(` 标记；`python site/build.py --check` 会把没填完的 TODO 当作错误，所以不会被漏提交。
tools.json（工具清单）和录制必须从真实服务生成，脚手架不会替你造。

用法：
  # MCP（自研）
  python scripts/market/new_item.py mcp mcp-foo --title "Foo 服务" --summary "一句话" \\
      --category utility --risk low --risk-note "只读，无副作用" --endpoint /foo/mcp --server-name foo --origin self
  # MCP（第三方）：必须给出我们钉死的上游版本
  python scripts/market/new_item.py mcp mcp-bar ... --origin third-party \\
      --upstream-name bar-mcp --upstream-version 1.2.3 --upstream-license MIT --upstream-url https://github.com/x/bar
  # Skill：--depends 填它依赖的 MCP 插件
  python scripts/market/new_item.py skill skill-baz --title "Baz 工作流" --summary "一句话" \\
      --category research --depends mcp-foo,mcp-bar

分类、风险等级见 site/taxonomy.json；字段规范见 .claude/skills/add-market-item/reference.md。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("MARKET_ROOT") or Path(__file__).resolve().parents[2])     # MARKET_ROOT 仅供测试
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("type", choices=["mcp", "skill"])
    ap.add_argument("name", help="插件名：MCP 以 mcp- 开头，Skill 以 skill- 开头；小写字母、数字、连字符；不能以 claude-/anthropic- 开头")
    ap.add_argument("--title", required=True)
    ap.add_argument("--summary", required=True, help="一句话简介（列表页卡片上显示）")
    ap.add_argument("--category", required=True, help="见 site/taxonomy.json")
    ap.add_argument("--tags", default="", help="逗号分隔")
    # MCP
    ap.add_argument("--origin", choices=["self", "third-party"])
    ap.add_argument("--risk", choices=["low", "medium", "high"])
    ap.add_argument("--risk-note", help="一句话说明风险与缓解")
    ap.add_argument("--endpoint", help="形如 /foo/mcp（经网关的路径）")
    ap.add_argument("--server-name", help=".mcp.json 里的服务名，如 foo")
    ap.add_argument("--token-scope", choices=["default", "browser"], default="default")
    ap.add_argument("--upstream-name"); ap.add_argument("--upstream-version")
    ap.add_argument("--upstream-license"); ap.add_argument("--upstream-url")
    # Skill
    ap.add_argument("--depends", default="", help="逗号分隔的 MCP 插件名")
    args = ap.parse_args(argv)

    taxonomy = json.loads((ROOT / "site" / "taxonomy.json").read_text(encoding="utf-8"))
    if args.category not in {c["key"] for c in taxonomy[args.type]}:
        sys.exit(f"category 必须是 {[c['key'] for c in taxonomy[args.type]]} 之一（要新分类就先改 site/taxonomy.json）")
    if not NAME_RE.match(args.name) or re.match(r"^(claude|anthropic|anthropics|cc-plugin)-", args.name):
        sys.exit("名字只能用小写字母/数字/连字符，且不能以 claude-、anthropic- 开头")
    if not args.name.startswith(args.type + "-"):
        sys.exit(f"{args.type} 插件的名字要以 {args.type}- 开头")
    pdir = ROOT / "plugins" / args.name
    if pdir.exists():
        sys.exit(f"{pdir} 已存在")
    market_file = ROOT / ".claude-plugin" / "marketplace.json"
    marketplace = json.loads(market_file.read_text(encoding="utf-8"))

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    market: dict = {"type": args.type, "title": args.title, "summary": args.summary, "category": args.category, "tags": tags}
    manifest = {"name": args.name, "version": "0.1.0", "description": args.summary,
                "author": {"name": "Grant Huang"}, "homepage": "https://github.com/Grant-Huang/utils",
                "repository": "https://github.com/Grant-Huang/utils", "keywords": [args.type] + tags}

    if args.type == "mcp":
        missing = [k for k in ("origin", "risk", "risk_note", "endpoint", "server_name") if not getattr(args, k)]
        if missing:
            sys.exit("MCP 必须提供：" + ", ".join("--" + m.replace("_", "-") for m in missing))
        if not (args.endpoint.startswith("/") and args.endpoint.endswith("/mcp")):
            sys.exit("--endpoint 形如 /foo/mcp")
        market.update(origin=args.origin, risk=args.risk, riskNote=args.risk_note, endpoint=args.endpoint, tokenScope=args.token_scope)
        if args.origin == "third-party":
            up = {"name": args.upstream_name, "version": args.upstream_version, "license": args.upstream_license, "url": args.upstream_url}
            if not all(up.values()):
                sys.exit("第三方 MCP 必须提供 --upstream-name/--upstream-version/--upstream-license/--upstream-url（版本用我们钉死的包版本，不要用服务自报的）")
            market["upstream"] = up
        env = "UTILS_BROWSER_TOKEN" if args.token_scope == "browser" else "UTILS_MCP_TOKEN"
        write_json(pdir / ".mcp.json", {"mcpServers": {args.server_name: {
            "type": "http", "url": "${UTILS_MCP_URL}" + args.endpoint, "headers": {"Authorization": "Bearer ${%s}" % env}}}})
        (pdir / "market").mkdir(parents=True, exist_ok=True)
        (pdir / "market" / "detail.md").write_text(
            "## 它能做什么\n\nTODO(填写：一两句话说明；只写你亲自验证过的事实)\n\n"
            "## 实测结果\n\nTODO(填写：你实际运行得到的结论；没实测的写明\"未实测\")\n\n"
            "## 安全与限制\n\nTODO(填写：能读什么、能访问什么网络、数据是否出站、需要怎样的隔离)\n", encoding="utf-8")
        write_json(pdir / "market" / "examples.json", {"calls": [
            {"title": "TODO(填写：示例标题)", "tool": "TODO(填写：工具名，必须在 tools.json 里)", "arguments": {}}]})
    else:
        deps = [d.strip() for d in args.depends.split(",") if d.strip()]
        manifest["dependencies"] = deps
        skill_name = args.name[len("skill-"):]
        sdir = pdir / "skills" / skill_name
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "SKILL.md").write_text(
            f"---\nname: {skill_name}\n"
            "description: TODO(填写：以 Use when 开头，写清楚什么请求该触发它；有对应 MCP 工具时要明确说“用这些工具，而不是自己写代码/文件”)\n---\n\n"
            f"# {args.title}\n\n"
            "TODO(填写：步骤、工具用法、已知限制。只写实测过的行为，没验证的明确标注)\n", encoding="utf-8")
        (pdir / "market").mkdir(parents=True, exist_ok=True)
        (pdir / "market" / "detail.md").write_text(
            "## 它教模型做什么\n\nTODO(填写)\n\n## 适用 / 不适用\n\nTODO(填写)\n\n## 依赖\n\nTODO(填写)\n\n"
            "## 验证状态\n\nTODO(填写：在真实模型会话里测过什么、结果如何；没测过就写\"尚未验证\")\n", encoding="utf-8")
        write_json(pdir / "market" / "examples.json", {"prompts": ["TODO(填写：一条用户会真的这么问的话)"]})

    manifest["metadata"] = {"market": market}
    write_json(pdir / ".claude-plugin" / "plugin.json", manifest)
    marketplace["plugins"].append({"name": args.name, "source": f"./plugins/{args.name}", "description": args.summary})
    write_json(market_file, marketplace)

    print(f"已创建 {pdir.relative_to(ROOT)}，并加入 .claude-plugin/marketplace.json。接下来：")
    if args.type == "mcp":
        print(f"  1. 让服务跑起来（见 servers/ 与 deploy/），然后：\n"
              f"     python scripts/market/snapshot_tools.py {args.name} --url <服务 /mcp 地址> [--token ...]")
        print("  2. 填写 market/detail.md、market/examples.json（把所有 TODO( 换成真实内容）")
        print(f"  3. 对能安全演示的调用做真实录制：python scripts/market/record_mcp.py {args.name} --help")
    else:
        print("  1. 填写 skills/…/SKILL.md、market/detail.md、market/examples.json（把所有 TODO( 换成真实内容）")
        print(f"  2. 真实录制并检查 Skill 是否被触发：python scripts/market/record_skill.py {args.name} --help")
    print("  校验：python site/build.py --check && claude plugin validate . && claude plugin validate ./plugins/" + args.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
