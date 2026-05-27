# src/llm/clients/response_utils.py
"""
OpenAI 兼容 API 响应解析工具。
统一处理 content 为 None、推理模型 reasoning 字段等边界情况。
"""
from __future__ import annotations

from typing import Any

from llm.clients.text_sanitize import strip_reasoning_artifacts


def _content_field_to_text(content: Any) -> str:
    """OpenAI 兼容：content 可能是字符串或多模态 part 数组。"""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                t = item.get("text")
                if isinstance(t, str) and t.strip():
                    parts.append(t.strip())
        return "\n".join(parts).strip()
    return ""


def extract_message_content(data: dict[str, Any] | None) -> str:
    """
    从 chat/completions 响应 JSON 中提取助手正文（用户可见部分）。
    仅使用 message.content；推理字段 reasoning_content 等不作为对话正文（避免思考链进气泡）。
    若 content 含 think 围栏或思考标签，会剥离后再返回。
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

    raw_text = _content_field_to_text(message.get("content"))
    if raw_text:
        cleaned = strip_reasoning_artifacts(raw_text)
        if cleaned:
            return cleaned
        # content 全是思考痕迹时视为无正文，勿回退到 reasoning 字段
        return ""

    return ""


def extract_vision_message_content(data: dict[str, Any] | None) -> str:
    """
    识图专用：先走 extract_message_content；仍为空时尝试 reasoning 字段
    （部分 VLM 在 thinking 开启时会这样返回）。聊天路径请勿使用，避免思考链进气泡。
    """
    text = extract_message_content(data)
    if text:
        return text
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
    for key in ("reasoning_content", "reasoning"):
        alt = message.get(key)
        if isinstance(alt, str) and alt.strip():
            cleaned = strip_reasoning_artifacts(alt)
            if cleaned:
                return cleaned
    return ""
