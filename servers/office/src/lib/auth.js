// src/lib/auth.js — HTTP 部署的鉴权与来源校验（与 servers/webtool 使用同一套环境变量约定）
//
//   MCP_AUTH_TOKENS      逗号分隔的 Bearer token；HTTP 模式下至少需要一个
//   MCP_ALLOW_NO_AUTH=1  显式关闭鉴权（仅限本机调试）
//   MCP_ALLOWED_HOSTS    逗号分隔，允许的 Host 头（防 DNS rebinding），例如 "mcp.example.com"
//   MCP_ALLOWED_ORIGINS  逗号分隔，允许的 Origin 头（浏览器跨域调用 /mcp 时需要）

import { timingSafeEqual, createHash } from 'node:crypto';

const csv = (name) => (process.env[name] ?? '').split(',').map(s => s.trim()).filter(Boolean);

export function loadSecurityConfig(port) {
  const tokens = csv('MCP_AUTH_TOKENS');
  if (tokens.length === 0 && process.env.MCP_ALLOW_NO_AUTH !== '1') {
    throw new Error(
      'refusing to start HTTP server without auth: set MCP_AUTH_TOKENS ' +
      '(or MCP_ALLOW_NO_AUTH=1 for local debugging)');
  }
  // 本机访问始终放行；对外域名通过 MCP_ALLOWED_HOSTS 追加
  const hosts = [...csv('MCP_ALLOWED_HOSTS'), `127.0.0.1:${port}`, `localhost:${port}`, '127.0.0.1', 'localhost'];
  return { tokens, hosts, origins: csv('MCP_ALLOWED_ORIGINS') };
}

// 常量时间比较：先哈希成定长再比，避免长度泄露
const digest = (s) => createHash('sha256').update(s).digest();
const safeEqual = (a, b) => timingSafeEqual(digest(a), digest(b));

export function isAuthorized(req, cfg) {
  if (cfg.tokens.length === 0) return true;               // 仅 MCP_ALLOW_NO_AUTH=1 时可能出现
  const h = req.headers.authorization ?? '';
  const supplied = /^bearer /i.test(h) ? h.slice(7) : '';
  return cfg.tokens.some(t => safeEqual(supplied, t));
}

// 返回 null 表示通过，否则返回拒绝原因
export function checkHostAndOrigin(req, cfg) {
  const host = req.headers.host ?? '';
  if (!cfg.hosts.includes(host)) return `host not allowed: ${host}`;
  const origin = req.headers.origin;
  if (origin) {
    // 白名单内，或与 Host 同源（demo 前端自己调用自己）才放行
    let sameOrigin = false;
    try { sameOrigin = new URL(origin).host === host; } catch {}
    if (!cfg.origins.includes(origin) && !sameOrigin) return `origin not allowed: ${origin}`;
  }
  return null;
}
