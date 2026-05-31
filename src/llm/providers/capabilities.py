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
    from llm.pipelines.chat_output_strategy import is_deepseek_chat_model

    if is_deepseek_chat_model(client.base_url, client.model):
        print(
            "[CapabilityProbe] DeepSeek 跳过 JSON 探测（聊天使用自然语言；"
            "记忆模型仍可用 JSON）"
        )
        return "natural_only"

    from llm.clients.reasoning_extras import reasoning_payload_extras

    extras = reasoning_payload_extras(
        client.base_url, client.model, profile="structured"
    )
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
            extra_payload=extras,
            log_prefix="JSON探测",
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
            extra_payload=extras,
            log_prefix="JSON探测",
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


def run_json_only_probe(
    base_url: str,
    api_key: str,
    model: str,
) -> dict[str, Any]:
    """仅探测 JSON 输出能力（不跑识图，避免终端误报「识图探测成功」）。"""
    base = normalize_base_url(base_url)
    client = OpenAICompatibleClient(base, api_key, model)
    json_mode = probe_json_mode(client)
    return {
        "json_mode": json_mode,
        "probed_at": datetime.now(timezone.utc).isoformat(),
    }


def probe_memory_extract_dry_run(
    base_url: str,
    api_key: str,
    model: str,
) -> tuple[bool, str]:
    """
    用与正式抽取相同的请求形态做试运行（短对话样本）。
    返回 (是否通过, 说明)。
    """
    from llm.clients.reasoning_extras import reasoning_payload_extras
    from llm.memory_extract import load_extract_system_prompt, parse_extract_response

    base = normalize_base_url(base_url)
    client = OpenAICompatibleClient(base, api_key, model)
    if not client.chat_url:
        return False, "Base URL 无效"

    system = load_extract_system_prompt()
    user_sample = (
        "以下是刚完成的对话片段，请判断是否有值得写入长期记忆的内容。\n"
        "用户：请记住我平时更喜欢喝低度甜酒酿，不太能喝烈酒。\n"
        "助手：好的，我会记住你的偏好。\n"
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_sample},
    ]
    extras = reasoning_payload_extras(base, model, profile="structured")
    raw = None
    last_err = ""
    for attempt, use_rf in enumerate((True, False), start=1):
        try:
            raw = client.chat_completions(
                messages,
                temperature=0.2,
                max_tokens=256,
                response_format_json=use_rf,
                extra_payload=extras,
                log_prefix="记忆探测",
            )
            if raw and raw.strip():
                break
            last_err = f"第 {attempt} 次请求返回空正文"
        except Exception as e:
            last_err = str(e)
            raw = None

    if not (raw or "").strip():
        return False, last_err or "模型无响应"

    items = parse_extract_response(raw)
    if items:
        return True, f"抽取试运行通过（解析到 {len(items)} 条样本记忆）"
    # 空 memories 也算 API 通
    if "memories" in (raw or "").lower() or raw.strip().startswith("{"):
        return True, "抽取试运行通过（模型返回 JSON，当前样本判定为无需录入）"
    return False, f"响应无法解析为记忆 JSON，预览：{(raw or '')[:120]}…"


def run_memory_capability_probe(
    base_url: str,
    api_key: str,
    model: str,
) -> dict[str, Any]:
    """记忆模型专用探测：JSON 模式 + 抽取试运行（不探测识图）。"""
    result = run_json_only_probe(base_url, api_key, model)
    ok, note = probe_memory_extract_dry_run(base_url, api_key, model)
    result["memory_extract_ok"] = ok
    result["memory_extract_note"] = note
    return result


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
