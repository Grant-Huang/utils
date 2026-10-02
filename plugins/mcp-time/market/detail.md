## 它能做什么

两个工具：`get_current_time`（指定时区的当前时间）、`convert_time`（时区换算）。一次调用就能回答"现在几点"，不必让模型去执行 shell。

## 部署方式

上游是官方参考实现，**只有 stdio**，是 **PyPI 包**（npm 上没有）。我们用 `mcp-proxy` 把它包成 Streamable HTTP。
版本坑（已实测）：`mcp-proxy 0.12.0` 与 `mcp 2.x` 不兼容（导入报错），镜像里钉了 `mcp<2`。

## 说明

官方声明这类参考服务是教育性实现、非生产级；time 只做时区换算，风险最低。
服务自己报告的版本是 mcp 库的版本，不是 `mcp-server-time` 的版本，以我们钉死的包版本为准。
