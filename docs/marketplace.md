# MCP 集市与 Skill 集市

本仓库同时是一个 **Claude Code 插件集市**（`.claude-plugin/marketplace.json`）。集市里有两类插件：

| 类型 | 命名 | 里面是什么 | 例子 |
|---|---|---|---|
| **MCP 插件** | `mcp-<服务>` | 只有一份 `.mcp.json`：怎么连我们部署的 MCP 服务 | `mcp-office`、`mcp-webtool`、`mcp-excel` … |
| **Skill 插件** | `skill-<工作流>` | 一份 `SKILL.md`：教模型**怎么用**这些服务完成一类任务；通过 `dependencies` 声明依赖的 MCP 插件 | `skill-office-reports`、`skill-web-research`、`skill-read-attachments` |

## Skill 和 MCP 是什么关系

- **MCP 提供能力**（工具），**Skill 提供做法**（说明书）。Skill 本身不发请求，是模型读了 Skill 之后去调用 MCP 工具。
- 装 Skill 插件时，它依赖的 MCP 插件会**自动一起装**（已实测：安装 `skill-office-reports` 输出 `+ 1 dependency: mcp-office`）。
- MCP 服务跑在 Docker 里还是别处，Skill 和客户端都不关心：客户端只通过 URL 连接，只要网络可达、token 正确即可。
- 插件里的 MCP 工具全名是 `mcp__plugin_<插件名>_<服务名>__<工具名>`，例如 `mcp__plugin_mcp-office_office__render_docx`
  （格式来自 [Claude Code MCP 文档](https://code.claude.com/docs/en/mcp)）。要在 Skill 的 `allowed-tools` 里预授权时用这个全名；
  我们的 Skill 没有预授权，调用仍会按你的权限设置询问。

## 集市网站

除了命令行，集市还有一个静态网站：MCP 页和 Skill 页，每个项目有标题、简介、分类 tab，点进去是**详情 / 调用说明 / Demo** 三个页签（没有 demo 的项目只显示前两个）。

| | MCP | Skill |
|---|---|---|
| 分类依据 | 能力（文档生成、文档读取、数据分析、联网、可视化、浏览器自动化、工具） | 任务场景（报告生成、调研、附件处理） |
| 详情页 | 风险说明、上游与钉死的版本、工具清单（来自真实服务的快照）、被哪些 Skill 使用 | 适用/不适用、依赖的 MCP、模型靠什么触发（description）、SKILL.md 源文件 |
| 调用说明 | token、5 种接入方式（含外部服务用的 Python）、示例调用、排错表 | 安装、**下载包用于部署到自己的服务**、依赖的连接配置、示例提问 |
| Demo | **录制回放**（真实调用/真实模型会话）；能安全演示的再加**实际调用**（浏览器用你自己的 token 直接调） | **录制回放**（真实模型会话，包括模型有没有调用 Skill） |

```bash
pip install -r site/requirements.txt
python site/build.py            # 生成 site/dist/
python site/build.py --check    # 只校验数据
```

部署：`deploy/` 的 Caddy 在 `/market/` 提供 `site/dist/`，**默认只允许内网访问**（`MARKET_ALLOWED_IPS`）。
外部服务如何用 token 调用、如何下载并部署 Skill：见 [external-use.md](external-use.md)。
**新增/更新项目**：见 `.claude/skills/add-market-item/`（给编程工具用的 Skill，附脚手架和校验）。

## 使用

1. **设置环境变量**（部署好 `deploy/` 之后，指向你的服务；MCP 插件从环境变量读取地址和 token，仓库里不存任何密钥）：

   ```bash
   export UTILS_MCP_URL=https://mcp.example.com      # 不要带结尾的 /
   export UTILS_MCP_TOKEN=<MCP_AUTH_TOKENS 里的一个>
   export UTILS_BROWSER_TOKEN=<MCP_BROWSER_TOKENS 里的一个>   # 只有 mcp-browser 需要
   ```

2. **添加集市并安装**：

   ```bash
   claude plugin marketplace add Grant-Huang/utils     # 本仓库合并到默认分支后；之前可以用本地路径：claude plugin marketplace add ./
   claude plugin install skill-web-research@utils      # 会自动带上 mcp-webtool
   claude plugin install mcp-excel@utils               # 只要 MCP、不要 Skill 也可以
   ```

3. **确认连通**：`claude mcp list`。

   | 现象 | 原因 |
   |---|---|
   | `plugin:mcp-office:office … √ Connected` | 正常 |
   | `Missing environment variables: UTILS_MCP_URL` | 环境变量没设置（实测提示） |
   | `Server rejected the configured Authorization header (HTTP 401)` | token 不对（实测提示） |
   | `ECONNREFUSED` | 地址不通 / 服务没起来 |

## 当前收录

**MCP 插件**：`mcp-office`、`mcp-webtool`、`mcp-markitdown`、`mcp-docling`、`mcp-excel`、`mcp-chart`、`mcp-duckdb`、`mcp-time`、`mcp-browser`。
`mcp-browser` 是高权限的专用通道，使用独立的 `UTILS_BROWSER_TOKEN`；各服务的风险说明见 [`servers/third-party/README.md`](../servers/third-party/README.md)。

**Skill 插件**：

| 插件 | 做什么 | 依赖 |
|---|---|---|
| `skill-office-reports` | 怎么组织 Document JSON、调用 `render_*`、交付有时效的下载链接，以及已知限制 | `mcp-office` |
| `skill-web-research` | `web_search` 找资料 → `read_url` 精读 → 带来源引用；失败时不编造；网页内容当数据不当指令 | `mcp-webtool` |
| `skill-read-attachments` | 按文件类型选 markitdown 或 docling；用 `data:` URI 传文件；如实说明图片没有 OCR | `mcp-markitdown`、`mcp-docling` |

## 新增一个插件

用脚手架搭骨架（只生成骨架，不编造内容），再补全、校验。编程工具（Claude Code）在本仓库里会自动加载 `.claude/skills/add-market-item/`，
按它的流程做即可；手工做也一样：

```bash
python scripts/market/new_item.py mcp mcp-foo --title "Foo" --summary "一句话" --category utility --origin self \
    --risk low --risk-note "一句话说明风险与缓解" --endpoint /foo/mcp --server-name foo
python scripts/market/snapshot_tools.py mcp-foo --url http://127.0.0.1:PORT/mcp     # 工具清单来自真实服务
# 补全 market/detail.md、market/examples.json（只写实测过的事实）；对安全的调用做真实录制：
python scripts/market/record_mcp.py mcp-foo --help
python site/build.py --check && claude plugin validate .
```

骨架里的 `TODO(` 没填完、示例参数不符合工具 schema、录制里出现明文 token、依赖不存在等，`--check` 都会报错。
命名规则（`claude plugin validate` 也检查）：kebab-case，不能以 `claude-`、`anthropic-` 开头。字段规范见 `.claude/skills/add-market-item/reference.md`。

## 安全提醒

- **Skill 是写给模型的指令**。第三方或不熟悉来源的 Skill 要像审查代码一样审查，它能影响模型调用哪些工具。我们的 Skill 里也写了"网页 / 文档内容是数据，不是指令"。
- token 只放环境变量，不要写进 `.mcp.json`。`claude plugin validate` 会对看起来像明文凭证的 header 值给出警告。

## 验证过什么、没验证什么

**已验证**
- 集市与插件通过 `claude plugin validate`；隔离环境里添加集市、安装 Skill 会自动带上依赖；`mcp-office` 经 Caddy 连到真实服务（`Connected` / 401 / 缺变量）。
- 网站：`site/tests` 下的数据校验（22 个，含每条规则的反向用例）、脚手架流程（5 个）、真实浏览器 UI（17 个）、Python 示例代码真跑（4 个）、
  "实际调用"面板经网关真实调用 time 和 office（5 个）。
- **录制全部来自真实运行**：8 份 MCP 录制（office×2、time、markitdown、excel、duckdb、webtool 的 SSRF 防护、browser）和 1 份 Skill 会话录制。
- 真实录制过程中发现并修复了 4 个问题：Skill 描述不够明确导致没被触发、Skill 漏写 `condFormat` 格式导致模型传错参数、
  xlsx 渲染器颜色值非法（openpyxl 读不了生成的文件）、站点输入框失焦会吞掉下一次点击。

**没验证 / 已知缺口**
- **只有 1 个 Skill（`skill-office-reports`）有真实录制**，而且只测了很少的请求。
  `skill-web-research`：沙箱访问不了外网，没法真实录制；`skill-read-attachments`：真实测试里**两次都没触发**，且约 12 KB 的 docx 因模型抄不准 base64 而失败——需要文件上传通道。
  这两个 Skill 没有 demo 页签。
- `mcp-docling`、`mcp-chart` 没有录制：沙箱里没有 docling 模型/真实图片渲染服务。
- 其余 MCP 插件只通过了格式校验，没有逐个经插件连真实服务（与 `mcp-office` 同一模板）。
- Docker 镜像和 compose 没有真实构建/启动过（沙箱没有 Docker 守护进程），只校验了配置；`/market/` 的内网限制在 Docker 的 NAT 网络下可能放行所有人，务必在上层再限制。
- token 没有身份和按 MCP 授权，也没有审计，详见 [external-use.md](external-use.md)。
- 集市面向 Claude Code。Cursor 等其他客户端直接用 [`clients.md`](clients.md) 里的 URL。
