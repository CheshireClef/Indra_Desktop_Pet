# src/llm/output_modes.py
"""
聊天 JSON 输出策略链：response_format → prompt JSON → 自然语言情绪标签。
"""
from __future__ import annotations

from typing import Any, Callable


def chat_with_output_policy(
    *,
    messages: list[dict],
    output_mode: str,
    cached_json_mode: str | None,
    llm_caller: Callable[..., str | None],
    llm_caller_json_rf: Callable[..., str | None],
    use_json_system: bool,
    use_natural_system: bool,
    rebuild_messages_json,
    rebuild_messages_natural,
) -> tuple[str | None, str]:
    """
    按策略链调用 LLM。
    返回 (raw_text, strategy_used)。
    strategy_used: response_format | prompt_only | natural | json_preferred_failed
    """
    mode = (output_mode or "auto").lower()
    jmode = (cached_json_mode or "").lower()

    def try_rf(msgs):
        return llm_caller_json_rf(msgs)

    def try_plain(msgs):
        return llm_caller(msgs)

    if mode == "natural_only":
        msgs = rebuild_messages_natural(messages) if use_natural_system else messages
        text = try_plain(msgs)
        return text, "natural"

    if mode == "json_preferred":
        msgs = rebuild_messages_json(messages) if use_json_system else messages
        text = try_rf(msgs)
        if text:
            print("[OutputMode] json_preferred: response_format")
            return text, "response_format"
        text = try_plain(msgs)
        if text:
            print("[OutputMode] json_preferred: 降级 prompt_only")
            return text, "prompt_only"
        return None, "json_preferred_failed"

    # auto
    if jmode == "natural_only":
        msgs = rebuild_messages_natural(messages) if use_natural_system else messages
        text = try_plain(msgs)
        return text, "natural"

    msgs_json = rebuild_messages_json(messages) if use_json_system else messages
    if jmode == "response_format":
        text = try_rf(msgs_json)
        if text:
            print("[OutputMode] auto: response_format (cached)")
            return text, "response_format"

    if jmode in ("", "prompt_only", "response_format"):
        text = try_rf(msgs_json)
        if text:
            print("[OutputMode] auto: response_format")
            return text, "response_format"
        text = try_plain(msgs_json)
        if text:
            print("[OutputMode] auto: 降级 prompt_only")
            return text, "prompt_only"

    msgs_nat = rebuild_messages_natural(messages) if use_natural_system else messages
    text = try_plain(msgs_nat)
    if text:
        print("[OutputMode] auto: 降级 natural")
        return text, "natural"
    return None, "failed"


def json_only_policy(
    messages: list[dict],
    llm_caller_json_rf: Callable[..., str | None],
    llm_caller_plain: Callable[..., str | None],
) -> str | None:
    """长期记忆等场景：仅 A→B，失败返回 None。"""
    text = llm_caller_json_rf(messages)
    if text:
        return text
    return llm_caller_plain(messages)
