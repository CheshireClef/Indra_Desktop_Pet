# src/llm/clients/text_sanitize.py
"""
从 LLM 原始输出中剥离推理/思考痕迹，并提取 JSON 载荷。
用于 DeepSeek、MiniMax 等会在 content 中夹杂 think 块 / 思维链的模型。
"""
from __future__ import annotations

import re

# DeepSeek / MiniMax 等常用的 markdown 风格思考围栏
_THINK_FENCE_OPEN = "```think"
_THINK_FENCE_CLOSE = "```"

# 常见 XML 风格思考标签
_THINK_BLOCK_RE = re.compile(
    r"<(?:think|thinking|redacted_thinking)\b[^>]*>.*?</(?:think|thinking|redacted_thinking)>",
    re.DOTALL | re.IGNORECASE,
)
_THINK_OPEN_RE = re.compile(
    r"<(?:think|thinking|redacted_thinking)\b[^>]*>",
    re.IGNORECASE,
)

# 角色扮演模型偶发：把「内心独白」写在全角/半角括号里并当作正文（非 API reasoning 字段）
_PAREN_MONOLOGUE_RE = re.compile(
    r"^[（(]([^）)]{20,})[）)]\s*",
)


def strip_paren_roleplay_monologue(text: str) -> str:
    """
    去掉开头连续的长括号独白块（≥20 字），保留后续实际对白。
    仅剥离开头，避免误伤句中短括号动作描写。
    """
    s = (text or "").strip()
    while True:
        m = _PAREN_MONOLOGUE_RE.match(s)
        if not m:
            break
        s = s[m.end() :].strip()
    return s


def strip_reasoning_artifacts(text: str) -> str:
    """
    移除模型思考过程，保留应对用户展示的正文。
    - 若存在 ```think ... ```，取最后一个闭合围栏之后的内容
    - 移除 <thinking> 等块；未闭合的思考标签则截断到标签前
    """
    if not (text or "").strip():
        return ""
    s = text.strip()
    lower = s.lower()
    if _THINK_FENCE_OPEN in lower:
        idx = lower.rfind(_THINK_FENCE_CLOSE)
        if idx >= 0:
            s = s[idx + len(_THINK_FENCE_CLOSE) :].strip()
    s = _THINK_BLOCK_RE.sub("", s).strip()
    m = _THINK_OPEN_RE.search(s)
    if m:
        s = s[: m.start()].strip()
    s = strip_paren_roleplay_monologue(s)
    return s


def extract_json_payload(text: str) -> str:
    """从可能夹杂思考文字的回复中提取 JSON 字符串（安全，无闭合时不退回全文）。"""
    from llm.parsers.json_extract import extract_json_object

    result = extract_json_object(text)
    return result.payload or ""
