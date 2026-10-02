// 端到端测试：真实启动 HTTP 服务 / stdio 子进程，用官方 MCP 客户端调用。  运行：npm test
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const example = JSON.parse(readFileSync(path.join(root, 'examples/asr-report.json'), 'utf8'));
const PORT = Number(process.env.TEST_PORT) || 38911, BASE = `http://127.0.0.1:${PORT}`, TOKEN = 'test-token';
let proc;

before(async () => {
  proc = spawn('node', ['src/http/bridge.js'], {
    cwd: root, env: { ...process.env, PORT, MCP_AUTH_TOKENS: TOKEN, RATE_LIMIT_PER_MIN: '1000' }, stdio: 'pipe',
  });
  await new Promise((resolve, reject) => {
    proc.stdout.on('data', d => String(d).includes('listening') && resolve());
    proc.on('exit', c => reject(new Error(`server exited early: ${c}`)));
    setTimeout(() => reject(new Error('server start timeout')), 10000);
  });
});
after(() => proc?.kill());

const httpClient = async (token = TOKEN) => {
  const c = new Client({ name: 'test', version: '0' });
  await c.connect(new StreamableHTTPClientTransport(new URL(`${BASE}/mcp`), {
    requestInit: { headers: token ? { authorization: `Bearer ${token}` } : {} },
  }));
  return c;
};

test('refuses to start without auth config', async () => {
  const p = spawn('node', ['src/http/bridge.js'], { cwd: root, env: { ...process.env, PORT: '38912', MCP_AUTH_TOKENS: '' }, stdio: 'pipe' });
  const code = await new Promise(r => p.on('exit', r));
  assert.notEqual(code, 0);
});

test('health is public, /mcp and /render need a token', async () => {
  assert.equal((await fetch(`${BASE}/health`)).status, 200);
  const rpc = { jsonrpc: '2.0', id: 1, method: 'tools/list' };
  const h = { 'content-type': 'application/json', accept: 'application/json, text/event-stream' };
  assert.equal((await fetch(`${BASE}/mcp`, { method: 'POST', headers: h, body: JSON.stringify(rpc) })).status, 401);
  assert.equal((await fetch(`${BASE}/mcp`, { method: 'POST', headers: { ...h, authorization: 'Bearer nope' }, body: JSON.stringify(rpc) })).status, 401);
  assert.equal((await fetch(`${BASE}/render/docx`, { method: 'POST', headers: h, body: '{}' })).status, 401);
});

test('foreign Origin and bad Host are rejected', async () => {
  const h = { 'content-type': 'application/json', accept: 'application/json, text/event-stream', authorization: `Bearer ${TOKEN}` };
  const body = JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list' });
  assert.equal((await fetch(`${BASE}/mcp`, { method: 'POST', headers: { ...h, origin: 'https://evil.example' }, body })).status, 403);
  // Node 的 fetch 不允许改 Host，这里用原始 http 请求验证
  const http = await import('node:http');
  const status = await new Promise(res => {
    const r = http.request({ port: PORT, host: '127.0.0.1', method: 'POST', path: '/mcp', headers: { ...h, host: 'evil.example' } }, x => res(x.statusCode));
    r.end(body);
  });
  assert.equal(status, 403);
});

test('static path traversal is blocked', async () => {
  const http = await import('node:http');
  const status = await new Promise(res => http.get({ port: PORT, host: '127.0.0.1', path: '/..%2fpackage.json' }, x => res(x.statusCode)));
  assert.ok([403, 404].includes(status));
  assert.equal((await fetch(`${BASE}/`)).status, 200);          // demo 前端仍可访问
});

test('MCP over HTTP: list tools, render returns resource_link, link downloads a real docx', async () => {
  const c = await httpClient();
  const { tools } = await c.listTools();
  assert.deepEqual(tools.map(t => t.name).sort(), ['render_docx', 'render_pptx', 'render_xlsx']);
  const r = await c.callTool({ name: 'render_docx', arguments: { document: example, filename: '../../evil name.docx' } });
  assert.ok(!r.isError);
  const link = r.content.find(x => x.type === 'resource_link');
  assert.ok(link, 'expected resource_link');
  assert.ok(!link.uri.includes('..'), 'filename must be sanitised');
  const dl = await fetch(link.uri);
  assert.equal(dl.status, 200);
  const bytes = Buffer.from(await dl.arrayBuffer());
  assert.equal(bytes.subarray(0, 2).toString(), 'PK');          // docx 是 zip
  await c.close();
});

test('download endpoint rejects bad ids', async () => {
  assert.equal((await fetch(`${BASE}/files/not-a-uuid/x.docx`)).status, 404);
  assert.equal((await fetch(`${BASE}/files/00000000-0000-4000-8000-000000000000/x.docx`)).status, 404);
});

test('inline=true embeds the file as a resource blob', async () => {
  const c = await httpClient();
  const ex = JSON.parse(readFileSync(path.join(root, 'examples/asr-report.xlsx.json'), 'utf8'));
  const r = await c.callTool({ name: 'render_xlsx', arguments: { document: ex, inline: true } });
  const res = r.content.find(x => x.type === 'resource');
  assert.equal(Buffer.from(res.resource.blob, 'base64').subarray(0, 2).toString(), 'PK');
  await c.close();
});

test('render failure is isError, not a protocol error', async () => {
  const c = await httpClient();
  const r = await c.callTool({ name: 'render_xlsx', arguments: { document: { sheets: [{ name: 'x', data: 'not-an-array' }] } } });
  assert.equal(r.isError, true);
  assert.match(r.content[0].text, /render_xlsx failed/);
  await c.close();
});

test('skill resource is readable', async () => {
  const c = await httpClient();
  const out = await c.readResource({ uri: 'office://skill/default' });
  assert.equal(JSON.parse(out.contents[0].text).name, 'office-d/v1');
  await c.close();
});

test('REST /render still works (demo front-end path)', async () => {
  const r = await fetch(`${BASE}/render/pptx`, {
    method: 'POST', headers: { 'content-type': 'application/json', authorization: `Bearer ${TOKEN}` },
    body: JSON.stringify({ document: JSON.parse(readFileSync(path.join(root, 'examples/asr-report.pptx.json'), 'utf8')), filename: 'a.pptx' }),
  });
  assert.equal(r.status, 200);
  assert.equal(Buffer.from(await r.arrayBuffer()).subarray(0, 2).toString(), 'PK');
});

test('MCP over stdio: embeds the file inline', async () => {
  const c = new Client({ name: 'test', version: '0' });
  await c.connect(new StdioClientTransport({ command: 'node', args: ['src/mcp/server.js'], cwd: root }));
  const r = await c.callTool({ name: 'render_docx', arguments: { document: example } });
  const res = r.content.find(x => x.type === 'resource');
  assert.ok(res, 'stdio should embed the blob');
  assert.equal(Buffer.from(res.resource.blob, 'base64').subarray(0, 2).toString(), 'PK');
  await c.close();
});

// ---- 回归：xlsx 颜色必须是合法的 8 位 ARGB（曾因重复拼 FF 前缀生成 10 位的 FFFF1F4E79） ----
import JSZip from 'jszip';
import { argb } from '../src/lib/renderers/xlsx.js';

async function stylesRgb(buf) {
  const zip = await JSZip.loadAsync(buf);
  const xml = await zip.file('xl/styles.xml').async('string');
  return [...xml.matchAll(/rgb="([^"]*)"/g)].map(m => m[1]);
}

test('argb() normalises the accepted colour spellings and rejects the rest', () => {
  assert.equal(argb('70AD47'), 'FF70AD47');
  assert.equal(argb('#70ad47'), 'FF70AD47');
  assert.equal(argb('FF70AD47'), 'FF70AD47');
  for (const bad of ['red', '70AD4', 'FFFF1F4E79', '', undefined]) assert.throws(() => argb(bad), /invalid color/);
});

test('xlsx with the default skill only contains valid ARGB colours', async () => {
  const { render } = await import('../src/lib/render.js');
  const buf = await render('xlsx', JSON.parse(readFileSync(path.join(root, 'examples/asr-report.xlsx.json'), 'utf8')), {});
  const colours = await stylesRgb(buf);
  assert.ok(colours.length > 0);
  for (const c of colours) assert.match(c, /^[0-9A-F]{8}$/, `invalid colour in styles.xml: ${c}`);
});

test('headerFill accepts 6-digit and #-prefixed colours; an invalid one is a clear isError', async () => {
  const c = await httpClient();
  const doc = (fill) => ({ sheets: [{ name: 'S', headerFill: fill, data: [['a', 'b'], [1, 2]] }] });
  for (const fill of ['70AD47', '#70AD47']) {
    const r = await c.callTool({ name: 'render_xlsx', arguments: { document: doc(fill), inline: true } });
    assert.ok(!r.isError, `fill ${fill} should work`);
    const blob = r.content.find(x => x.type === 'resource').resource.blob;
    assert.ok((await stylesRgb(Buffer.from(blob, 'base64'))).includes('FF70AD47'));
  }
  const bad = await c.callTool({ name: 'render_xlsx', arguments: { document: doc('red') } });
  assert.equal(bad.isError, true);
  assert.match(bad.content[0].text, /invalid color/);
  await c.close();
});
