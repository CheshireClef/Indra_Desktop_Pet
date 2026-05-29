# src/llm/clients/reasoning_extras.py
"""
结构化 LLM 请求（记忆抽取、JSON 探测、识图）的「关闭/压低深度思考」扩展参数。

各厂商字段名不同，统一在此按 registry + 模型族启发合并，避免切换非 Qwen 推理模型时正文为空。
"""
from __future__ import annotations

import re
from typing import Any, Literal

from llm.clients.vision_adapter import VisionHints, match_vendor_id, merge_vision_hints
from llm.providers.registry import get_vendor

Profile = Literal["structured", "chat", "inherit"]

# 模型族启发：structured（记忆/JSON/识图）
_MODEL_HEURISTIC_RULES: list[tuple[re.Pattern[str], dict[str, Any]]] = [
    # Qwen3 / 通义：SiliconFlow、DashScope、vLLM 等
    (
        re.compile(r"qwen3[\.\-_/]|/qwen3", re.I),
        {
            "enable_thinking": False,
            "chat_template_kwargs": {"enable_thinking": False},
        },
    ),
    # 智谱 GLM-4 系列
    (
        re.compile(r"glm[-_]?4|glm4|glm[-_]?[\d.]*v", re.I),
        {"enable_thinking": False},
    ),
    # MiniMax
    (re.compile(r"minimax|abab[\d._-]", re.I), {"enable_thinking": False}),
    # OpenAI o 系 / GPT-5 推理档
    (
        re.compile(r"\bgpt-5|gpt-5\.|/o[134](?:-|$|/)", re.I),
        {"reasoning_effort": "none"},
    ),
    # OpenRouter 上常见 reasoning 模型 id
    (
        re.compile(r"deepseek-r1|deepseek[-_/]reasoner|/r1(?:-|$)", re.I),
        {},  # R1 类通常无法关思考，仅依赖解析回退
    ),
    # Google Gemini 思考档（兼容模式部分网关透传）
    (
        re.compile(r"gemini-2\.5|gemini-3|gemini2\.5", re.I),
        {
            "thinking_config": {"thinking_budget": 0, "include_thoughts": False},
        },
    ),
    # Moonshot Kimi 思考模型
    (
        re.compile(r"kimi[-_]?k2|k2[-_]?thinking|moonshot.*thinking", re.I),
        {"enable_thinking": False},
    ),
    # DeepSeek VL / 视觉
    (
        re.compile(r"deepseek.*(?:vl|vision)", re.I),
        {"enable_thinking": False},
    ),
]

# 主聊天：关闭 API 级思考链，避免 reasoning_content 或 content 混入独白
_CHAT_HEURISTIC_RULES: list[tuple[re.Pattern[str], dict[str, Any]]] = [
    (
        re.compile(r"deepseek[-_]?v4|deepseek[-_]?chat|deepseek[-_]?reasoner", re.I),
        {"thinking": {"type": "disabled"}},
    ),
]


def _deep_merge_dict(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, val in overlay.items():
        if (
            key in out
            and isinstance(out[key], dict)
            and isinstance(val, dict)
        ):
            out[key] = _deep_merge_dict(out[key], val)
        else:
            out[key] = val
    return out


def _vendor_reasoning_defaults(vendor_id: str | None) -> dict[str, Any]:
    if not vendor_id:
        return {}
    vendor_cfg = get_vendor(vendor_id) or {}
    rd = vendor_cfg.get("reasoning_defaults")
    if isinstance(rd, dict):
        return dict(rd)
    # 兼容旧配置：vision_defaults 中的 enable_thinking 同步到结构化路径
    vd = vendor_cfg.get("vision_defaults") or {}
    if isinstance(vd, dict) and "enable_thinking" in vd:
        return {"enable_thinking": vd["enable_thinking"]}
    return {}


def _model_heuristic_extras(
    model: str, rules: list[tuple[re.Pattern[str], dict[str, Any]]] | None = None
) -> dict[str, Any]:
    m = (model or "").strip()
    if not m:
        return {}
    merged: dict[str, Any] = {}
    for pattern, extras in rules or _MODEL_HEURISTIC_RULES:
        if pattern.search(m):
            merged = _deep_merge_dict(merged, extras)
    return merged


def reasoning_payload_extras(
    base_url: str,
    model: str,
    *,
    vendor_id: str | None = None,
    profile: Profile = "structured",
    vision_hints: VisionHints | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    合并进 chat/completions 请求体的扩展字段。

    profile=structured：记忆/JSON/识图，尽量关闭深度思考（registry + 模型族启发）。
    profile=chat：主聊天，应用 registry + 聊天专用启发（如 DeepSeek V4 关 thinking）。
    profile=inherit：仅 registry 默认，不叠加模型启发（预留）。
    """
    vid = vendor_id or match_vendor_id(base_url)
    extras = _vendor_reasoning_defaults(vid)

    if profile == "structured":
        extras = _deep_merge_dict(extras, _model_heuristic_extras(model))
    elif profile == "chat":
        extras = _deep_merge_dict(
            extras, _model_heuristic_extras(model, _CHAT_HEURISTIC_RULES)
        )

    # 识图探测缓存的 hints 优先级最高（用户已探测成功的组合）
    if vision_hints is not None:
        if isinstance(vision_hints, VisionHints):
            h = vision_hints
        else:
            h = VisionHints.from_dict(vision_hints)
        if h.enable_thinking is not None:
            extras["enable_thinking"] = h.enable_thinking
            # vLLM + Qwen 探测成功时常用 chat_template_kwargs
            if h.enable_thinking is False and re.search(
                r"qwen3", (model or ""), re.I
            ):
                extras = _deep_merge_dict(
                    extras,
                    {"chat_template_kwargs": {"enable_thinking": False}},
                )

    return extras


def vision_payload_extras(
    base_url: str,
    model: str,
    hints: VisionHints | None = None,
) -> dict[str, Any]:
    """识图请求扩展字段（结构化 profile + 探测 hints）。"""
    h = hints or merge_vision_hints(base_url, model)
    return reasoning_payload_extras(
        base_url,
        model,
        profile="structured",
        vision_hints=h,
    )
