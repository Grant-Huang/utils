# 外部服务如何使用这些 MCP 和 Skill

场景：你们自己在别处部署的服务（Agent、后端程序等），要通过 token 调用集市里的 MCP，并使用其中的 Skill。

## MCP：直接用 token 调用

每个 MCP 都是一个 HTTP 端点 `https://<网关域名>/<名称>/mcp`，调用时带请求头 `Authorization: Bearer <token>`。
集市每个 MCP 的“调用说明”页都有可复制的 curl、通用 JSON 配置和 Python（只用标准库）示例。
Python 示例有测试：模板会被真的对一个服务跑一遍（`site/tests/test_snippets.py`）。

### 发放和吊销 token（管理员）

token 是服务端环境变量里的字符串，没有单独的管理后台：

| 操作 | 做法 |
|---|---|
| 发放 | 生成一个随机值（如 `openssl rand -hex 32`），追加到 `deploy/.env` 的 `MCP_AUTH_TOKENS`（逗号分隔），`docker compose up -d` 让服务重建 |
| 吊销 | 从 `MCP_AUTH_TOKENS` 里删掉它，同样重建 |
| 浏览器专用通道 | 另用 `MCP_BROWSER_TOKENS`；普通 token 不能用，专用 token 也不能用于普通通道（已实测） |

建议**每个调用方一个独立 token**，这样吊销一个不影响别人。token 只放环境变量或密钥管理，不要写进代码、镜像或仓库。

### ⚠ 当前机制的局限（请知晓）

- **token 没有身份，也没有审计日志**：服务端看不到“这个 token 属于谁”。请自己维护一份“token → 调用方”的对应表。
- **不能按 MCP 授权**：`MCP_AUTH_TOKENS` 里的 token 对所有普通 MCP 都有效，没法发一个“只能调 office”的 token。唯一的例外是浏览器专用通道。
- **限流是按 token 的粗粒度计数**（authcheck 与 office 各自按每分钟次数限制，额度由管理员配置），不是配额或计费。
- 如果这些不够用（例如要对外部客户开放），下一步需要做“按 MCP 授权的 token + 审计”，目前没有。

## Skill：下载后部署到你们的服务里

Skill 本质是一个目录（`SKILL.md` 加可选的附属文件）。在集市里打开某个 Skill 的“调用说明”页，可以下载两种包：

| 包 | 内容 | 用法 |
|---|---|---|
| Skill 包 | 只有 `<skill>/SKILL.md` | 解压到你们服务的 `.claude/skills/`，得到 `.claude/skills/<skill>/SKILL.md` |
| 完整插件包 | `.claude-plugin/plugin.json` + `skills/` | `claude --plugin-dir ./<包>.zip` 加载（Claude Code 的 `--plugin-dir` 接受目录或 zip） |

包是**确定性生成**的（同样的内容得到同样的字节，页面上有 sha256），可以用来核对没被改过。

**Skill 本身不会连接 MCP。** 部署 Skill 之后，还要在你们的服务里配好它依赖的 MCP 连接。每个 Skill 的“调用说明”页会列出依赖的每个 MCP 的连接配置：

```json
{ "mcpServers": { "office": { "type": "http", "url": "https://<网关域名>/office/mcp",
                              "headers": { "Authorization": "Bearer ${UTILS_MCP_TOKEN}" } } } }
```

## 重要：Skill 能否被触发，要在你们自己的环境里再验证

Skill 靠模型读它的 `description` 决定是否使用。我们在真实模型会话里测过（见各 Skill 的“验证状态”）：
- 描述写得不够明确时，模型会绕过 Skill，直接自己写代码；
- 附件类 Skill 受“没有文件上传通道”限制，大文件目前做不到。

换了模型、换了环境，行为可能不同。部署后请用真实请求试几轮。
