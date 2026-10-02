## 它能做什么

25 个 `browser_*` 工具：导航、点击、填表、截图、读取页面快照、执行 JavaScript 等。基于无障碍快照，而不是截图。

## ⚠ 高权限，专用通道

实测默认就暴露了 `browser_run_code_unsafe`（官方文档称其**等价于远程代码执行**）、`browser_evaluate` 和 `browser_file_upload`。
官方也明说它**不是安全边界**。所以我们：

- 默认**不启动**（compose 里是 `browser` profile）；
- 只认**单独的 `MCP_BROWSER_TOKENS`**，普通 token 进不去（已实测）；
- 它需要外网，不能放进无外网的隔离网络。

## 部署注意

它自带 Host 校验，放在网关后面必须用 `--allowed-hosts` 加上对外域名，否则返回 403（已实测）。
它是有状态会话（`Mcp-Session-Id`）。

## 适用场景

只适合"需要登录后操作网页"的专用场景，不要当作默认工具。
