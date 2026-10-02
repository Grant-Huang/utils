# 客户端接入

两个 server 部署后的端点（经 `deploy/` 里的 Caddy 路由）：

| Server | URL |
|---|---|
| office | `https://<host>/office/mcp` |
| webtool（`web_search`、`read_url`） | `https://<host>/webtool/mcp` |
| markitdown / docling / excel / duckdb / time / chart | `https://<host>/<名称>/mcp` |
| browser（Playwright，专用通道） | `https://<host>/browser/mcp` |

第三方 server 的说明、风险与启用方式见 [`servers/third-party/README.md`](../servers/third-party/README.md)。
`/browser` 只认 `MCP_BROWSER_TOKENS`，普通 token 不能用。

鉴权：`Authorization: Bearer <token>`，token 来自部署时的 `MCP_AUTH_TOKENS`。

## Claude Code

语法依据 [Claude Code MCP 文档](https://code.claude.com/docs/en/mcp)：

```bash
claude mcp add --transport http office  https://mcp.example.com/office/mcp  --header "Authorization: Bearer $TOKEN"
claude mcp add --transport http webtool https://mcp.example.com/webtool/mcp --header "Authorization: Bearer $TOKEN"
```

或项目根目录的 `.mcp.json`（支持 `${VAR}` 环境变量展开，避免把 token 写进仓库）：

```json
{
  "mcpServers": {
    "office":  { "type": "http", "url": "https://mcp.example.com/office/mcp",  "headers": { "Authorization": "Bearer ${MCP_TOKEN}" } },
    "webtool": { "type": "http", "url": "https://mcp.example.com/webtool/mcp", "headers": { "Authorization": "Bearer ${MCP_TOKEN}" } }
  }
}
```

## 本机 stdio（不经过 HTTP，无需 token）

```bash
claude mcp add --transport stdio office  -- node /path/to/utils/servers/office/src/mcp/server.js
claude mcp add --transport stdio webtool -- python -m webtool.server      # 需先在该环境 pip install
```

## 直接用 curl 验证

```bash
curl -s https://mcp.example.com/office/mcp \
  -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## 给每个使用方发独立 token

`MCP_AUTH_TOKENS=tokenA,tokenB,tokenC`，要吊销某个使用方就删掉它对应的 token 并重启。
