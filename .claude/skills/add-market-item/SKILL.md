---
name: add-market-item
description: Use when adding, updating or removing an MCP server or a Skill in this repository's marketplace (the "utils 集市" under plugins/ and site/) — for example "add a new MCP to the market", "publish this skill", "update the demo or recording", "the tool list is out of date". Covers scaffolding, snapshotting tools from the real service, real recordings, validation, and what must never be fabricated.
---

# 向集市新增 / 更新 / 删除一个 MCP 或 Skill

集市的**单一数据源就是仓库**：`plugins/<name>/` 里的文件。站点由 `python site/build.py` 生成，没有数据库。
字段、分类、风险等级的完整规范在 [reference.md](reference.md)，写之前先读一遍。

先装依赖（只需一次）：`pip install -r site/requirements.txt pytest playwright`。

## 新增一个 MCP

1. **定类型和分类**：MCP 插件名以 `mcp-` 开头；分类见 `site/taxonomy.json`；风险等级按 reference.md 里的标准判断（不要凭感觉）。
2. **服务本身要先部署好**（不属于本 Skill）：自研放 `servers/<name>/`；第三方放 `servers/third-party/<name>/Dockerfile`，
   **版本钉死**，并在 `deploy/` 里加 compose profile 和 Caddyfile 路由。见 `servers/third-party/README.md`。
3. **搭骨架**（只生成骨架，不编造内容）：
   ```bash
   python scripts/market/new_item.py mcp mcp-foo --title "Foo 服务" --summary "一句话" --category utility \
     --origin third-party --risk medium --risk-note "一句话说明风险与缓解" --endpoint /foo/mcp --server-name foo \
     --upstream-name foo-mcp --upstream-version 1.2.3 --upstream-license MIT --upstream-url https://github.com/x/foo
   ```
   第三方的 `--upstream-version` 必须是**我们钉死的包版本**，不要用服务自己报告的版本（实测过：chart 的包是 0.9.10，它自报 0.8.x）。
4. **把服务在本机跑起来，快照工具清单**（站点上的工具表来自它，不手写）：
   ```bash
   python scripts/market/snapshot_tools.py mcp-foo --url http://127.0.0.1:PORT/mcp [--token ...]
   ```
5. **亲自实测，再写 `market/detail.md`**：只写你**亲自验证过**的事实。没验证的写"未实测"，不要从上游文档照抄成结论。
   必须说清楚：能读什么、能访问什么网络、数据会不会出站、需要怎样的隔离。
6. **写 `market/examples.json`**：`calls` 里每个示例的参数会按该工具的 inputSchema 自动校验，写错会被拦住。
7. **录制真实调用**（推荐）：写一个 steps 脚本 `[{"tool":"…","arguments":{…}}]`，然后
   ```bash
   python scripts/market/record_mcp.py mcp-foo --url <网关或服务的 /mcp 地址> --token … --id <slug> --title "…" \
     --script steps.json --rewrite http://localhost:18080=https://mcp.example.com
   ```
   - 只录**无副作用、可安全展示**的调用。失败（`isError`）也要如实录，它能展示安全防护（例如 SSRF 防护拒绝内网地址）。
   - 录制里的本机地址用 `--rewrite` 改成示例域名，这会被记在 `normalized` 里，是允许的；除此之外不许改内容。
8. **要不要开"实际调用"**（`metadata.market.live`）：只有同时满足下面四条才开——无副作用、数据不出站、不读服务器上的文件、调用成本可忽略。
   拿不准就不开；高风险和第三方会读文件的服务一律不开。
9. 跑**校验清单**（见下）。

## 新增一个 Skill

1. 它依赖的 MCP 必须已经在集市里（`dependencies` 里写 MCP 插件名，安装 Skill 时会自动带上它们）。
2. **搭骨架**：`python scripts/market/new_item.py skill skill-baz --title … --summary … --category research --depends mcp-foo`
   （Skill 目录名是插件名去掉 `skill-` 前缀）。
3. **写 `SKILL.md`**：
   - `description` 是模型决定是否触发的**唯一依据**。以 `Use when …` 开头，写清楚什么请求该触发；
     如果有对应的 MCP 工具，要**明确说"用这些工具，而不是自己写代码或文件"**——我们真实测过，不写这句，模型会直接用 Python 自己干。
   - 正文只写**实测过的行为**。工具的参数格式要对照 `market/tools.json` 的 schema 和服务端实现来写，**不能让模型去猜**
     （实测过：模板里漏写 `condFormat` 的确切格式，模型就传成了错的数组）。
4. **真实录制并检查触发**（会真的调用模型，约 $0.05–0.3）：
   ```bash
   UTILS_MCP_URL=… UTILS_MCP_TOKEN=… python scripts/market/record_skill.py skill-baz --id <slug> --title "…" \
     --prompt "用户会真的这么问的话" --allow 'mcp__plugin_mcp-foo_foo__*' --rewrite http://localhost:18080=https://mcp.example.com
   ```
   看输出里的 **`Skill 被触发=`**：
   - 为 `False`：**不要提交这份录制**（它没展示这个 Skill）。改 `description`（更明确）后重录；
   - 为 `True`：再看模型传的参数对不对、最终回答是否如实。参数错了，根因通常是 SKILL.md 漏写了格式，改 Skill，不要改录制。
5. 把真实测试结果（**包括失败**）写进 `market/detail.md` 的"验证状态"。没测过就写"尚未验证"，没有录制就让它没有 demo 页签。

## 更新 / 删除

- **服务升级了**：重新 `snapshot_tools.py`；示例会被自动重新校验；动过行为的话重录，并更新钉死的 `upstream.version`。
- **删除**：删 `plugins/<name>/` 和 `.claude-plugin/marketplace.json` 里的条目；依赖它的 Skill 要先处理（校验会报）。

## 校验清单（全部通过才算完成）

```bash
python site/build.py --check                 # 数据完整性：字段、分类、示例参数 schema、录制、依赖、TODO、明文 token
claude plugin validate ./plugins/<name>      # 官方的插件格式校验
claude plugin validate .                     # 官方的集市校验
python -m pytest site/tests -q               # 站点测试（UI 测试需要 Chromium；实际调用联调需要网关，没配会自动跳过）
python site/build.py                         # 生成 site/dist，打开看一眼
```

## 绝对不要

- **编造或手写**录制、工具清单、版本号、"实测结论"。录制只能来自 `record_mcp.py` / `record_skill.py` 的真实运行。
- 把没触发 Skill 的会话当作该 Skill 的演示。
- 把 token 写进任何文件（`.mcp.json` 里只能是 `${UTILS_MCP_TOKEN}` 这样的变量；校验会拦明文）。
- 为了"看起来完整"留下 `TODO(` 占位符，或者给没有录制的项目补一个假 demo——**没有 demo 就没有 demo 页签，这是正常的**。
- 隐藏风险：能读文件、数据出站、需要高权限的服务，风险等级和 `riskNote` 必须如实写。
