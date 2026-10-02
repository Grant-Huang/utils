# docling-mcp：PDF 结构化解析（OCR、表格结构）。比 markitdown 重得多（[local] 带 torch 与模型）。
# 只加载 conversion 工具组：默认还会加载 generation / manipulation（会改文档），我们不需要。
# conversion 里的 convert_directory_files_into_docling_document 会扫描目录 → 同样必须隔离在无敏感文件、无外网的容器里。
FROM python:3.11-slim
RUN pip install --no-cache-dir "docling-mcp[local]==3.2.1" \
 && useradd -m -s /usr/sbin/nologin app
USER app
# 模型必须在构建阶段下载好：运行时容器在 internal 网络里没有外网。
# ⚠ 未验证：沙箱里装不全 docling 依赖，`docling-tools models download` 的输出目录与运行时是否一致，需在真实构建中确认。
RUN docling-tools models download
ENV HF_HUB_OFFLINE=1
ENV HF_HOME=/home/app/.cache/huggingface
EXPOSE 8000
CMD ["docling-mcp-server", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000", "conversion"]
