# markitdown-mcp：PDF/Word/PPT/Excel/HTML/ZIP → Markdown。
# ⚠ 官方明说：无鉴权，且 convert_to_markdown 能读容器内任意文件、访问任意网络地址（已实测 file:///etc/hostname 可读）。
#   所以：容器里不放任何敏感文件/密钥；compose 里放在 internal 网络（无外网出口）；入口由 Caddy+authcheck 鉴权。
# 版本：PyPI 上只有 alpha（0.0.1a7），必须钉版本。
FROM python:3.11-slim
RUN pip install --no-cache-dir "markitdown-mcp==0.0.1a7" \
 && useradd -m -s /usr/sbin/nologin app
USER app
EXPOSE 3001
# 没有 /health 端点：用一次真实的 MCP initialize 当健康检查（实测过它会被一个请求卡死，见 README）
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request as u,json,sys;r=u.Request('http://127.0.0.1:3001/mcp',json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'hc','version':'0'}}}).encode(),{'content-type':'application/json','accept':'application/json, text/event-stream'});sys.exit(0 if u.urlopen(r,timeout=4).status==200 else 1)"
CMD ["markitdown-mcp", "--http", "--host", "0.0.0.0", "--port", "3001"]
