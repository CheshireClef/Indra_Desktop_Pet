# src/llm/clients/llm_response.py
"""
统一 LLM 聊天响应结构（对齐 PicoClaw / Nanobot 的 LLMResponse 思路）。

解析层负责从各厂商原始 JSON 拆出「思考」与「正文」，UI 与业务只消费本结构。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMChatResult:
    """一次 chat/completions 的结构化结果。"""

    content: str
    """应对用户展示的正文（已剥离常见思考痕迹）。"""

    reasoning: str | None = None
    """API 级思考链（reasoning_content / thinking 块等），供 UI 单独展示。"""

    raw_content: str | None = None
    """message.content 原始拼接，便于调试。"""

    @property
    def has_reasoning(self) -> bool:
        return bool((self.reasoning or "").strip())

    def content_or_none(self) -> str | None:
        s = (self.content or "").strip()
        return s if s else None
