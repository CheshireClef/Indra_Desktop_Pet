# src/llm/clients/url_utils.py
"""
OpenAI 兼容 API 的 URL 规范化：兼容用户填写 base_url 或完整 chat/completions 地址。
"""
from __future__ import annotations


def normalize_base_url(url: str) -> str:
    """将各类输入规范为 API 根路径（以 /v1 结尾，不含 chat/completions）。"""
    u = (url or "").strip().rstrip("/")
    if not u:
        return ""
    for suffix in ("/v1/chat/completions", "/chat/completions"):
        if u.endswith(suffix):
            u = u[: -len(suffix)].rstrip("/")
            break
    if u.endswith("/v1"):
        return u
    if "/v1/" in u or u.endswith("/v1"):
        return u.split("/v1")[0] + "/v1" if "/v1" in u else u
    return f"{u}/v1"


def chat_completions_url(base_or_full: str) -> str:
    """得到 chat/completions 完整 POST URL。"""
    u = (base_or_full or "").strip().rstrip("/")
    if not u:
        return ""
    if u.endswith("/chat/completions"):
        return u
    base = normalize_base_url(u)
    if not base:
        return u
    return f"{base}/chat/completions"


def models_list_url(base_or_full: str) -> str:
    """得到 models 列表 GET URL。"""
    base = normalize_base_url(base_or_full)
    if not base:
        return ""
    return f"{base}/models"
