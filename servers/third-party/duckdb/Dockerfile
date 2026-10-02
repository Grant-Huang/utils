# mcp-server-motherduck：对 DuckDB 文件做 SQL 分析。默认只读（写入被拒，已实测）。
# 已实测：DuckDB 可直接 read_csv / read_xlsx 查文件；但它同样能读容器内任意文件和访问网络 → 必须隔离（internal 网络、/data 只读挂载）。
FROM python:3.11-slim
RUN pip install --no-cache-dir "mcp-server-motherduck==1.0.8" \
 && useradd -m -s /usr/sbin/nologin app && mkdir /data && chown app /data
COPY --chmod=755 entrypoint.sh /entrypoint.sh
USER app
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
