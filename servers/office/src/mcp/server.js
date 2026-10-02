// src/mcp/server.js — MCP stdio server（本机被 MCP 客户端以子进程拉起）。
// 注意：stdio 模式下 stdout 只能输出 MCP 消息，日志一律走 stderr。

import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { createMcpServer } from './tools.js';

const server = createMcpServer({ inlineByDefault: true });
await server.connect(new StdioServerTransport());
console.error('[office-mcp] stdio server ready');
