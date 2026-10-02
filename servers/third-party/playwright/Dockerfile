# @playwright/mcp：浏览器自动化。⚠ 官方明说"不是安全边界"，且默认暴露 browser_run_code_unsafe（等价 RCE）、
# browser_evaluate、browser_file_upload（已实测）。只作为"专用通道"：单独的 MCP_BROWSER_TOKENS，默认不启动（compose profile: browser）。
# 没有在真实容器里构建过；--allowed-hosts 必须包含对外域名，否则它会 403（已实测其 Host 校验）。
FROM node:22-slim
RUN npm install -g @playwright/mcp@0.0.83 \
 && npx playwright install --with-deps chromium \
 && useradd -m -s /usr/sbin/nologin app
USER app
EXPOSE 8931
# ALLOWED_HOSTS 由 compose 传入
CMD ["sh", "-c", "exec playwright-mcp --headless --isolated --no-sandbox --host 0.0.0.0 --port 8931 --allowed-hosts \"$ALLOWED_HOSTS\""]
