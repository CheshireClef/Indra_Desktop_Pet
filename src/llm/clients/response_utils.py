# src/llm/clients/response_utils.py
"""
OpenAI 兼容 API 响应解析工具。
统一处理 content 为 None、推理模型 reasoning 字段等边界情况。
"""
from __future__ import annotations

from typing import Any

from llm.clients.llm_response import LLMChatResult
from llm.clients.text_sanitize import strip_reasoning_artifacts

# content 数组里表示「思考」的 part 类型（Anthropic extended thinking 等）
_THINKING_PART_TYPES = frozenset(
    {"thinking", "reasoning", "redacted_thinking", "thought"}
)


def _content_field_to_text(content: Any) -> str:
    """OpenAI 兼容：content 可能是字符串或多模态 part 数组（仅 text 部分）。"""
    text, _ = _split_content_field(content)
    return text


def _split_content_field(content: Any) -> tuple[str, str]:
    """
    从 message.content 拆出 (正文文本, 思考文本)。
    支持字符串或 part 数组（含 Anthropic thinking 块）。
    """
    if isinstance(content, str):
        return content.strip(), ""
    if isinstance(content, list):
        text_parts: list[str] = []
        think_parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            part_type = (item.get("type") or "").lower()
            if part_type in _THINKING_PART_TYPES:
                chunk = item.get("thinking") or item.get("text") or item.get("content")
                if isinstance(chunk, str) and chunk.strip():
                    think_parts.append(chunk.strip())
                continue
            if part_type == "text":
                t = item.get("text")
                if isinstance(t, str) and t.strip():
                    text_parts.append(t.strip())
        return "\n".join(text_parts).strip(), "\n".join(think_parts).strip()
    return "", ""


def _first_message(data: dict[str, Any]) -> dict[str, Any] | None:
    choices = data.get("choices")
    if not choices or not isinstance(choices, list):
        return None
    first = choices[0] if choices else {}
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    return message if isinstance(message, dict) else None


def _reasoning_from_message_fields(message: dict[str, Any]) -> str:
    """OpenAI 兼容 reasoning_content / reasoning 等顶层字段。"""
    chunks: list[str] = []
    for key in ("reasoning_content", "reasoning", "thinking"):
        val = message.get(key)
        if isinstance(val, str) and val.strip():
            chunks.append(val.strip())
    return "\n\n".join(chunks).strip()


def parse_chat_completion(data: dict[str, Any] | None) -> LLMChatResult:
    """
    统一解析 chat/completions 响应：正文与思考分离。

    - 正文：content 中的 text / 字符串，并 strip_reasoning_artifacts
    - 思考：reasoning_content、thinking 块、content 中的 thinking part
    - 不把思考回灌进正文（避免 PicoClaw 所修的「思考进气泡」问题）
    """
    if not data or not isinstance(data, dict):
        return LLMChatResult(content="")
    message = _first_message(data)
    if not message:
        return LLMChatResult(content="")

    raw_text, think_in_content = _split_content_field(message.get("content"))
    reasoning_raw = _reasoning_from_message_fields(message)
    if think_in_content:
        reasoning_raw = "\n\n".join(
            p for p in (reasoning_raw, think_in_content) if p
        ).strip()

    content_clean = strip_reasoning_artifacts(raw_text) if raw_text else ""
    reasoning_clean = (reasoning_raw or "").strip() or None

    return LLMChatResult(
        content=content_clean,
        reasoning=reasoning_clean,
        raw_content=raw_text or None,
    )


def extract_message_content(data: dict[str, Any] | None) -> str:
    """
    从 chat/completions 响应 JSON 中提取助手正文（用户可见部分）。
    仅使用 message.content；推理字段 reasoning_content 等不作为对话正文（避免思考链进气泡）。
    若 content 含 think 围栏或思考标签，会剥离后再返回。
    """
    return parse_chat_completion(data).content


def extract_vision_message_content(data: dict[str, Any] | None) -> str:
    """
    识图专用：先走 extract_message_content；仍为空时尝试 reasoning 字段
    （部分 VLM 在 thinking 开启时会这样返回）。聊天路径请勿使用，避免思考链进气泡。
    """
    parsed = parse_chat_completion(data)
    if parsed.content:
        return parsed.content
    # 识图：正文为空时用 reasoning 兜底（VLM 思考占满 token 时）
    if parsed.reasoning:
        cleaned = strip_reasoning_artifacts(parsed.reasoning)
        if cleaned:
            return cleaned
    return ""
