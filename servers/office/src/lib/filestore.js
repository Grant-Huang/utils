// src/lib/filestore.js — 生成文件的临时存储 + 下载 URL
// 远程调用者拿到的是 resource_link（下载地址），而不是塞进 JSON-RPC 的 base64。
// 下载 URL 里的 id 是 128 位随机数（unguessable capability），文件 TTL 到期自动清理。

import { randomUUID } from 'node:crypto';
import { mkdirSync, writeFileSync, readFileSync, rmSync, readdirSync, statSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

const DIR = process.env.OFFICE_FILE_DIR || path.join(tmpdir(), 'office-mcp-files');
export const FILE_TTL_MS = Number(process.env.OFFICE_FILE_TTL_SECONDS || 3600) * 1000;

const ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

// 文件名只保留安全字符并强制扩展名，杜绝路径穿越 / 头注入
export function safeFilename(name, fmt) {
  let base = String(name ?? '').replace(/\.[^.]*$/, '')
    .replace(/[^\p{L}\p{N}_\-. ]/gu, '_').replace(/\.{2,}/g, '.').replace(/^\.+/, '').slice(0, 80).trim();
  if (!base) base = 'report';
  return `${base}.${fmt}`;
}

export function saveFile(buf, filename) {
  const id = randomUUID();
  mkdirSync(path.join(DIR, id), { recursive: true });
  writeFileSync(path.join(DIR, id, filename), buf);
  return { id, expiresAt: new Date(Date.now() + FILE_TTL_MS).toISOString() };
}

// id 与文件名都必须过白名单，且解析后的路径必须仍在 DIR 内
export function readFile(id, filename) {
  if (!ID_RE.test(id) || filename !== path.basename(filename)) return null;
  const p = path.join(DIR, id, filename);
  if (!p.startsWith(DIR + path.sep) || !existsSync(p)) return null;
  if (Date.now() - statSync(p).mtimeMs > FILE_TTL_MS) return null;
  return readFileSync(p);
}

export function sweep() {
  if (!existsSync(DIR)) return;
  for (const id of readdirSync(DIR)) {
    const d = path.join(DIR, id);
    try { if (Date.now() - statSync(d).mtimeMs > FILE_TTL_MS) rmSync(d, { recursive: true, force: true }); } catch {}
  }
}
