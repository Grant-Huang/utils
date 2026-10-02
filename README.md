# utils — MCP 工具集合平台

把多个独立的 MCP server 放在一个仓库里，统一以 **Streamable HTTP** 部署给多人使用（同时保留本机 stdio 用法）。

```
utils/
├── servers/
│   ├── office/     Node   生成 docx / pptx / xlsx（docx-js 等），含 demo 前端
│   └── webtool/    Python 搜索 → rerank → 抓取，返回页面正文
├── deploy/         docker-compose + Caddy（路径前缀路由、自动 HTTPS）
└── docs/clients.md 各客户端如何接入
```

**设计取舍**：两个 server 语言不同、依赖体量差异大（webtool 带 torch / chromium），所以各自独立进程、独立镜像，
由 Caddy 在一个域名下按路径路由，而不是合并成一个进程。新增 server 只需：放进 `servers/<name>/`、
实现同一套环境变量约定、在 compose 和 Caddyfile 各加几行。

## 两个 server 共同的约定

| | |
|---|---|
| 端点 | `POST /mcp`（Streamable HTTP，无状态）、`GET /health`（公开） |
| 鉴权 | `Authorization: Bearer <token>`；`MCP_AUTH_TOKENS` 逗号分隔多个；**未配置则拒绝启动**（`MCP_ALLOW_NO_AUTH=1` 仅限本机调试） |
| 防 DNS rebinding | 校验 `Host`（`MCP_ALLOWED_HOSTS`）与 `Origin`（`MCP_ALLOWED_ORIGINS`） |
| 失败语义 | 业务失败返回 `isError: true` + 原因，让模型可读可重试 |

依据：[MCP Tools 规范](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)、
[Transports 规范](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)（Origin 校验、鉴权、本机绑定 127.0.0.1）。

## 部署

```bash
cd deploy
cp .env.example .env        # 填 PUBLIC_HOST / PUBLIC_URL / MCP_AUTH_TOKENS（openssl rand -hex 32）
docker compose up -d --build
```

只有 Caddy 对外暴露端口，`office` / `webtool` 仅内网可达。接入方式见 [docs/clients.md](docs/clients.md)。

## 本地开发 / 测试

```bash
cd servers/office  && npm install && npm test                       # 11 个端到端测试
cd servers/webtool && pip install -e ".[dev]" && pytest             # 11 个 MCP 层测试（不联网）
```

各 server 的详细说明见 `servers/office/README.md`、`servers/webtool/README.md`。
