// src/http/bridge.js — HTTP 服务：Streamable HTTP MCP 端点 + REST 渲染接口 + demo 前端
//
//   POST /mcp                  MCP（Streamable HTTP，无状态）            需 Bearer
//   POST /render/{docx|pptx|xlsx}  REST 渲染，直接返回二进制              需 Bearer
//   GET  /files/:id/:name      下载 MCP 工具生成的文件（id 为 128 位随机数） 公开(capability)
//   GET  /health  /skill/default  /  (demo 前端静态文件)                   公开
//
// 环境变量：PORT(8911) HOST(127.0.0.1) PUBLIC_BASE_URL MCP_AUTH_TOKENS MCP_ALLOWED_HOSTS
//           MCP_ALLOWED_ORIGINS MCP_ALLOW_NO_AUTH RATE_LIMIT_PER_MIN(60) OFFICE_FILE_TTL_SECONDS(3600)

import http from 'node:http';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { render, listFormats } from '../lib/render.js';
import { defaultSkill } from '../lib/skills/default.js';
import { loadSecurityConfig, isAuthorized, checkHostAndOrigin } from '../lib/auth.js';
import { readFile, sweep, safeFilename } from '../lib/filestore.js';
import { createMcpServer, MIME } from '../mcp/tools.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = path.resolve(__dirname, '../../public');
const PORT = Number(process.env.PORT) || 8911;
const HOST = process.env.HOST || '127.0.0.1';          // 容器内用 HOST=0.0.0.0，由反向代理对外
const MAX_BODY = 10 * 1024 * 1024;                     // 10MB，防止超大请求体
const RATE_LIMIT = Number(process.env.RATE_LIMIT_PER_MIN) || 60;
const PUBLIC_BASE_URL = (process.env.PUBLIC_BASE_URL || '').replace(/\/+$/, '');

const security = loadSecurityConfig(PORT);             // 未配置 token 且未显式允许 → 直接抛错退出

const STATIC_MIME = {
  html: 'text/html; charset=utf-8', js: 'application/javascript; charset=utf-8',
  css: 'text/css; charset=utf-8', json: 'application/json; charset=utf-8',
};

// ---- helpers ---------------------------------------------------------------

class HttpError extends Error { constructor(status, message) { super(message); this.status = status; } }

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = []; let size = 0;
    req.on('data', c => {
      size += c.length;
      if (size > MAX_BODY) { reject(new HttpError(413, 'request body too large')); req.destroy(); return; }
      chunks.push(c);
    });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

// CORS：不再使用 `*`。只对白名单 Origin 回显；同源请求不需要 CORS 头。
function applyCors(req, res) {
  const origin = req.headers.origin;
  if (origin && security.origins.includes(origin)) {
    res.setHeader('access-control-allow-origin', origin);
    res.setHeader('vary', 'Origin');
    res.setHeader('access-control-allow-headers', 'authorization, content-type, mcp-protocol-version, mcp-session-id');
    res.setHeader('access-control-allow-methods', 'GET,POST,OPTIONS');
  }
}

function sendJson(res, code, body, headers = {}) {
  res.writeHead(code, { 'content-type': 'application/json; charset=utf-8', ...headers });
  res.end(JSON.stringify(body));
}

// 简单固定窗口限流（每个 token / IP 每分钟 RATE_LIMIT 次）。多实例部署应放到网关层。
const windows = new Map();
function rateLimited(key) {
  const minute = Math.floor(Date.now() / 60000);
  const w = windows.get(key);
  if (!w || w.minute !== minute) { windows.set(key, { minute, n: 1 }); return false; }
  return ++w.n > RATE_LIMIT;
}
setInterval(() => { const m = Math.floor(Date.now() / 60000); for (const [k, w] of windows) if (w.minute < m) windows.delete(k); }, 60000).unref();

// 需要鉴权的接口统一走这里；返回 false 表示已经写出拒绝响应
function guard(req, res) {
  const bad = checkHostAndOrigin(req, security);
  if (bad) { sendJson(res, 403, { error: bad }); return false; }
  if (!isAuthorized(req, security)) {
    sendJson(res, 401, { error: 'unauthorized' }, { 'www-authenticate': 'Bearer' }); return false;
  }
  const key = (req.headers.authorization ?? '') || req.socket.remoteAddress || 'anon';
  if (rateLimited(key)) { sendJson(res, 429, { error: 'rate limit exceeded' }, { 'retry-after': '60' }); return false; }
  return true;
}

function serveStatic(res, urlPath) {
  const rel = urlPath === '/' ? 'index.html' : decodeURIComponent(urlPath).replace(/^\/+/, '');
  const filePath = path.resolve(PUBLIC_DIR, rel);
  // 注意要带分隔符：否则 /public-evil 这类前缀相同的目录会绕过检查
  if (!filePath.startsWith(PUBLIC_DIR + path.sep)) return sendJson(res, 403, { error: 'forbidden' });
  try {
    const body = readFileSync(filePath);
    res.writeHead(200, { 'content-type': STATIC_MIME[path.extname(filePath).slice(1).toLowerCase()] || 'application/octet-stream' });
    res.end(body);
  } catch { sendJson(res, 404, { error: 'not found' }); }
}

// 文件下载地址前缀：优先用 PUBLIC_BASE_URL（反向代理带路径前缀时必须设置）；否则按已校验的 Host 推导
const getBaseUrl = (extra) => PUBLIC_BASE_URL ||
  (extra?.requestInfo?.headers?.host ? `http://${extra.requestInfo.headers.host}` : undefined);

// ---- MCP endpoint (stateless: 每个请求一个 server + transport) -----------------

async function handleMcp(req, res) {
  if (req.method !== 'POST') {
    // 无状态模式不提供 GET 的 SSE 流，也没有会话可 DELETE（规范允许返回 405）
    return sendJson(res, 405, { jsonrpc: '2.0', error: { code: -32000, message: 'Method not allowed.' }, id: null }, { allow: 'POST' });
  }
  if (!guard(req, res)) return;
  let parsed;
  try { parsed = JSON.parse((await readBody(req)).toString('utf8')); }
  catch (e) {
    if (e instanceof HttpError) return sendJson(res, e.status, { error: e.message });
    return sendJson(res, 400, { jsonrpc: '2.0', error: { code: -32700, message: 'Parse error' }, id: null });
  }
  const server = createMcpServer({ getBaseUrl, inlineByDefault: false });
  const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
  res.on('close', () => { transport.close(); server.close(); });
  await server.connect(transport);
  await transport.handleRequest(req, res, parsed);
}

// ---- server ---------------------------------------------------------------------

const server = http.createServer(async (req, res) => {
  try {
    applyCors(req, res);
    if (req.method === 'OPTIONS') { res.writeHead(204); return res.end(); }

    const url = new URL(req.url, 'http://placeholder');
    const hostBad = checkHostAndOrigin({ headers: { host: req.headers.host } }, security);  // Host 对所有路径生效
    if (hostBad) return sendJson(res, 403, { error: hostBad });

    if (url.pathname === '/mcp') return await handleMcp(req, res);

    if (req.method === 'GET' && url.pathname === '/health') {
      return sendJson(res, 200, { ok: true, formats: listFormats(), skill: defaultSkill.name, auth: security.tokens.length > 0 });
    }
    if (req.method === 'GET' && url.pathname === '/skill/default') return sendJson(res, 200, defaultSkill);

    const f = url.pathname.match(/^\/files\/([^/]+)\/([^/]+)$/);
    if (req.method === 'GET' && f) {
      const name = decodeURIComponent(f[2]);
      const buf = readFile(f[1], name);
      if (!buf) return sendJson(res, 404, { error: 'not found or expired' });
      const fmt = path.extname(name).slice(1);
      res.writeHead(200, {
        'content-type': MIME[fmt] ?? 'application/octet-stream',
        'content-length': buf.length,
        'content-disposition': `attachment; filename*=UTF-8''${encodeURIComponent(name)}`,
        'x-content-type-options': 'nosniff',
      });
      return res.end(buf);
    }

    // POST /render/:fmt  body = { document, skill?, filename? }
    const m = url.pathname.match(/^\/render\/(docx|pptx|xlsx)$/);
    if (req.method === 'POST' && m) {
      if (!guard(req, res)) return;
      let body;
      try { body = JSON.parse((await readBody(req)).toString('utf8')); }
      catch (e) { return sendJson(res, e.status ?? 400, { error: e.status ? e.message : 'invalid JSON body' }); }
      try {
        const buf = await render(m[1], body.document ?? {}, body.skill ?? {});
        const filename = safeFilename(body.filename, m[1]);
        res.writeHead(200, {
          'content-type': MIME[m[1]], 'content-length': buf.length,
          'content-disposition': `attachment; filename*=UTF-8''${encodeURIComponent(filename)}`,
        });
        return res.end(buf);
      } catch (err) { return sendJson(res, 500, { error: String(err?.message ?? err) }); }
    }

    if (req.method === 'GET') return serveStatic(res, url.pathname);
    sendJson(res, 405, { error: 'method not allowed' });
  } catch (err) {
    if (res.headersSent) return res.end();
    console.error('[office-mcp] unhandled', err);
    sendJson(res, err.status ?? 500, { error: err.status ? err.message : 'internal error' });
  }
});

setInterval(sweep, 10 * 60 * 1000).unref();           // 定期清理过期的生成文件
server.listen(PORT, HOST, () => {
  console.log(`[office-mcp] listening on http://${HOST}:${PORT}  (auth: ${security.tokens.length ? 'bearer' : 'DISABLED'})`);
  console.log('[office-mcp] POST /mcp · POST /render/{docx,pptx,xlsx} · GET /files/:id/:name · GET /health · GET /');
});
