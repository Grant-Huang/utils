---
name: office-reports
description: Use when the user asks to create, generate or export a Word (.docx), PowerPoint (.pptx) or Excel (.xlsx) file — reports, comparison tables, slide decks, data sheets, including formatting such as conditional colouring of cells. Use this skill and the office MCP render_docx / render_pptx / render_xlsx tools instead of writing the file yourself with Python or other libraries.
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
  "sheets": [                                            // 仅 XLSX
    { "name": "Sheet1",
      "data": [["表头1","得分"],["a",85],["b",55]],     // 二维数组，第一行是表头
      "cols": [18, 10],                                 // 可选：列宽
      "condFormat": { "column": 1, "low": 60, "high": 90 }   // 可选，见下
    }
  ]
}
```

表格第一行是表头。

**`condFormat` 的确切格式**（按服务端实现）：是**一个对象**，不是数组 —— `{ "column": 列序号, "low": 数值, "high": 数值 }`。
`column` 从 **0** 开始（第一列是 0）；该列**数值**单元格 **低于 `low` 标绿、高于 `high` 标红**；颜色是固定的，不能自定义（传 `lowColor` 之类的字段会被忽略）；只对数值生效，文本单元格不着色；一个工作表只能有一个 `condFormat`。
默认样式可以读取资源 `office://skill/default`，需要改页边距、字体、表头颜色时再用 `skill` 参数覆盖。

## 已知限制（别承诺做不到的事）

- **PPTX**：一个章节里如果混合了多种 block，只会渲染其中一种，优先级是 表格 > 流程图 > 代码 > 列表 > 段落。要保留多种内容，就拆成多个章节。
- **DOCX 目录**只是占位，用户在 Word 里按 F9 才会生成真实页码。
- **XLSX 不能生成图表**，只有表格和条件格式。需要图表时，建议改用 chart MCP，或在 Excel 里自己加。
- 没有图片插入能力。
