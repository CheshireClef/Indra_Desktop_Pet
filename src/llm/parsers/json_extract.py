# src/llm/parsers/json_extract.py
"""
从 LLM 原始文本中安全提取 JSON 对象（括号平衡、禁止无闭合时退回全文）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from llm.clients.text_sanitize import strip_reasoning_artifacts

BracePreference = Literal["first", "last"]

_FENCE_OPEN_RE = re.compile(r"```(?:json)?\s*", re.IGNORECASE)


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


def _try_fenced_balanced(s: str) -> tuple[str | None, bool, bool]:
    """
    从 Markdown 围栏中提取完整 JSON 对象（从围栏内第一个 `{` 平衡扫描）。
    返回 (payload, had_prose_before_json, incomplete_fence)。
    """
    m = _FENCE_OPEN_RE.search(s)
    if not m:
        return None, False, False

    had_prose = m.start() > 0
    inner = s[m.end() :]
    close = inner.find("```")
    if close < 0:
        return None, had_prose, True

    body = inner[:close].strip()
    first_brace = body.find("{")
    if first_brace < 0:
        return None, had_prose, False

    balanced = _balanced_object_from(body, first_brace)
    if balanced:
        return balanced, had_prose, False
    return None, had_prose, False


def _extract_by_brace(s: str, preference: BracePreference) -> tuple[str | None, bool]:
    """按 first/last 策略从文本中提取平衡 JSON 对象。"""
    if preference == "first":
        indices = [i for i in (s.find("{"), s.rfind("{")) if i >= 0]
        # first 优先；若 first 失败再试 last（兼容 think 块后仅有尾部 JSON 的少数情况）
        order = sorted(set(indices))
    else:
        indices = [i for i in (s.rfind("{"), s.find("{")) if i >= 0]
        order = []
        seen: set[int] = set()
        for i in indices:
            if i not in seen:
                order.append(i)
                seen.add(i)

    for idx in order:
        balanced = _balanced_object_from(s, idx)
        if balanced:
            return balanced, idx > 0
    return None, bool(s)


def extract_json_object(
    raw: str,
    *,
    brace_preference: BracePreference = "last",
) -> ExtractJsonResult:
    """
    安全提取单个 JSON 对象字符串。
    禁止在无法得到平衡 `{}` 时返回整段原文。

    brace_preference:
    - last：聊天场景，JSON 常在末尾（默认）
    - first：嵌套 schema（如 memories 数组内含对象），须取根对象
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

    payload, had_prose, incomplete = _try_fenced_balanced(s)
    if incomplete:
        return ExtractJsonResult(
            payload=None,
            incomplete_fence=True,
            had_prose_before_json=had_prose,
        )
    if payload:
        return ExtractJsonResult(payload=payload, had_prose_before_json=had_prose)

    balanced, had_prose = _extract_by_brace(s, brace_preference)
    if balanced:
        return ExtractJsonResult(payload=balanced, had_prose_before_json=had_prose)

    return ExtractJsonResult(payload=None, had_prose_before_json=bool(s))
