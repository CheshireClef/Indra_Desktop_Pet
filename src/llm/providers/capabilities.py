# src/llm/providers/capabilities.py
"""
模型能力探测：JSON 输出模式、多模态识图。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from llm.clients.openai_compatible import OpenAICompatibleClient
from llm.clients.url_utils import normalize_base_url
from llm.clients.vision_adapter import adaptive_probe_vision


def probe_json_mode(client: OpenAICompatibleClient) -> str:
    """
    探测 JSON 能力，返回 json_mode:
    response_format | prompt_only | natural_only
    """
    probe_msgs_rf = [
        {"role": "system", "content": "只输出 JSON：{\"ok\":true}"},
        {"role": "user", "content": "ping"},
    ]
    try:
        text = client.chat_completions(
            probe_msgs_rf,
            temperature=0,
            max_tokens=32,
            response_format_json=True,
        )
        if text and "ok" in text.lower():
            return "response_format"
    except Exception:
        pass

    probe_msgs_prompt = [
        {"role": "system", "content": '只输出一个 JSON 对象 {"ok":true}，不要其他文字。'},
        {"role": "user", "content": "ping"},
    ]
    try:
        text = client.chat_completions(
            probe_msgs_prompt,
            temperature=0,
            max_tokens=32,
            response_format_json=False,
        )
        if text and "ok" in text.lower():
            return "prompt_only"
    except Exception:
        pass

    return "natural_only"


def probe_vision(
    client: OpenAICompatibleClient,
    *,
    vendor_id: str | None = None,
    cached_hints: dict[str, Any] | None = None,
) -> tuple[bool, dict[str, Any]]:
    """自适应识图探测，返回 (是否支持, 元数据含 vision_hints / probe_note)。"""
    ok, meta = adaptive_probe_vision(
        client,
        vendor_id=vendor_id,
        cached_hints=cached_hints,
    )
    return ok, meta


def run_full_probe(
    base_url: str,
    api_key: str,
    model: str,
) -> dict[str, Any]:
    """对指定连接与模型执行完整探测。"""
    base = normalize_base_url(base_url)
    client = OpenAICompatibleClient(base, api_key, model)
    json_mode = probe_json_mode(client)
    supports_vision, vision_meta = probe_vision(client)
    result: dict[str, Any] = {
        "json_mode": json_mode,
        "supports_vision": supports_vision,
        "probed_at": datetime.now(timezone.utc).isoformat(),
    }
    result.update(vision_meta)
    return result
