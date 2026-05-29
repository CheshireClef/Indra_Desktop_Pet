# src/llm/parsers/json_extract.py
"""
从 LLM 原始文本中安全提取 JSON 对象（括号平衡、禁止无闭合时退回全文）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from llm.clients.text_sanitize import strip_reasoning_artifacts

_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*(\{[\s\S]*?\})\s*```",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExtractJsonResult:
    payload: str | None
    """可 json.loads 的字符串；失败为 None。"""
    incomplete_fence: bool = False
    """存在未闭合的 ```json 块。"""
    had_prose_before_json: bool = False
    """JSON 前有非 JSON 正文（应丢弃，勿当 reply）。"""


def _balanced_object_from(text: str, start: int) -> str | None:
    """从 start 处的 `{` 做括号平衡，返回完整 object 子串。"""
    if start < 0 or start >= len(text) or text[start] != "{":
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_json_object(raw: str) -> ExtractJsonResult:
    """
    安全提取单个 JSON 对象字符串。
    禁止在无法得到平衡 `{}` 时返回整段原文。
    """
    s = strip_reasoning_artifacts((raw or "").strip())
    if not s:
        return ExtractJsonResult(payload=None)

    # 未闭合的 ```json 围栏
    lower = s.lower()
    if "```json" in lower or (lower.count("```") == 1 and "```" in lower):
        fence_start = lower.find("```json")
        if fence_start < 0:
            fence_start = lower.find("```")
        tail = s[fence_start + 3 :] if fence_start >= 0 else ""
        if "```" not in tail:
            return ExtractJsonResult(
                payload=None,
                incomplete_fence=True,
                had_prose_before_json=fence_start > 0,
            )

    # 完整 fenced 块
    block = _JSON_FENCE_RE.search(s)
    if block:
        candidate = block.group(1).strip()
        had_prose = block.start() > 0
        if _balanced_object_from(candidate, 0) == candidate:
            return ExtractJsonResult(
                payload=candidate,
                had_prose_before_json=had_prose,
            )

    # 从最后一个 `{` 起平衡扫描（优先靠近末尾的 JSON）
    last_brace = s.rfind("{")
    if last_brace >= 0:
        balanced = _balanced_object_from(s, last_brace)
        if balanced:
            return ExtractJsonResult(
                payload=balanced,
                had_prose_before_json=last_brace > 0,
            )

    return ExtractJsonResult(payload=None, had_prose_before_json=bool(s))
