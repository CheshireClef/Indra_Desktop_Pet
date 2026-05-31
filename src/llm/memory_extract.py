# src/llm/memory_extract.py
"""
聊天长期记忆后台抽取：独立 prompt、结构化 JSON、记忆专用模型 API。
"""
from __future__ import annotations

import json
from typing import Any

from llm.clients.text_sanitize import extract_json_payload
from llm.memory_extract_sampling import SCREEN_COMMENT_PREFIX
from llm.output_modes import json_only_policy
from utils import resource_path

_SCREEN_COMMENT_PREFIX = SCREEN_COMMENT_PREFIX


def load_extract_system_prompt() -> str:
    path = resource_path("config/prompts/memory_extract.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        print(f"[MemoryExtract] 无法加载 prompt 文件: {e}")
        return (
            "你只输出 JSON：{\"memories\":[{\"content\":\"…\",\"topic\":\"…\"}]}，"
            "无内容时 memories 为 []。用 Markdown 代码块包裹。"
        )


def build_extract_user_payload(history_slice: list[dict[str, Any]]) -> str:
    """将最近 N 轮对话格式化为抽取用 user 载荷。"""
    from llm.memory_extract_sampling import is_screen_comment_message

    lines: list[str] = [
        "以下为用户与助手的日常对话，忽略角色扮演中的虚构情节，"
        "只提取关于用户本人的事实。\n",
        "以下是刚完成的对话片段，请判断是否有值得写入长期记忆的内容。\n",
    ]
    for msg in history_slice:
        if not isinstance(msg, dict):
            continue
        if is_screen_comment_message(msg):
            continue
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        text = (str(msg.get("content") or "")).strip()
        if not text:
            continue
        label = "用户" if role == "user" else "助手"
        lines.append(f"{label}：{text}\n")
    return "".join(lines).strip()


def parse_extract_response(raw: str | None) -> list[tuple[str, str | None]]:
    """
    解析抽取 JSON，返回 [(content, topic), ...]。
    解析失败返回空列表（fail-safe，不写库）。
    """
    if not (raw or "").strip():
        return []
    payload = extract_json_payload(raw.strip(), brace_preference="first")
    if not payload:
        print("[MemoryExtract] 解析失败：无 JSON 载荷")
        return []
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError as e:
        print(f"[MemoryExtract] 解析失败：{e}")
        return []
    if not isinstance(obj, dict):
        print("[MemoryExtract] 解析失败：根节点非 JSON 对象")
        return []
    memories = obj.get("memories")
    if memories is None:
        # 兼容旧 API 单条形状（deprecated，仅解析层保留）
        single = obj.get("memory_to_save")
        if isinstance(single, str) and single.strip():
            topic = obj.get("memory_topic")
            t = topic.strip() if isinstance(topic, str) and topic.strip() else None
            return [(single.strip(), t)]
        print(
            "[MemoryExtract] 解析失败：JSON 中缺少 memories 数组"
            f"（已提取载荷预览：{payload[:120]}…）"
        )
        return []
    if not isinstance(memories, list):
        return []
    out: list[tuple[str, str | None]] = []
    for item in memories:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        topic = item.get("topic")
        t = topic.strip() if isinstance(topic, str) and topic.strip() else None
        out.append((content.strip(), t))
    return out


def request_memory_llm_json(
    settings_manager,
    messages: list[dict[str, Any]],
    *,
    max_attempts: int = 2,
) -> str | None:
    """记忆专用 LLM：response_format → prompt JSON 降级；失败时有限重试。"""
    from llm.model_service import ModelService

    sm = settings_manager
    binding = sm.get_memory_binding()
    conn_id = binding.get("connection_id", "default")
    model = binding.get("model") or ""
    cache = sm.get_capability_cache(conn_id, model) or {}
    json_mode = (cache.get("json_mode") or "").lower()

    ms = ModelService.get_instance(sm)

    def rf(msgs: list[dict]) -> str | None:
        return ms.memory_chat_completions(msgs, response_format_json=True)

    def plain(msgs: list[dict]) -> str | None:
        return ms.memory_chat_completions(msgs, response_format_json=False)

    def _once() -> str | None:
        if json_mode == "natural_only":
            return plain(messages)
        if json_mode == "response_format":
            text = rf(messages)
            if text:
                return text
            return plain(messages)
        return json_only_policy(messages, llm_caller_json_rf=rf, llm_caller_plain=plain)

    last: str | None = None
    for attempt in range(1, max_attempts + 1):
        last = _once()
        if last and last.strip():
            return last
        if attempt < max_attempts:
            print(f"[MemoryExtract] 记忆模型无正文，重试 {attempt}/{max_attempts - 1}…")
    return last


def run_memory_extract(
    history_slice: list[dict[str, Any]],
    settings_manager,
) -> list[tuple[str, str | None]]:
    """对对话片段执行记忆抽取，返回待写入条目列表。"""
    if not history_slice:
        return []
    system = load_extract_system_prompt()
    user_payload = build_extract_user_payload(history_slice)
    if not user_payload:
        return []
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_payload},
    ]
    raw = request_memory_llm_json(settings_manager, messages)
    items = parse_extract_response(raw)
    if items:
        print(f"[MemoryExtract] 抽取到 {len(items)} 条候选记忆")
    else:
        if raw and (raw or "").strip():
            print("[MemoryExtract] 记忆模型已响应，但解析后无有效记忆条目")
            preview = raw.strip().replace("\n", " ")[:160]
            print(f"[MemoryExtract] 响应预览：{preview}…")
        else:
            print(
                "[MemoryExtract] 记忆模型无有效响应（可能为网络/限流、Key 无效，"
                "或 Qwen 等模型思考链占满 token；请先在设置→记忆管理点「测试记忆抽取」）"
            )
    return items
