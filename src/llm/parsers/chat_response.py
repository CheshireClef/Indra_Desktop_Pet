# src/llm/parsers/chat_response.py
"""
主聊天通道：解析 {reply, emotion} JSON；失败时不将全文当作 reply。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from llm.clients.text_sanitize import strip_reasoning_artifacts
from llm.parsers.json_extract import extract_json_object

# 与 ChatManager.VALID_EMOTION_TAGS 保持一致
VALID_EMOTION_TAGS = frozenset(
    ["喜爱", "开心", "干杯", "疑问", "伤心", "无聊", "尴尬", "生气", "平常"]
)

_JSON_RETRY_HINT = (
    "\n\n【系统】上一轮输出格式无效。你必须只输出一个 JSON 对象，"
    '字段仅包含 reply 与 emotion，禁止任何其它文字、Markdown 代码块或思考过程。'
    '示例：{"reply":"……","emotion":"开心"}'
)


@dataclass(frozen=True)
class ChatParseResult:
    reply: str
    emotion: str
    ok: bool
    parse_mode: str
    """json_ok | json_incomplete | invalid_json | empty_reply | fallback_tag | empty_input"""
    error: str | None = None


def clamp_reply_length(reply: str, max_chars: int) -> str:
    if max_chars <= 0 or len(reply) <= max_chars:
        return reply
    print(f"[ChatParse] reply 超长已截断：{len(reply)} -> {max_chars}")
    return reply[:max_chars].rstrip() + "…"


def parse_chat_output(
    content: str,
    *,
    allow_tag_fallback: bool = False,
    max_reply_chars: int = 800,
) -> ChatParseResult:
    """
    解析聊天 LLM 原始输出。
    allow_tag_fallback：仅 natural_only 等模式允许回退到【情绪】标签剥离。
    """
    if not (content or "").strip():
        return ChatParseResult(
            reply="",
            emotion="平常",
            ok=False,
            parse_mode="empty_input",
            error="empty_input",
        )

    extracted = extract_json_object(content)
    if extracted.incomplete_fence:
        print(
            "[ChatParse] parse_mode=json_incomplete | "
            f"had_prose={extracted.had_prose_before_json}"
        )
        return ChatParseResult(
            reply="",
            emotion="平常",
            ok=False,
            parse_mode="json_incomplete",
            error="incomplete_json",
        )

    if extracted.payload:
        try:
            obj = json.loads(extracted.payload)
            if not isinstance(obj, dict):
                raise ValueError("not a dict")
            reply = (obj.get("reply") or "").strip() if obj.get("reply") is not None else ""
            reply = strip_reasoning_artifacts(reply)
            emotion = (obj.get("emotion") or "").strip() or "平常"
            if emotion not in VALID_EMOTION_TAGS:
                emotion = "平常"
            reply = clamp_reply_length(reply, max_reply_chars)
            if not reply:
                print("[ChatParse] parse_mode=empty_reply | json_ok but reply empty")
                return ChatParseResult(
                    reply="",
                    emotion=emotion,
                    ok=False,
                    parse_mode="empty_reply",
                    error="empty_reply",
                )
            print(
                f"[ChatParse] parse_mode=json_ok | emotion={emotion} | reply_len={len(reply)}"
            )
            return ChatParseResult(
                reply=reply,
                emotion=emotion,
                ok=True,
                parse_mode="json_ok",
            )
        except Exception as e:
            print(f"[ChatParse] parse_mode=invalid_json | {e}")
            if not allow_tag_fallback:
                return ChatParseResult(
                    reply="",
                    emotion="平常",
                    ok=False,
                    parse_mode="invalid_json",
                    error="invalid_json",
                )

    if not allow_tag_fallback:
        print("[ChatParse] parse_mode=invalid_json | no fallback")
        return ChatParseResult(
            reply="",
            emotion="平常",
            ok=False,
            parse_mode="invalid_json",
            error="no_json",
        )

    # natural_only：情绪标签回退（短文本场景）
    raw = strip_reasoning_artifacts(content)
    marker = "【刚刚对屏幕的评论】"
    if marker in raw:
        raw = raw[: raw.find(marker)].strip()
    clean_reply, emotion_tag = _extract_emotion_tag_fallback(raw)
    clean_reply = clamp_reply_length(clean_reply, max_reply_chars)
    print(
        f"[ChatParse] parse_mode=fallback_tag | emotion={emotion_tag} | "
        f"reply_len={len(clean_reply)}"
    )
    return ChatParseResult(
        reply=clean_reply,
        emotion=emotion_tag,
        ok=bool(clean_reply),
        parse_mode="fallback_tag",
    )


def _extract_emotion_tag_fallback(reply: str) -> tuple[str, str]:
    if not reply.strip():
        return "", "平常"
    valid_tags_pattern = "|".join(re.escape(tag) for tag in VALID_EMOTION_TAGS)
    pattern = re.compile(r"\s*【(" + valid_tags_pattern + r")】\s*")
    matches = pattern.findall(reply)
    emotion_tag = matches[-1].strip() if matches else "平常"
    pure_reply = pattern.sub("", reply)
    pure_reply = re.sub(r"\s+", " ", pure_reply).strip()
    if not pure_reply:
        return "", "平常"
    return pure_reply, emotion_tag


def json_retry_system_suffix() -> str:
    return _JSON_RETRY_HINT
