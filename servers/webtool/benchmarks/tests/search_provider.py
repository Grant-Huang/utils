"""兼容 shim：benchmark 测试仍用 `from search_provider import ...`，实际实现已移入 webtool 包。"""
from webtool.search_provider import *  # noqa: F401,F403
