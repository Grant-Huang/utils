"""录制文件（recording）的结构、截断规则与校验。录制回放页只展示这种文件。

录制必须来自**真实运行**：record_mcp.py 真实调用 MCP 服务，record_skill.py 真实跑一次 `claude -p`。
这里只做两件被明确标注的事：
  1. 截断：过长的字符串（如 base64 文件内容）替换为 "头部…[已截断，原长 N 字符，sha256 …]"，并在 steps[].truncated 里标 true；
  2. 规范化：把本机网关地址改写成示例域名，记录在 recording.normalized 里。
除此之外，内容原样保留。

schema 1：
{
  "schema": 1, "kind": "mcp" | "skill", "id": "slug", "title": "...", "description": "...",
  "recordedAt": "2026-10-02T04:00:00Z",
  "source": {...},                      # mcp: {plugin, server}; skill: {plugins, model}
  "normalized": ["..."],                # 做过的规范化说明，没有则为空数组
  "steps": [
    {"type": "user", "text": "..."},                                         # 仅 skill
    {"type": "tool_call", "tool": "...", "arguments": {...}},
    {"type": "tool_result", "isError": false, "durationMs": 12,
     "content": [{"type": "text", "text": "..."} | {"type": "resource_link", "uri": "...", "name": "...", "mimeType": "..."}
                 | {"type": "resource", "mimeType": "...", "bytes": 1234}], "truncated": false},
    {"type": "assistant", "text": "..."}                                     # 仅 skill
  ],
  "stats": {"durationMs": 123, "costUsd": 0.1, "model": "..."}              # 可选
}
"""
from __future__ import annotations

import hashlib
import json
import re

MAX_STR = 2000     # 超过这个长度的字符串会被截断
HEAD = 300         # 截断后保留的头部长度
STEP_TYPES = {"user", "assistant", "tool_call", "tool_result"}


def truncate_str(s: str) -> tuple[str, bool]:
    if len(s) <= MAX_STR:
        return s, False
    digest = hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]
    return f"{s[:HEAD]}…[已截断，原长 {len(s)} 字符，sha256 {digest}]", True


def truncate(obj):
    """递归截断；返回 (新对象, 是否发生截断)。"""
    if isinstance(obj, str):
        return truncate_str(obj)
    if isinstance(obj, list):
        pairs = [truncate(x) for x in obj]
        return [p[0] for p in pairs], any(p[1] for p in pairs)
    if isinstance(obj, dict):
        out, hit = {}, False
        for k, v in obj.items():
            out[k], h = truncate(v)
            hit = hit or h
        return out, hit
    return obj, False


def normalize_content(content: list[dict]) -> list[dict]:
    """tool_result.content：内嵌 resource 的 blob 不存（只记大小和类型），其余原样。"""
    out = []
    for c in content or []:
        if c.get("type") == "resource" and isinstance(c.get("resource"), dict):
            r = c["resource"]
            blob = r.get("blob")
            size = (len(blob) * 3) // 4 if isinstance(blob, str) else None
            out.append({"type": "resource", "uri": r.get("uri"), "mimeType": r.get("mimeType"), "bytes": size})
        else:
            out.append(c)
    return out


def rewrite_text(obj, mapping: dict[str, str]):
    """把本机网关地址改写为示例域名（只用于展示，调用方必须在 recording.normalized 里声明）。"""
    if not mapping:
        return obj
    if isinstance(obj, str):
        for a, b in mapping.items():
            obj = obj.replace(a, b)
        return obj
    if isinstance(obj, list):
        return [rewrite_text(x, mapping) for x in obj]
    if isinstance(obj, dict):
        return {k: rewrite_text(v, mapping) for k, v in obj.items()}
    return obj


def validate(rec: dict) -> list[str]:
    """返回问题列表，空列表表示合法。site/check 也用这个函数。"""
    errs = []
    if rec.get("schema") != 1:
        errs.append("schema 必须是 1")
    if rec.get("kind") not in ("mcp", "skill"):
        errs.append("kind 必须是 mcp 或 skill")
    for k in ("id", "title", "recordedAt"):
        if not rec.get(k):
            errs.append(f"缺少 {k}")
    if rec.get("id") and not re.fullmatch(r"[a-z0-9][a-z0-9-]*", rec["id"]):
        errs.append("id 只能用小写字母、数字、连字符")
    steps = rec.get("steps")
    if not isinstance(steps, list) or not steps:
        errs.append("steps 不能为空")
        return errs
    for i, s in enumerate(steps):
        t = s.get("type")
        if t not in STEP_TYPES:
            errs.append(f"steps[{i}] type 非法: {t}")
        elif t == "tool_call" and not s.get("tool"):
            errs.append(f"steps[{i}] tool_call 缺少 tool")
        elif t == "tool_result" and "isError" not in s:
            errs.append(f"steps[{i}] tool_result 缺少 isError")
        elif t in ("user", "assistant") and not isinstance(s.get("text"), str):
            errs.append(f"steps[{i}] {t} 缺少 text")
    # 每个 tool_result 前面必须有对应的 tool_call
    pending = 0
    for s in steps:
        if s.get("type") == "tool_call":
            pending += 1
        elif s.get("type") == "tool_result":
            pending -= 1
            if pending < 0:
                errs.append("tool_result 前面没有对应的 tool_call")
                break
    if rec.get("kind") == "skill" and not any(s.get("type") == "user" for s in steps):
        errs.append("skill 录制必须包含 user 步骤（提问）")
    return errs


def dump(rec: dict) -> str:
    return json.dumps(rec, ensure_ascii=False, indent=2) + "\n"
