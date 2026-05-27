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
    return s


def extract_json_payload(text: str) -> str:
    """从可能夹杂思考文字的回复中提取 JSON 字符串。"""
    s = strip_reasoning_artifacts(text)
    if not s:
        return ""
    block = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", s, re.IGNORECASE)
    if block:
        return block.group(1).strip()
    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        return s[start : end + 1].strip()
    return s
