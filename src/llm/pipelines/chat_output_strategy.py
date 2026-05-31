# src/llm/pipelines/chat_output_strategy.py
"""
主聊天输出策略：按厂商/模型选择 JSON 或自然语言+情绪标签。

DeepSeek 官方 JSON Output 存在「有概率返回空 content」的已知问题，聊天路径对其跳过
response_format / prompt JSON，见 https://api-docs.deepseek.com/zh-cn/guides/json_mode
"""
from __future__ import annotations

import re

from llm.clients.vision_adapter import match_vendor_id

_DEEPSEEK_MODEL_RE = re.compile(r"deepseek", re.I)


def is_deepseek_chat_model(
    base_url: str,
    model: str,
    *,
    vendor: str | None = None,
) -> bool:
    """是否应按自然语言+【情绪】标签与 DeepSeek 对话（不用 JSON Output）。"""
    if (vendor or "").lower() == "deepseek":
        return True
    if _DEEPSEEK_MODEL_RE.search(model or ""):
        return True
    if match_vendor_id(base_url) == "deepseek":
        return True
    return False


def effective_chat_output_mode(
    user_mode: str,
    base_url: str,
    model: str,
    *,
    vendor: str | None = None,
    cached_json_mode: str | None = None,
) -> tuple[str, str | None]:
    """
    返回 (实际 output_mode, 建议 capabilities_cache.json_mode)。

    DeepSeek：强制 natural_only，避免官方 JSON 空 content。
    """
    if is_deepseek_chat_model(base_url, model, vendor=vendor):
        if (user_mode or "auto").lower() != "natural_only":
            print(
                "[OutputMode] DeepSeek 聊天跳过 JSON Output（官方已知可能返回空 content），"
                "使用自然语言 + 【情绪】标签"
            )
        return "natural_only", "natural_only"
    return (user_mode or "auto").lower(), cached_json_mode
