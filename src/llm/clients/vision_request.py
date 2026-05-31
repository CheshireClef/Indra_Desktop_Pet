# src/llm/clients/vision_request.py
"""
多模态识图请求体构造（OpenAI 兼容）。
参数由 vision_adapter 按服务商/缓存 hints 合并，避免逐模型硬编码。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from llm.clients.vision_adapter import (
    VisionHints,
    build_vision_user_message_with_hints,
    merge_vision_hints,
    vision_payload_extras,
)


def guess_image_mime(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/png")


def build_vision_user_message(
    text: str,
    image_b64: str,
    *,
    mime: str = "image/png",
    detail: str = "low",
    content_order: str = "image_first",
) -> dict[str, Any]:
    """构造含 image_url + text 的 user message（无 hints 时的简便接口）。"""
    hints = VisionHints(detail=detail, content_order=content_order)
    return build_vision_user_message_with_hints(text, image_b64, hints, mime=mime)


def build_vision_chat_payload(
    model: str,
    user_message: dict[str, Any],
    *,
    base_url: str = "",
    max_tokens: int = 512,
    temperature: float = 0.2,
    vision_hints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hints = merge_vision_hints(base_url, model, cached=vision_hints)
    payload: dict[str, Any] = {
        "model": model,
        "messages": [user_message],
        "stream": False,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    payload.update(vision_payload_extras(base_url, model, hints))
    return payload
