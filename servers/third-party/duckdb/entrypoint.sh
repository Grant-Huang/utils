#!/bin/sh
# 只读模式要求库文件已存在；首次启动时建一个空库，之后由管理员往 /data 里放数据或 CSV/xlsx。
set -e
DB=/data/analytics.duckdb
[ -f "$DB" ] || python -c "import duckdb; duckdb.connect('$DB').close()"
exec mcp-server-motherduck --transport http --host 0.0.0.0 --port 8000 --db-path "$DB"
