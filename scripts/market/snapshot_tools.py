#!/usr/bin/env python3
"""对一个运行中的 MCP 服务做"工具清单快照"，写入 plugins/<plugin>/market/tools.json。

站点上的工具清单来自这份快照，而不是手写，所以不会和真实服务脱节。
快照里会记录服务名/版本/协议版本和时间；服务升级后重新跑一遍即可。

用法：
  python scripts/market/snapshot_tools.py mcp-office --url http://127.0.0.1:8911/mcp --token $TOKEN
  python scripts/market/snapshot_tools.py mcp-markitdown --url http://127.0.0.1:3001/mcp      # 无鉴权的本机服务
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mcp_http import McpClient  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plugin", help="插件名，例如 mcp-office")
    ap.add_argument("--url", required=True, help="MCP 端点完整 URL（以 /mcp 结尾）")
    ap.add_argument("--token", help="Bearer token（服务无鉴权时可省略）")
    args = ap.parse_args(argv)

    plugin_dir = ROOT / "plugins" / args.plugin
    if not plugin_dir.is_dir():
        sys.exit(f"plugin not found: {plugin_dir}")

    c = McpClient(args.url, args.token)
    c.initialize()
    tools = c.list_tools()
    snap = {
        "snapshotAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "server": c.server_info,
        "protocolVersion": c.protocol_version,
        "tools": [{k: t[k] for k in ("name", "title", "description", "inputSchema", "annotations") if k in t}
                  for t in tools],
    }
    out = plugin_dir / "market" / "tools.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{args.plugin}: {len(tools)} tools ← {c.server_info.get('name')} {c.server_info.get('version', '')} → {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
