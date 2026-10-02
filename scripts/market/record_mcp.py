#!/usr/bin/env python3
"""对运行中的 MCP 服务做一次**真实**的工具调用录制，写入 plugins/<plugin>/market/recordings/<id>.json。

steps 脚本是一个 JSON 文件：[{"tool": "...", "arguments": {...}}, ...]，按顺序真实调用，原样记录返回。
服务返回的是什么就记什么；失败（isError）也照实记录，这对展示安全防护很有用。

用法：
  python scripts/market/record_mcp.py mcp-time --url http://localhost:18080/time/mcp --token $TOKEN \\
      --id shanghai-now --title "获取上海当前时间" --script steps.json \\
      [--description "..."] [--rewrite http://localhost:18080=https://mcp.example.com]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import recording as R  # noqa: E402
from mcp_http import McpClient  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plugin")
    ap.add_argument("--url", required=True)
    ap.add_argument("--token")
    ap.add_argument("--id", required=True, help="录制 id（小写字母、数字、连字符）")
    ap.add_argument("--title", required=True)
    ap.add_argument("--description", default="")
    ap.add_argument("--script", required=True, help="steps 脚本 JSON 文件")
    ap.add_argument("--rewrite", action="append", default=[], metavar="FROM=TO", help="把本机地址改写为示例域名（会记录在 normalized 里）")
    args = ap.parse_args(argv)

    plugin_dir = ROOT / "plugins" / args.plugin
    if not plugin_dir.is_dir():
        sys.exit(f"plugin not found: {plugin_dir}")
    script = json.loads(Path(args.script).read_text(encoding="utf-8"))
    mapping = dict(r.split("=", 1) for r in args.rewrite)

    c = McpClient(args.url, args.token)
    c.initialize()

    steps, total_ms = [], 0
    for item in script:
        t0 = time.perf_counter()
        res = c.call_tool(item["tool"], item.get("arguments", {}))      # 真实调用；协议错误会抛异常并中止录制
        ms = round((time.perf_counter() - t0) * 1000)
        total_ms += ms

        call = {"tool": item["tool"], "arguments": item.get("arguments", {})}
        call, hit = R.truncate(R.rewrite_text(call, mapping))
        steps.append({"type": "tool_call", **call, "truncated": hit})

        result = {"isError": bool(res.get("isError")), "durationMs": ms,
                  "content": R.normalize_content(res.get("content", []))}
        result, hit = R.truncate(R.rewrite_text(result, mapping))
        steps.append({"type": "tool_result", **result, "truncated": hit})

    rec = {
        "schema": 1, "kind": "mcp", "id": args.id, "title": args.title, "description": args.description,
        "recordedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {"plugin": args.plugin, "server": c.server_info},
        "normalized": [f"文本中的 {a} 改写为 {b}" for a, b in mapping.items()],
        "steps": steps, "stats": {"durationMs": total_ms},
    }
    errs = R.validate(rec)
    if errs:
        sys.exit("录制不合法：" + "; ".join(errs))
    out = plugin_dir / "market" / "recordings" / f"{args.id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(R.dump(rec), encoding="utf-8")
    errored = sum(1 for s in steps if s["type"] == "tool_result" and s["isError"])
    print(f"{args.plugin}/{args.id}: {len(script)} 次调用（{errored} 次返回 isError）→ {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
