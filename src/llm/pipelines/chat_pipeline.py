# src/llm/pipelines/chat_pipeline.py
"""
主聊天 LLM 管道：消息构建辅助、输出解析、格式重试提示。
ChatManager 仍负责 history / RAG / 记忆调度；本模块集中「调用 + 解析」契约。
"""
from __future__ import annotations

from typing import Any, Callable

from llm.parsers.chat_response import (
    ChatParseResult,
    json_retry_system_suffix,
    parse_chat_output,
)
from llm.output_modes import chat_with_output_policy
from llm.pipelines.chat_output_strategy import effective_chat_output_mode


def get_json_output_instruction(
    valid_emotion_tags: list[str],
    *,
    use_markdown_fence: bool,
) -> str:
    """聊天 JSON schema：仅 reply + emotion。"""
    tags = "、".join(valid_emotion_tags)
    base = (
        "\n\n【输出格式】你必须只输出一个 JSON 对象，不要输出 JSON 以外的任何文字。"
        "禁止输出思考过程、chain-of-thought 或 think 围栏。"
        "\n字段说明："
        "\n- reply（必填）：你作为角色对用户说的正文。"
        f"\n- emotion（必填）：从以下列表选一个：{tags}。"
        "仅当完全无情绪时选「平常」；涉及饮酒情节优先选「干杯」。"
    )
    if use_markdown_fence:
        return (
            base
            + "输出时用 Markdown 代码块包裹，例如：\n```json\n"
            '{"reply":"……","emotion":"开心"}\n```'
        )
    return base + '\n示例：{"reply":"……","emotion":"开心"}'


def invoke_chat_with_policy(
    *,
    messages: list[dict],
    output_mode: str,
    cached_json_mode: str | None,
    llm_caller: Callable[..., str | None],
    llm_caller_json_rf: Callable[..., str | None],
    rebuild_messages_json: Callable[[list[dict]], list[dict]],
    rebuild_messages_natural: Callable[[list[dict]], list[dict]],
    base_url: str = "",
    model: str = "",
    vendor: str | None = None,
) -> tuple[str | None, str]:
    """调用 output_modes 策略链，返回 (raw_text, strategy_used)。"""
    mode, jmode = effective_chat_output_mode(
        output_mode,
        base_url,
        model,
        vendor=vendor,
        cached_json_mode=cached_json_mode,
    )
    return chat_with_output_policy(
        messages=messages,
        output_mode=mode,
        cached_json_mode=jmode,
        llm_caller=llm_caller,
        llm_caller_json_rf=llm_caller_json_rf,
        use_json_system=True,
        use_natural_system=True,
        rebuild_messages_json=rebuild_messages_json,
        rebuild_messages_natural=rebuild_messages_natural,
    )


def parse_chat_raw(
    raw: str,
    *,
    strategy: str,
    max_reply_chars: int,
) -> ChatParseResult:
    allow_fallback = (strategy or "").lower() == "natural"
    return parse_chat_output(
        raw,
        allow_tag_fallback=allow_fallback,
        max_reply_chars=max_reply_chars,
    )


def append_json_retry_to_messages(messages: list[dict]) -> list[dict]:
    """复制 messages 并在 system 末尾追加格式纠正说明。"""
    out: list[dict] = []
    hint = json_retry_system_suffix()
    for msg in messages:
        if msg.get("role") == "system" and isinstance(msg.get("content"), str):
            m = dict(msg)
            m["content"] = msg["content"] + hint
            out.append(m)
        else:
            out.append(dict(msg))
    if not any(m.get("role") == "system" for m in out):
        out.insert(0, {"role": "system", "content": hint.strip()})
    return out


def should_use_markdown_json_instruction(cached_json_mode: str | None) -> bool:
    """response_format 模式下不要求 Markdown 代码块包裹。"""
    return (cached_json_mode or "").lower() != "response_format"
