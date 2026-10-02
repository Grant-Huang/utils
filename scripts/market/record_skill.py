#!/usr/bin/env python3
"""对一个 Skill 做一次**真实**的会话录制：真的跑一次 `claude -p`（会产生模型调用费用），
把 stream-json 事件流转成 recording 格式，写入 plugins/<skill 插件>/market/recordings/<id>.json。

录制里包含：用户提问 → 模型是否调用了 Skill 工具 → 调用了哪些 MCP 工具（参数与结果）→ 最终回答。
这同时也是对"这个 Skill 会不会被触发"的一次真实检验：如果录制里没有出现 Skill 调用，就如实呈现。

前置：MCP 服务可达（本机网关或线上），并设置环境变量 UTILS_MCP_URL / UTILS_MCP_TOKEN（浏览器通道另需 UTILS_BROWSER_TOKEN），
插件里的 .mcp.json 会从环境变量读取它们。

用法：
  UTILS_MCP_URL=http://localhost:18080 UTILS_MCP_TOKEN=... python scripts/market/record_skill.py skill-office-reports \\
      --id xlsx-with-colors --title "生成带条件格式的 Excel" --prompt "..." \\
      --allow 'mcp__plugin_mcp-office_office__*' [--max-budget-usd 1.0] [--rewrite http://localhost:18080=https://mcp.example.com]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import recording as R  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def plugin_deps(plugin: str) -> list[str]:
    pj = json.loads((ROOT / "plugins" / plugin / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    deps = []
    for d in pj.get("dependencies", []):
        deps.append(d if isinstance(d, str) else d["name"])
    return deps


def short_tool_name(name: str) -> str:
    """mcp__plugin_mcp-office_office__render_xlsx → render_xlsx；其他（如 Skill）原样。"""
    return name.split("__")[-1] if name.startswith("mcp__") else name


def result_content(block: dict) -> list[dict]:
    c = block.get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    out = []
    for item in c or []:
        out.append({"type": "text", "text": item.get("text", "")} if item.get("type") == "text" else item)
    return out


def convert(events: list[dict], prompt: str) -> tuple[list[dict], dict]:
    """stream-json 事件 → (steps, stats)。"""
    steps: list[dict] = [{"type": "user", "text": prompt}]
    stats: dict = {}
    names: dict[str, str] = {}
    for ev in events:
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            stats["model"] = ev.get("model")
        elif t == "assistant":
            for b in ev.get("message", {}).get("content", []):
                if b.get("type") == "text" and b.get("text", "").strip():
                    steps.append({"type": "assistant", "text": b["text"]})
                elif b.get("type") == "tool_use":
                    names[b["id"]] = b["name"]
                    steps.append({"type": "tool_call", "tool": short_tool_name(b["name"]),
                                  "fullName": b["name"], "arguments": b.get("input", {})})
        elif t == "user":
            for b in ev.get("message", {}).get("content", []) if isinstance(ev.get("message", {}).get("content"), list) else []:
                if b.get("type") == "tool_result":
                    steps.append({"type": "tool_result", "isError": bool(b.get("is_error")),
                                  "content": result_content(b)})
        elif t == "result":
            stats["costUsd"] = ev.get("total_cost_usd")
            stats["durationMs"] = ev.get("duration_ms")
            stats["turns"] = ev.get("num_turns")
    return steps, stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plugin", help="Skill 插件名，例如 skill-office-reports")
    ap.add_argument("--id", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--description", default="")
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--allow", action="append", default=[], help="额外放行的工具（可重复），例如 'mcp__plugin_mcp-office_office__*'")
    ap.add_argument("--max-budget-usd", default="1.0")
    ap.add_argument("--rewrite", action="append", default=[], metavar="FROM=TO")
    args = ap.parse_args(argv)

    plugin_dir = ROOT / "plugins" / args.plugin
    if not (plugin_dir / "skills").is_dir():
        sys.exit(f"{args.plugin} 不是 Skill 插件")
    for var in ("UTILS_MCP_URL", "UTILS_MCP_TOKEN"):
        if not os.environ.get(var):
            sys.exit(f"请先设置环境变量 {var}")
    mapping = dict(r.split("=", 1) for r in args.rewrite)

    plugins = [args.plugin] + plugin_deps(args.plugin)
    cmd = ["claude", "-p", args.prompt, "--output-format", "stream-json", "--verbose", "--no-session-persistence",
           "--max-budget-usd", args.max_budget_usd,
           "--allowedTools", ",".join(["Skill"] + args.allow)]
    for p in plugins:
        cmd += ["--plugin-dir", str(ROOT / "plugins" / p)]

    with tempfile.TemporaryDirectory() as cwd:          # 空目录：避免读到仓库里的 CLAUDE.md / 项目 Skill
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=900)
    events = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    if not events:
        sys.exit(f"没有拿到事件流。stderr: {proc.stderr[-400:]}")

    steps, stats = convert(events, args.prompt)
    out_steps = []
    for s in steps:
        body = {k: v for k, v in s.items() if k != "type"}
        body, hit = R.truncate(R.rewrite_text(body, mapping))
        out_steps.append({"type": s["type"], **body, "truncated": hit})

    rec = {
        "schema": 1, "kind": "skill", "id": args.id, "title": args.title, "description": args.description,
        "recordedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {"plugins": plugins, "model": stats.get("model")},
        "normalized": [f"文本中的 {a} 改写为 {b}" for a, b in mapping.items()],
        "steps": out_steps, "stats": stats,
    }
    text = R.dump(rec)
    for secret in (os.environ["UTILS_MCP_TOKEN"], os.environ.get("UTILS_BROWSER_TOKEN", "")):
        if secret and secret in text:
            sys.exit("录制内容里出现了 token，已中止写入（请检查 --rewrite 或脱敏）")
    errs = R.validate(rec)
    if errs:
        sys.exit("录制不合法：" + "; ".join(errs))
    out = plugin_dir / "market" / "recordings" / f"{args.id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")

    called_skill = any(s["type"] == "tool_call" and s["tool"] == "Skill" for s in out_steps)
    tools = [s["tool"] for s in out_steps if s["type"] == "tool_call"]
    print(f"{args.plugin}/{args.id}: {len(out_steps)} 步；Skill 被触发={called_skill}；工具调用={tools}；"
          f"花费 ${stats.get('costUsd')} → {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
