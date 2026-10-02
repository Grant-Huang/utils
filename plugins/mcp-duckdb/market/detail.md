## 它能做什么

对一个 DuckDB 文件跑 SQL（`execute_query`），另有 `list_databases`、`list_tables`、`list_columns` 等。适合"统计调用次数、按时间段汇总"这类分析请求。

## 实测结果

- **能直接查文件**：`read_csv('…')` 和 `read_xlsx('…')` 都成功（xlsx 用 openpyxl 生成的文件实测）。
- **默认只读**：`CREATE TABLE` 被拒（`attached in read-only mode`）。
- 内存库必须加 `--read-write`，所以我们用文件库。

## ⚠ 只读 ≠ 安全

只读只防写入，**不防读文件**。我们实测：`SELECT * FROM read_csv('/etc/hostname', header=false)` 成功读到了服务器文件。
所以必须隔离：`internal` 网络（无外网）、`/data` 只读挂载、容器里不放密钥。

## 文件从哪来

数据由管理员放进 `duckdb-data` 卷，目前没有远程上传通道。

## 许可

上游包元数据里没有声明 license，商用前请到上游仓库确认。
