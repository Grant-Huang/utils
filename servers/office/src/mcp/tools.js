// src/mcp/tools.js — 用官方 SDK 注册 MCP 工具（stdio 与 Streamable HTTP 共用）
//
// 返回内容遵循 MCP 规范的 content 类型：
//   · HTTP 模式（有下载地址）：text(元数据) + resource_link(下载 URL)
//   · stdio 模式 / inline=true：text(元数据) + resource(内嵌 blob，base64)
// 渲染失败不抛协议错误，而是 isError:true，让模型能读到原因并重试。

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import { render, listFormats } from '../lib/render.js';
import { defaultSkill } from '../lib/skills/default.js';
import { saveFile, safeFilename, FILE_TTL_MS } from '../lib/filestore.js';

export const MIME = {
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
};

const describe = (fmt) =>
  `Generate a ${fmt.toUpperCase()} file from a structured Document JSON model. ` +
  `The Document is an object: { cover?, toc?, chapters:[{title,level,blocks:[paragraph|table|flowchart|code|pagebreak|list]}], sheets? (xlsx only), references?, meta? }. ` +
  `Optional skill overrides: page, body, heading, table, code, header, footer, theme, font (read resource office://skill/default for defaults). ` +
  `Returns a download link (HTTP) or an embedded file resource (stdio).`;

/**
 * @param {{ getBaseUrl?: (extra:any)=>string|undefined, inlineByDefault: boolean }} opts
 *   getBaseUrl 返回文件下载地址前缀；未提供则只能 inline。
 */
export function createMcpServer({ getBaseUrl, inlineByDefault }) {
  const server = new McpServer({ name: 'office-mcp', version: '0.2.0' });

  for (const fmt of listFormats()) {
    server.registerTool(`render_${fmt}`, {
      title: `Render ${fmt.toUpperCase()}`,
      description: describe(fmt),
      inputSchema: {
        document: z.record(z.string(), z.any()).describe('Document model JSON. See README for the full shape.'),
        skill: z.record(z.string(), z.any()).optional().describe('Optional style overrides merged onto the defaults.'),
        filename: z.string().max(120).optional().describe(`Suggested filename (default report.${fmt}).`),
        inline: z.boolean().optional().describe('Embed the file bytes in the result instead of returning a download link.'),
      },
      annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: false },
    }, async (args, extra) => {
      try {
        const buf = await render(fmt, args.document, args.skill ?? {});
        const filename = safeFilename(args.filename, fmt);
        const meta = { filename, bytes: buf.length, mime: MIME[fmt] };
        const baseUrl = getBaseUrl?.(extra);
        const inline = args.inline ?? (inlineByDefault || !baseUrl);

        if (inline) {
          return { content: [
            { type: 'text', text: JSON.stringify(meta) },
            { type: 'resource', resource: {
              uri: `office-mcp://generated/${encodeURIComponent(filename)}`,
              mimeType: MIME[fmt], blob: Buffer.from(buf).toString('base64'),
            } },
          ] };
        }
        const { id, expiresAt } = saveFile(buf, filename);
        const url = `${baseUrl}/files/${id}/${encodeURIComponent(filename)}`;
        return { content: [
          { type: 'text', text: JSON.stringify({ ...meta, url, expires_at: expiresAt, ttl_seconds: FILE_TTL_MS / 1000 }) },
          { type: 'resource_link', uri: url, name: filename, mimeType: MIME[fmt] },
        ] };
      } catch (err) {
        return { isError: true, content: [{ type: 'text', text: `render_${fmt} failed: ${err?.message ?? err}` }] };
      }
    });
  }

  server.registerResource('default-skill', 'office://skill/default', {
    title: 'Default skill', description: 'Default style values that `skill` overrides are merged onto.',
    mimeType: 'application/json',
  }, async (uri) => ({ contents: [{ uri: uri.href, mimeType: 'application/json', text: JSON.stringify(defaultSkill, null, 2) }] }));

  return server;
}
