# mcp-server-time（官方参考实现，PyPI 包；npm 上没有）。只有 stdio，用 mcp-proxy 包成 Streamable HTTP。
# 版本坑（已实测）：mcp-proxy 0.12.0 与 mcp 2.x 不兼容（ImportError: request_ctx），必须 mcp<2。
# 官方声明这些是"教育性参考实现，非生产级"；time 只做时区换算，无文件/网络访问，风险最低。
FROM python:3.11-slim
RUN pip install --no-cache-dir "mcp<2" "mcp-proxy==0.12.0" "mcp-server-time==2026.8.18" \
 && useradd -m -s /usr/sbin/nologin app
USER app
EXPOSE 8080
CMD ["mcp-proxy", "--transport", "streamablehttp", "--stateless", "--host", "0.0.0.0", "--port", "8080", "--", "mcp-server-time"]
