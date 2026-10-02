## 它能做什么

把一份结构化的 **Document JSON** 渲染成 `.docx` / `.pptx` / `.xlsx`。三个工具对应三种格式：`render_docx`、`render_pptx`、`render_xlsx`。
自研服务，基于 docx-js、pptxgenjs、xlsx-js-style。

## 返回什么

- **HTTP 调用**：返回一段元数据文本和一个 `resource_link`（下载地址）。文件默认只保留约 1 小时（`OFFICE_FILE_TTL_SECONDS` 可改）。
- **stdio 调用或传 `inline: true`**：文件以内嵌资源（base64）返回。
- 渲染失败时返回 `isError: true` 和原因，不是协议错误，模型可以据此修正后重试。

## 适合 / 不适合

- 适合：把整理好的内容一次性输出成报告、对比表、幻灯片、数据表。
- 不适合：修改**已有**文件（用 `mcp-excel` 改 xlsx）；插入图片；生成 xlsx 图表（本服务不支持，可配合 `mcp-chart`）。

## 已知限制

- PPTX：一个章节里混合多种内容块时，只渲染其中一种（优先级：表格 > 流程图 > 代码 > 列表 > 段落），需要拆成多个章节。
- DOCX 的目录只是占位，需要在 Word 里按 F9 刷新。
- 单次请求体上限 10 MB。

## 相关

配套 Skill：`skill-office-reports`（教模型怎么组织 Document JSON 并交付链接）。
