"""SSRF 防护：read_url 这类"让服务器替调用方去抓任意 URL"的工具必须先过这一关。

规则（任何一条不满足就拒绝）：
  · 只允许 http / https，且不能带 user:pass@
  · 端口只允许 80 / 443 / 8080 / 8443（WEBTOOL_ALLOWED_PORTS 可改），防止拿它扫内网端口
  · 主机名解析出的**每一个** IP 都必须是公网地址（ipaddress.is_global）：
    挡掉回环、内网 10/172.16/192.168、链路本地（含云厂商元数据 169.254.169.254）、CGNAT、组播、保留地址；
    IPv4-mapped IPv6（::ffff:127.0.0.1）会先还原再判断
  · WEBTOOL_ALLOW_PRIVATE_URLS=1 可整体关闭（仅限本机开发）

局限（诚实说明）：这是"请求前校验"。DNS rebinding（校验后域名改指内网）无法在应用层完全杜绝；
crawl4ai / playwright 的重定向由浏览器自己处理，只能在抓取后校验最终 URL 并拒绝返回内容。
真正可靠的兜底是网络层：给容器配置出站规则，禁止访问内网网段和元数据地址。
"""
from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlsplit


def _allowed_ports() -> set[int]:
    raw = os.environ.get("WEBTOOL_ALLOWED_PORTS", "80,443,8080,8443")
    return {int(p) for p in raw.split(",") if p.strip()}


def _is_public(ip_text: str) -> bool:
    ip = ipaddress.ip_address(ip_text.split("%")[0])        # 去掉 IPv6 zone id
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    # 只靠 is_global 不够：Python 把组播 224.0.0.0/4 也算 global（测试里抓到的），所以显式排除
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_unspecified
                                 or ip.is_loopback or ip.is_link_local or ip.is_private)


def check_url(url: str, resolver=None) -> str:
    """校验通过返回规范化后的 URL，否则抛 ValueError（消息可直接给调用方看）。"""
    if os.environ.get("WEBTOOL_ALLOW_PRIVATE_URLS") == "1":
        return url
    try:
        parts = urlsplit(url.strip())
        port = parts.port                                     # 端口非法时这里会抛 ValueError
    except ValueError:
        raise ValueError("invalid URL")
    if parts.scheme not in ("http", "https"):
        raise ValueError("only http and https URLs are allowed")
    if parts.username or parts.password:
        raise ValueError("URLs with embedded credentials are not allowed")
    host = parts.hostname
    if not host:
        raise ValueError("URL has no host")
    port = port or (443 if parts.scheme == "https" else 80)
    if port not in _allowed_ports():
        raise ValueError(f"port {port} is not allowed")
    try:
        infos = (resolver or socket.getaddrinfo)(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError("host could not be resolved")
    addrs = {info[4][0] for info in infos}
    if not addrs:
        raise ValueError("host could not be resolved")
    for a in addrs:
        if not _is_public(a):
            # 不回显具体 IP，避免把内网拓扑泄露给调用方
            raise ValueError("URL points to a non-public address and is blocked")
    return url.strip()
