# office-mcp

把 Anthropic 官方 docx/pptx/xlsx skill 的能力封装成 **MCP server**（stdio + Streamable HTTP）+ REST 接口 + demo 前端。
任何 MCP 兼容的 Agent 都能调用，也可以直接 HTTP POST 拿文件。

## 1. 架构

```
MCP client ──stdio──────────▶ src/mcp/server.js ─┐
MCP client ──POST /mcp──────▶ src/http/bridge.js ─┼─▶ src/mcp/tools.js ─▶ src/lib/render.js ─▶ renderers/{docx,pptx,xlsx}.js
demo 前端 / curl ─POST /render▶ src/http/bridge.js ─┘                                              skills/default.js
```

MCP 与 REST 共用同一个 `render()`，输出的文件字节一致。

## 2. 启动

```bash
npm install
npm test                                  # 端到端测试（真实起服务 + 官方 MCP 客户端）

# 本机调试（无鉴权，仅监听 127.0.0.1）
MCP_ALLOW_NO_AUTH=1 npm start             # http://127.0.0.1:8911
# 对外服务：必须配置 token
MCP_AUTH_TOKENS=$(openssl rand -hex 32) HOST=0.0.0.0 npm start
# stdio（被 MCP 客户端拉起）
node src/mcp/server.js
```

HTTP 模式**没有 token 会拒绝启动**。环境变量：

| 变量 | 说明 | 默认 |
|---|---|---|
| `MCP_AUTH_TOKENS` | 逗号分隔的 Bearer token | 必填（或 `MCP_ALLOW_NO_AUTH=1`） |
| `MCP_ALLOWED_HOSTS` | 允许的 Host 头，防 DNS rebinding；本机地址始终允许 | — |
| `MCP_ALLOWED_ORIGINS` | 允许跨域调用的 Origin；同源始终允许 | — |
| `PUBLIC_BASE_URL` | 文件下载地址前缀（反向代理带路径时必须设，如 `https://mcp.example.com/office`） | 按 Host 推导 |
| `HOST` / `PORT` | 监听地址 | `127.0.0.1` / `8911` |
| `RATE_LIMIT_PER_MIN` | 每个 token/IP 每分钟请求数 | `60` |
| `OFFICE_FILE_TTL_SECONDS` | 生成文件保留时间 | `3600` |

## 3. MCP 接口

端点：`POST /mcp`（Streamable HTTP，无状态；`GET/DELETE` 返回 405）。

| 工具 | 输入 | 输出 |
|---|---|---|
| `render_docx` / `render_pptx` / `render_xlsx` | `{ document, skill?, filename?, inline? }` | HTTP：`text`(元数据) + `resource_link`(下载 URL，TTL 内有效)；stdio 或 `inline:true`：`text` + 内嵌 `resource`(base64 blob) |

另有资源 `office://skill/default`（默认样式 JSON）。渲染失败返回 `isError: true` 和原因，不是协议错误。

### Document 模型

```ts
{
  meta?: { creator?: string, title?: string },
  cover?: {
    title: string, subtitle?: string,
    fields?: [[label, value], ...],
    abstract?: string,
  },
  toc?: boolean,                  // 是否生成 TOC 占位（Word 按 F9 刷新）
  header?: { text: string },      // 页眉 "X" · {PAGE} / {NUMPAGES}
  footer?: { text: string },      // 页脚（默认空）
  chapters: [
    {
      title: string,
      level?: 1 | 2 | 3,
      blocks: [
        | { type: 'paragraph', text: string, opts?: TextRunOpts, para?: ParagraphOpts }
        | { type: 'table', rows: string[][], widths?: number[], headerFill?: string, caption?: string }
        | { type: 'flowchart', nodes: { label: string, color: string }[], caption?: string }
        | { type: 'code', title?: string, code: string, borderColor?: string }
        | { type: 'pagebreak' }
        | { type: 'list', items: string[] }   // PPTX 专用
      ]
    }
  ],
  references?: string[],          // docx 专用
  sheets?: [                      // xlsx 专用
    {
      name: string,
      data: any[][],              // AOA
      cols?: number[],            // 列宽 (wch)
      headerFill?: string,        // 表头颜色（覆盖 skill.theme.sheetHeaders）
      condFormat?: { column: number, low?: number, high?: number },
      autofilter?: string,
      freeze?: boolean,           // 默认 true
    }
  ],
}
```

完整样例见 `examples/asr-report.{json,docx.json,xlsx.json}`。

### Skill（可覆盖的样式默认值）

```ts
{
  name?: string,
  page?: { width?, height?, margin?: { top, right, bottom, left } },  // DXA
  body?: { asciiFont?, eastAsiaFont?, size?, color? },               // pt, hex
  heading?: { [1|2|3]?: { size?, color?, asciiFont?, eastAsiaFont? } },
  table?: { headerFill?, headerColor?, cellFill?, cellColor?, cellSize? },
  code?:  { fill?, color?, size?, font?, borderColor?, borderSize?, width? },
  header?: { size?, color? },
  footer?: { size?, color? },
  theme?: { primary?, sheetHeaders?: string[] },                     // PPTX/XLSX
  font?:  { cnBody?, cnHeading?, code? },                            // PPTX
}
```

**优先级**：per-block / per-table `headerFill` / `borderColor` 等 → 全局 `skill` → 内置默认值。

### 调用示例

```bash
claude mcp add --transport http office https://mcp.example.com/office/mcp \
  --header "Authorization: Bearer $TOKEN"
```

更多客户端见仓库根目录 `docs/clients.md`。

## 4. HTTP 接口

| Method | Path | 鉴权 | 说明 |
|---|---|---|---|
| POST | `/mcp` | Bearer | MCP |
| POST | `/render/{docx\|pptx\|xlsx}` | Bearer | body=`{document, skill?, filename?}` → 二进制附件 |
| GET | `/files/:id/:name` | id 即凭证 | 下载 MCP 工具生成的文件 |
| GET | `/health` `/skill/default` `/` | 公开 | 健康检查 / 默认 skill / demo 前端（页面右上角填 token） |

```bash
curl -X POST http://127.0.0.1:8911/render/docx -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d @examples/asr-report.json -o out.docx
```

## 5. 升级 Skill 的做法

Skill 是纯 JSON（`src/lib/skills/default.js`），改它不涉及 renderer 代码：

```js
// 新增一个行业专用 skill
// src/lib/skills/legal.js
import { defaultSkill } from './default.js';
export const legalSkill = {
  ...defaultSkill,
  name: 'office-d/legal/v1',
  body: { ...defaultSkill.body, eastAsiaFont: '仿宋', size: 12 },
  page: { ...defaultSkill.page, margin: { top: 1800, right: 1800, bottom: 1800, left: 1800 } },
};
```

然后在 `src/lib/render.js` 里加一个参数，让 caller 选哪个 skill。或者**多 skill 注册到一个 MCP server**，每种 skill 暴露一组工具（`render_docx_legal` / `render_docx_default`），方便 LLM 按业务线选择。

---

## 6. 已知限制

- xlsx 的 chart 原生 API 还没接，目前只能渲染表格 + 条件格式
- docx TOC 是占位（Word 按 F9 刷新），docx-js 没有官方 TOC 域生成
- pptx 流程图节点超过 6 个会自动换行；一个章节里混合多种 block 时，pptx 只渲染其中一种（按 表格 > 流程图 > 代码 > 列表 > 段落 的优先级）
- 限流是进程内的；多实例部署请在网关层限流
- `npm audit` 报 `pptxgenjs → image-size` 的 DoS 告警，仅在解析 JXL/HEIF/ICNS 图片时触发，本项目不处理图片

## 7. 文件清单

```
servers/office/
├── src/mcp/{server.js,tools.js}   # stdio 入口 / 工具注册（官方 SDK）
├── src/http/bridge.js         # Streamable HTTP + REST + 静态前端
├── src/lib/{render.js,auth.js,filestore.js}  skills/default.js  renderers/*.js
├── public/                    # demo 前端
├── examples/                  # 示例 Document JSON
├── test/e2e.test.js
└── Dockerfile
```
