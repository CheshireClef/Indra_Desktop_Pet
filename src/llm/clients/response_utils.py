# src/llm/clients/response_utils.py
"""
OpenAI 兼容 API 响应解析工具。
统一处理 content 为 None、推理模型 reasoning 字段等边界情况。
"""
from __future__ import annotations

from typing import Any


def extract_message_content(data: dict[str, Any] | None) -> str:
    """
    从 chat/completions 响应 JSON 中提取助手正文。
    若 content 为空，尝试 reasoning_content 等扩展字段（如部分 MiniMax 推理模型）。
    """
    if not data or not isinstance(data, dict):
        return ""
    choices = data.get("choices")
    if not choices or not isinstance(choices, list):
        return ""
    first = choices[0] if choices else {}
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""

    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()

    # 部分厂商将正文放在 reasoning 相关字段
    for key in ("reasoning_content", "reasoning"):
        alt = message.get(key)
        if isinstance(alt, str) and alt.strip():
            return alt.strip()

    details = message.get("reasoning_details")
    if isinstance(details, list):
        parts: list[str] = []
        for item in details:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        if parts:
            return "\n".join(parts)

    return ""
