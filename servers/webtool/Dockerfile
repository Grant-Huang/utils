# webtool MCP server（Python）。体积大户是 torch(sentence-transformers) 和 chromium：
#   docker build --build-arg EXTRAS=rerank,crawl4ai ...   按需裁剪（默认 all）
FROM python:3.11-slim
ARG EXTRAS=all
WORKDIR /app
ENV PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8912 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
COPY pyproject.toml ./
COPY webtool ./webtool
RUN pip install --no-cache-dir ".[${EXTRAS}]"
# 浏览器：仅当装了 playwright / crawl4ai 时才需要
RUN if pip show playwright >/dev/null 2>&1; then python -m playwright install --with-deps chromium; fi
RUN useradd -m app && chown -R app /app && ( [ ! -d /ms-playwright ] || chown -R app /ms-playwright )
USER app
EXPOSE 8912
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8912/health').status==200 else 1)"
CMD ["python", "-m", "webtool.server", "--transport", "http"]
