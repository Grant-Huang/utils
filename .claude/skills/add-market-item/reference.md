# 集市字段规范

## 文件布局

```
.claude-plugin/marketplace.json          收录哪些插件（new_item.py 会自动追加）
site/taxonomy.json                       分类与风险等级定义（新增分类在这里加）
site/config.json                         站点标题、示例域名、仓库名
plugins/<name>/
  .claude-plugin/plugin.json             名称、版本、dependencies、metadata.market
  .mcp.json                              仅 MCP 插件：连接配置
  skills/<skill>/SKILL.md                仅 Skill 插件
  market/
    detail.md                            详情页正文（Markdown；原始 HTML 会被转义）
    usage.md                             可选：追加到"调用说明"页末尾
    examples.json                        MCP: {"calls":[{title,tool,arguments}]}；Skill: {"prompts":["…"]}
    tools.json                           仅 MCP：由 snapshot_tools.py 从真实服务生成，不要手写
    recordings/<id>.json                 由 record_mcp.py / record_skill.py 生成，不要手写
```

## `plugin.json` 的 `metadata.market`

| 字段 | 适用 | 要求 |
|---|---|---|
| `type` | 全部 | `mcp` 或 `skill` |
| `title` / `summary` / `category` | 全部 | 必填；`category` 必须在 `site/taxonomy.json` 对应类型的分类里 |
| `tags` | 全部 | 字符串数组，用于搜索 |
| `origin` | MCP | `self`（自研）/ `third-party` |
| `risk` / `riskNote` | MCP | 等级见下；`riskNote` 一句话写风险与缓解 |
| `endpoint` | MCP | 经网关的路径，形如 `/office/mcp`；必须与 `.mcp.json` 的 url 一致 |
| `tokenScope` | MCP | `default`（`UTILS_MCP_TOKEN`）或 `browser`（`UTILS_BROWSER_TOKEN`，高权限专用通道） |
| `upstream` | 第三方 MCP | `{name, version, license, url}`；`version` 是我们钉死的包版本 |
| `live` | MCP，可选 | `{"tool": "…", "example": <examples.calls 的下标>}`；开启"实际调用"，条件见下 |

`dependencies`（Skill）写在 `plugin.json` 顶层，值是 MCP 插件名数组。

## 风险等级（按这个标准判，不要凭感觉）

| 等级 | 标准 |
|---|---|
| `low` | 只做无副作用的事，或只往临时目录写文件；没有读服务器文件、没有出站网络 |
| `medium` | 会读写服务器文件、访问网络，或把数据送出；**已通过隔离/限制缓解**（internal 网络、只读挂载、SSRF 防护等） |
| `high` | 高权限（等价代码执行、任意浏览器操作等）；只能用专用 token，默认不启用 |

## 什么时候可以开"实际调用"（`live`）

必须**同时**满足：无副作用 · 数据不出站 · 不读服务器上的文件 · 调用成本可忽略。
当前只有 `mcp-time`、`mcp-office`。第三方会读文件的服务（markitdown、duckdb、docling）和高权限服务（browser）不开。

## 录制（recording）

结构、截断与校验规则见 `scripts/market/recording.py` 文件头。要点：
- `kind` 与项目类型一致（`mcp` / `skill`）；`id` 与文件名一致，小写字母、数字、连字符；
- 每个 `tool_result` 前面必须有对应的 `tool_call`；Skill 录制必须有 `user` 步骤；
- 超过 2000 字符的字符串会被截断并标注原长和 sha256；内嵌文件只记大小；
- 只允许把本机网关地址改写成示例域名，并记录在 `normalized`；
- 录制或 market 下任何文件里出现疑似明文 token 会导致校验失败。

## 命名规则（`claude plugin validate` 也会检查）

- kebab-case；**不能以 `claude-`、`anthropic-`、`anthropics-`、`cc-plugin-` 开头**；
- marketplace.json 里的 `name` 必须与 `plugin.json` 的 `name`、目录名一致；
- MCP 以 `mcp-` 开头，Skill 以 `skill-` 开头（Skill 目录名 = 插件名去掉 `skill-`）。

## 环境变量约定

插件的 `.mcp.json` 从环境变量读取地址和 token，仓库里不存密钥：
`UTILS_MCP_URL`（网关根地址，不带结尾 `/`）、`UTILS_MCP_TOKEN`、`UTILS_BROWSER_TOKEN`（仅 browser 通道）。
插件里 MCP 工具的全名是 `mcp__plugin_<插件名>_<服务名>__<工具名>`。
