## 它能做什么

上游是 Docling 项目的 MCP 服务，定位是 PDF 的结构化解析，包括 OCR 和表格结构识别，比 MarkItDown 更重、更慢，适合扫描件和版面复杂的文档。

我们只加载 `conversion` 工具组（默认还会加载会修改文档的 generation / manipulation 组，我们不需要）。工具共 4 个：

- `convert_document_into_docling_document`（参数 `source`）
- `convert_directory_files_into_docling_document`（参数 `source`，**会扫描目录**）
- `is_document_in_local_cache`、`drop_document_from_local_cache`

## 实测与未实测

- **已实测**：服务能以 Streamable HTTP 启动，只加载 `conversion` 组，工具列表如上。
- **未实测**：真实的文档转换。沙箱里没有 Docling 的模型和网络，所以转换效果、OCR 质量、速度都没有验证。
- **镜像未构建**：模型需要在构建阶段预下载（运行时容器没有外网），`docling-tools models download` 的效果需要在真实构建里确认。

## 安全

转换工具接受 URL 或路径，目录扫描工具会读目录，所以和 MarkItDown 一样必须放在无外网出口、无敏感文件的隔离容器里。

## 资源

镜像大（带 torch 与模型），compose 里给了 6 GB 内存上限。

## 相关

配套 Skill：`skill-read-attachments`。
