# src/llm/providers/capabilities.py
"""
模型能力探测：JSON 输出模式、多模态识图。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from llm.clients.openai_compatible import OpenAICompatibleClient
from llm.clients.url_utils import normalize_base_url

# 1x1 透明 PNG
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


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


def probe_vision(client: OpenAICompatibleClient) -> bool:
    """发送极小 PNG 多模态请求，判断是否支持识图。"""
    if not client.chat_url or not client.model:
        return False
    payload = {
        "model": client.model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "描述这张图，一个字即可。"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{_TINY_PNG_B64}"},
                    },
                ],
            }
        ],
        "max_tokens": 16,
        "temperature": 0,
        "stream": False,
    }
    try:
        import requests

        resp = requests.post(
            client.chat_url,
            headers=client._headers(),
            json=payload,
            timeout=60,
        )
        if resp.status_code >= 400:
            return False
        from llm.clients.response_utils import extract_message_content

        text = extract_message_content(resp.json())
        return bool(text and text.strip())
    except Exception as e:
        print(f"[Capabilities] 识图探测失败: {e}")
        return False


def run_full_probe(
    base_url: str,
    api_key: str,
    model: str,
) -> dict[str, Any]:
    """对指定连接与模型执行完整探测。"""
    base = normalize_base_url(base_url)
    client = OpenAICompatibleClient(base, api_key, model)
    json_mode = probe_json_mode(client)
    supports_vision = probe_vision(client)
    return {
        "json_mode": json_mode,
        "supports_vision": supports_vision,
        "probed_at": datetime.now(timezone.utc).isoformat(),
    }
