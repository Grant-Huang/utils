# excel-mcp-server：不装 Excel 读写 xlsx（公式、图表、条件格式等）。自带 Bearer token + 目录白名单。
# 绑 0.0.0.0 时它会拒绝在没有 EXCEL_MCP_AUTH_TOKEN 的情况下启动（已实测），所以 compose 必须传内部 token。
FROM python:3.11-slim
RUN pip install --no-cache-dir "excel-mcp-server==1.1.1" \
 && useradd -m -s /usr/sbin/nologin app && mkdir /data && chown app /data
USER app
EXPOSE 8017
CMD ["excel-mcp-server", "streamable-http", "--allow-dir", "/data", "--host", "0.0.0.0", "--port", "8017"]
