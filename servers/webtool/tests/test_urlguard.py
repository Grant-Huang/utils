"""SSRF 防护单测：不联网，DNS 用桩函数。"""
import socket

import pytest

from webtool.urlguard import check_url


def resolving_to(*ips):
    def r(host, port, proto=0):
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in ips]
    return r


PUBLIC = resolving_to("93.184.216.34")


def test_public_https_ok():
    assert check_url("https://example.com/a?b=1", resolver=PUBLIC) == "https://example.com/a?b=1"


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "10.0.0.5", "172.16.3.4", "192.168.1.1",        # 回环 / 内网
    "169.254.169.254",                                              # 云厂商元数据
    "100.64.0.1",                                                   # CGNAT
    "0.0.0.0", "224.0.0.1", "240.0.0.1",                            # 未指定 / 组播 / 保留
    "::1", "fe80::1", "fc00::1",                                    # IPv6 回环 / 链路本地 / ULA
    "::ffff:127.0.0.1", "::ffff:169.254.169.254",                   # IPv4-mapped 绕过
])
def test_non_public_addresses_blocked(ip):
    with pytest.raises(ValueError, match="non-public"):
        check_url("http://x.example/", resolver=resolving_to(ip))


def test_any_private_among_many_blocks():                          # DNS 返回多个地址，只要有一个内网就拒绝
    with pytest.raises(ValueError, match="non-public"):
        check_url("http://x.example/", resolver=resolving_to("93.184.216.34", "10.0.0.1"))


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.com/x", "gopher://example.com", "javascript:alert(1)", "data:text/html,hi",
])
def test_non_http_schemes_blocked(url):
    with pytest.raises(ValueError, match="only http"):
        check_url(url, resolver=PUBLIC)


def test_credentials_blocked():
    with pytest.raises(ValueError, match="credentials"):
        check_url("http://user:pw@example.com/", resolver=PUBLIC)


@pytest.mark.parametrize("url", ["http://example.com:22/", "http://example.com:6379/", "https://example.com:3306/"])
def test_odd_ports_blocked(url):
    with pytest.raises(ValueError, match="port"):
        check_url(url, resolver=PUBLIC)


def test_allowed_ports_configurable(monkeypatch):
    monkeypatch.setenv("WEBTOOL_ALLOWED_PORTS", "9000")
    assert check_url("http://example.com:9000/", resolver=PUBLIC)
    with pytest.raises(ValueError, match="port"):
        check_url("http://example.com/", resolver=PUBLIC)


@pytest.mark.parametrize("url", ["", "http://", "http:///x", "not a url", "http://example.com:99999/"])
def test_malformed_urls_rejected(url):
    with pytest.raises(ValueError):
        check_url(url, resolver=PUBLIC)


def test_unresolvable_host():
    def boom(*a, **k): raise socket.gaierror("nope")
    with pytest.raises(ValueError, match="resolved"):
        check_url("http://nonexistent.invalid/", resolver=boom)


def test_error_does_not_leak_ip():
    with pytest.raises(ValueError) as e:
        check_url("http://x.example/", resolver=resolving_to("10.1.2.3"))
    assert "10.1.2.3" not in str(e.value)


def test_escape_hatch_for_local_dev(monkeypatch):
    monkeypatch.setenv("WEBTOOL_ALLOW_PRIVATE_URLS", "1")
    assert check_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000/"
