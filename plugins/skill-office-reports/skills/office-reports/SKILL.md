---
name: office-reports
description: Use when the user asks to produce a Word (.docx), PowerPoint (.pptx) or Excel (.xlsx) file from structured content — reports, comparison tables, slide decks, data sheets. Builds the Document JSON and calls the office MCP render tools.
---

# 生成 Office 文件

通过 office MCP 的三个工具生成文件：`render_docx`、`render_pptx`、`render_xlsx`。

## 步骤

1. 先把内容整理成结构化的 **Document JSON**（见下），不要边想边调工具。
2. 调用对应的 `render_*` 工具，参数：`document`（必填）、`skill`（可选，样式覆盖）、`filename`（可选）、`inline`（可选）。
3. 工具返回一段元数据文本和一个 `resource_link`（下载地址）。**把下载地址和有效期告诉用户**：文件默认只保留约 1 小时，过期要重新生成。
4. 如果用户的客户端打不开链接，用 `inline: true` 重新调用，文件会以内嵌资源的形式返回。
5. 调用失败时结果带 `isError`，错误文本会说明原因。按原因修正 JSON 后重试，不要原样重发。

## Document JSON

```
{
  "meta":   { "creator": "...", "title": "..." },
  "cover":  { "title": "...", "subtitle": "...", "fields": [["标签","值"]], "abstract": "..." },
  "toc": true,
  "header": { "text": "页眉文字" },
  "chapters": [
    { "title": "章节名", "level": 1,
      "blocks": [
        { "type": "paragraph", "text": "..." },
        { "type": "table", "rows": [["列1","列2"],["a","b"]], "caption": "..." },
        { "type": "flowchart", "nodes": [{"label":"步骤1","color":"1F4E79"}] },
        { "type": "code", "title": "...", "code": "..." },
        { "type": "list", "items": ["..."] },        // 仅 PPTX 使用
        { "type": "pagebreak" }
      ] }
  ],
  "references": ["..."],                              // 仅 DOCX
  "sheets": [ { "name": "Sheet1", "data": [["表头1","表头2"],[1,2]] } ]   // 仅 XLSX
}
```

表格第一行是表头。xlsx 的 `data` 是二维数组，第一行是表头，`sheets[].condFormat` 可给某列设高低阈值着色。
默认样式可以读取资源 `office://skill/default`，需要改页边距、字体、表头颜色时再用 `skill` 参数覆盖。

## 已知限制（别承诺做不到的事）

- **PPTX**：一个章节里如果混合了多种 block，只会渲染其中一种，优先级是 表格 > 流程图 > 代码 > 列表 > 段落。要保留多种内容，就拆成多个章节。
- **DOCX 目录**只是占位，用户在 Word 里按 F9 才会生成真实页码。
- **XLSX 不能生成图表**，只有表格和条件格式。需要图表时，建议改用 chart MCP，或在 Excel 里自己加。
- 没有图片插入能力。
