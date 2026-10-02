# 第三方 MCP server

这里不放代码，只放**镜像定义**（版本全部钉死、非 root 运行）。部署见 `deploy/docker-compose.third-party.yml`。
下面每一条「实测」都是在本仓库的集成测试环境里真实跑出来的结果，不是照搬文档。

## 入口与安全模型

```
客户端 ─HTTPS─▶ Caddy ─forward_auth─▶ authcheck（Bearer token / Origin / 限流）
                  │                      └ 通过才继续；上游收不到用户 token
                  └─▶ 各 MCP server（internal 网络：无外网出口；只读根文件系统；cap_drop ALL）
```

- **为什么统一鉴权**：这些 server 要么官方明说不支持鉴权（markitdown），要么没写（duckdb、chart、docling、playwright）。
- **为什么放 internal 网络**：markitdown / duckdb / docling 都能读容器内任意文件，且可能访问任意网络地址（见下）。
  容器里不放密钥、也没有外网出口，是它们安全可用的前提。
- **专用通道**：`/browser` 只认 `MCP_BROWSER_TOKENS`，普通 token 进不去（实测）。

## 一览

| 路径 | 工具 | 版本（钉死） | 默认启动 | 实测结论 |
|---|---|---|---|---|
| `/markitdown/mcp` | `convert_to_markdown(uri)` | `markitdown-mcp==0.0.1a7`（MIT） | profile `markitdown` | docx/pptx/xlsx/html 转换正常，中文保留，表格转 Markdown 表；**PNG 返回空，开箱没有 OCR** |
| `/docling/mcp` | 4 个（转换 + 本地缓存管理） | `docling-mcp[local]==3.2.1`（MIT） | profile `docling` | 只加载 `conversion` 组即可启动；**镜像与模型预下载未在真实环境构建验证** |
| `/excel/mcp` | 26 个（读写、格式、图表、条件格式…） | `excel-mcp-server==1.1.1`（MIT） | profile `excel` | 带 token 才能访问；绑 0.0.0.0 无 token 会**拒绝启动**；有 `create_chart`，**没有名叫"透视表"的工具**（最接近的是 `create_summary_table`） |
| `/chart/mcp` | 27 个图表工具 | `@antv/mcp-server-chart@0.9.10`（MIT） | profile `chart` | ⚠ 默认把数据发到公网渲染服务（见下）；设 `VIS_REQUEST_SERVER` 后请求体只发往该地址 |
| `/duckdb/mcp` | `execute_query` 等 | `mcp-server-motherduck==1.0.8`（包元数据未声明 license，需到仓库确认） | profile `duckdb` | **能直接 `read_csv` / `read_xlsx`**；文件库默认只读（写入被拒）；内存库必须 `--read-write`，所以用文件库 |
| `/time/mcp` | `get_current_time` / `convert_time` | `mcp-server-time==2026.8.18`（MIT）+ `mcp-proxy==0.12.0` | profile `time` | 正常；是 PyPI 包（npm 上没有）；**必须 `mcp<2`**，否则 mcp-proxy 导入报错 |
| `/browser/mcp` | 25 个 `browser_*` | `@playwright/mcp@0.0.83`（Apache-2.0） | profile `browser`（默认关） | 见下；需单独 token |

读取链接的 **`read_url`** 在 webtool server（`/webtool/mcp`）里，不在这里。

## 已确认的风险（都实测过）

1. **markitdown 能读服务器任意文件**：`convert_to_markdown({"uri":"file:///etc/hostname"})` 直接返回了文件内容。
   它还能访问任意网络地址；一个让它访问自身端口的请求会把它的事件循环卡死，之后连普通 SIGTERM 都杀不掉 —
   所以：internal 网络 + `restart: unless-stopped` + 健康检查，并且**不要把它暴露给不受信任的调用方**。
   远程调用方传附件请用 `data:` URI（已验证可用）。
2. **duckdb 同样能读任意文件**：`read_csv('/etc/hostname')` 成功。只读模式只防写入，不防读文件。
3. **chart 默认数据出站**：不设 `VIS_REQUEST_SERVER` 时，一次调用会把数据发到蚂蚁的公网服务，并返回 `mdn.alipayobjects.com` 上的公网图片地址
   （测试时发送的只是 A/B 两个假数据）。设置后请求体 `{"type":"pie","data":[…],"source":"mcp-server-chart"}` 只发往你指定的服务，
   返回你服务给出的 URL。**私有渲染服务需要自己部署，本仓库没有提供，也没验证过其部署方式。**
   chart 容器没设置该变量会拒绝启动；`generate_*_map` 系列私有部署不支持（上游文档）。
4. **playwright 默认暴露高权限工具**：`browser_run_code_unsafe`（官方称等价 RCE）、`browser_evaluate`、`browser_file_upload`。
   官方也明说它不是安全边界。所以默认不启动，只给持有 `MCP_BROWSER_TOKENS` 的人。
   它自带 Host 校验，放在 Caddy 后面必须用 `--allowed-hosts` 加上对外域名（compose 已处理，实测过不加会 403）。
5. **docling 的 `convert_directory_files_into_docling_document` 会扫描目录**，同样依赖容器隔离。

## 没接入的，以及为什么

| 项 | 决定 | 原因 |
|---|---|---|
| Crawl4AI 自带的 MCP（Docker） | **不接**，改为在 webtool 加 `read_url`（复用已有的 crawl4ai 引擎） | 自托管 MCP 只有 SSE / WebSocket，没有 Streamable HTTP；带 `execute_js` 工具（任意 JS）；文档没写 MCP 如何鉴权，也没有 SSRF 防护；要 ≥4GB 内存 |
| 官方 `fetch` | 不接 | 与 markitdown（http URI）和 `read_url` 重复，且是"替调用方抓任意 URL"，要额外做 SSRF 防护 |
| 官方 `filesystem` / `git` | 不接 | 把服务器文件系统/仓库直接开给远程调用方，没有明确场景；官方也声明这些是教育性参考实现、非生产级。真要用，应只挂一个专用只读卷 |

## 已知缺口

- **没有文件上传通道**：excel / duckdb 操作的是服务器上的文件（`excel-data` / `duckdb-data` 卷，目前只能由管理员放入）。
  markitdown 可用 `data:` URI。远程多人使用要补一个"上传/下载共享工作区"的 server。
- **Docker 镜像都没有在真实环境构建过**（沙箱里没有 Docker 守护进程）。命令和参数是用本地等价环境逐个跑通的，`docker compose config` 也校验过，
  但 Dockerfile 本身（尤其 docling 预下载模型、playwright 装浏览器）需要你构建一次。
- 限流只在 authcheck 里按 token 计数；`read_url` / `web_search` 的并发由 webtool 自己限制。
