# src/llm/clients/vision_adapter.py
"""
多模态识图适配：按服务商/模型合并默认参数，探测时自适应重试并缓存可用配置。

设计原则：
- 不针对单个 model id 硬编码；以 registry 中 vendor 级 vision_defaults 为主
- 探测阶段自动尝试图片尺寸、enable_thinking、图文顺序等组合
- 成功组合写入 capabilities_cache.vision_hints，正式识图复用
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterator
from urllib.parse import urlparse

from llm.clients.response_utils import extract_vision_message_content
from llm.clients.vision_probe_assets import DEFAULT_PROBE_SIDE, PROBE_IMAGES
from llm.providers.registry import get_vendor, load_registry

# 探测提示词（短，省 token）
_PROBE_PROMPT = "请用一句话描述这张图片的主色调或内容，不超过20字。"

# HTTP 400 且含下列关键词时，尝试更大探测图
_SIZE_ERROR_HINTS = re.compile(
    r"width|height|size|pixel|resolution|dimension|larger than|too small|min.*image",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class VisionHints:
    """识图请求偏好（可序列化进 capabilities_cache）。"""

    probe_side: int = DEFAULT_PROBE_SIDE
    enable_thinking: bool | None = False
    content_order: str = "image_first"  # image_first | text_first
    detail: str = "low"  # low | high | auto

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "probe_side": self.probe_side,
            "content_order": self.content_order,
            "detail": self.detail,
        }
        if self.enable_thinking is not None:
            d["enable_thinking"] = self.enable_thinking
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> VisionHints:
        if not data:
            return cls()
        et = data.get("enable_thinking")
        if et is not None and not isinstance(et, bool):
            et = None
        return cls(
            probe_side=int(data.get("probe_side") or DEFAULT_PROBE_SIDE),
            enable_thinking=et if isinstance(et, bool) else False,
            content_order=str(data.get("content_order") or "image_first"),
            detail=str(data.get("detail") or "low"),
        )


@dataclass
class VisionProbeAttempt:
    hints: VisionHints
    max_tokens: int = 128
    label: str = ""


def match_vendor_id(base_url: str) -> str | None:
    """根据 base_url 匹配 registry 中的 vendor id。"""
    base = (base_url or "").strip().rstrip("/").lower()
    if not base:
        return None
    host = urlparse(base if "://" in base else f"https://{base}").netloc.lower()
    best_id: str | None = None
    best_len = 0
    for vid, cfg in load_registry().items():
        bu = (cfg.get("base_url") or "").strip().rstrip("/").lower()
        if not bu:
            continue
        bu_host = urlparse(bu).netloc
        if host == bu_host or host.endswith(bu_host) or bu_host in host:
            if len(bu_host) > best_len:
                best_len = len(bu_host)
                best_id = vid
    if best_id:
        return best_id
    # 常见别名
    if "siliconflow" in host:
        return "siliconflow"
    if "openrouter" in host:
        return "openrouter"
    if "minimax" in host:
        return "minimax"
    if "openai.com" in host:
        return "openai"
    return None


def _model_heuristic_hints(model: str) -> VisionHints:
    """模型名启发式（族级，非单模型白名单）。"""
    m = (model or "").lower()
    hints = VisionHints()
    # GLM / 智谱 VL：官方要求边长 >28，探测用 64 更稳
    if re.search(r"glm[-_]?[\d.]*v|glm-4\.5v|glm4v", m):
        hints = VisionHints(probe_side=64, enable_thinking=False)
    elif "qwen3." in m or "qwen3-" in m:
        hints = VisionHints(probe_side=64, enable_thinking=False)
    elif "minimax" in m or "abab" in m:
        hints = VisionHints(probe_side=64, enable_thinking=False)
    elif "deepseek" in m and ("vl" in m or "vision" in m):
        hints = VisionHints(probe_side=64, enable_thinking=False)
    return hints


def merge_vision_hints(
    base_url: str,
    model: str,
    *,
    vendor_id: str | None = None,
    cached: dict[str, Any] | None = None,
) -> VisionHints:
    """合并：registry 默认 → 模型启发 → 用户探测缓存（优先级递增）。"""
    vid = vendor_id or match_vendor_id(base_url)
    merged = VisionHints()

    if vid:
        vendor_cfg = get_vendor(vid) or {}
        vd = vendor_cfg.get("vision_defaults") or {}
        if isinstance(vd, dict):
            merged = VisionHints.from_dict({**merged.to_dict(), **vd})

    merged = VisionHints.from_dict(
        {**merged.to_dict(), **_model_heuristic_hints(model).to_dict()}
    )

    if cached:
        merged = VisionHints.from_dict({**merged.to_dict(), **cached})

    if merged.probe_side not in PROBE_IMAGES:
        merged = VisionHints.from_dict(
            {**merged.to_dict(), "probe_side": DEFAULT_PROBE_SIDE}
        )
    return merged


def build_vision_user_message_with_hints(
    text: str,
    image_b64: str,
    hints: VisionHints,
    *,
    mime: str = "image/png",
) -> dict[str, Any]:
    """按 hints 构造多模态 user message。"""
    image_part = {
        "type": "image_url",
        "image_url": {
            "url": f"data:{mime};base64,{image_b64}",
            "detail": hints.detail,
        },
    }
    text_part = {"type": "text", "text": text}
    if hints.content_order == "text_first":
        parts = [text_part, image_part]
    else:
        parts = [image_part, text_part]
    return {"role": "user", "content": parts}


def vision_payload_extras(
    base_url: str,
    model: str,
    hints: VisionHints | None = None,
) -> dict[str, Any]:
    """合并服务商/模型/hints 的扩展字段（如 enable_thinking）。"""
    h = hints or merge_vision_hints(base_url, model)
    extras: dict[str, Any] = {}
    if h.enable_thinking is not None:
        extras["enable_thinking"] = h.enable_thinking
    return extras


def _attempt_from_hints(hints: VisionHints, label: str) -> VisionProbeAttempt:
    return VisionProbeAttempt(hints=hints, max_tokens=128, label=label)


def iter_probe_attempts(
    base_url: str,
    model: str,
    *,
    vendor_id: str | None = None,
    cached_hints: dict[str, Any] | None = None,
) -> Iterator[VisionProbeAttempt]:
    """
    分阶段生成探测尝试（通常 1～4 次请求），避免笛卡尔积刷 API。
    """
    base = merge_vision_hints(
        base_url, model, vendor_id=vendor_id, cached=cached_hints
    )
    # 阶段 1：合并后的最优猜测（含用户上次探测缓存）
    yield _attempt_from_hints(base, "default")

    # 阶段 2 候选：仅在阶段 1 失败后按需尝试
    fallbacks: list[VisionHints] = []

    for side in (128, 64, 32):
        if side != base.probe_side and side in PROBE_IMAGES:
            fallbacks.append(
                VisionHints.from_dict({**base.to_dict(), "probe_side": side})
            )

    if base.enable_thinking is not False:
        fallbacks.append(
            VisionHints.from_dict({**base.to_dict(), "enable_thinking": False})
        )
    if base.enable_thinking is not True:
        fallbacks.append(
            VisionHints.from_dict({**base.to_dict(), "enable_thinking": True})
        )

    if base.content_order != "text_first":
        fallbacks.append(
            VisionHints.from_dict({**base.to_dict(), "content_order": "text_first"})
        )

    seen = {tuple(sorted(base.to_dict().items()))}
    for h in fallbacks:
        key = tuple(sorted(h.to_dict().items()))
        if key in seen:
            continue
        seen.add(key)
        yield _attempt_from_hints(
            h,
            f"side={h.probe_side},think={h.enable_thinking},order={h.content_order}",
        )
        if len(seen) >= 6:
            return


def _is_size_related_error(status: int, body: str) -> bool:
    if status != 400:
        return False
    return bool(_SIZE_ERROR_HINTS.search(body or ""))


def run_vision_probe_attempt(
    client: Any,
    attempt: VisionProbeAttempt,
    *,
    prompt: str = _PROBE_PROMPT,
) -> tuple[bool, str, dict[str, Any] | None]:
    """
    执行单次识图探测。
    返回 (成功, 失败原因简述, 成功时的 vision_hints dict)。
    """
    import requests

    b64 = PROBE_IMAGES.get(attempt.hints.probe_side)
    if not b64:
        return False, "无探测图资源", None

    user_msg = build_vision_user_message_with_hints(
        prompt, b64, attempt.hints, mime="image/png"
    )
    payload: dict[str, Any] = {
        "model": client.model,
        "messages": [user_msg],
        "stream": False,
        "max_tokens": attempt.max_tokens,
        "temperature": 0,
    }
    payload.update(vision_payload_extras(client.base_url, client.model, attempt.hints))

    try:
        resp = requests.post(
            client.chat_url,
            headers=client._headers(),
            json=payload,
            timeout=60,
        )
        body_text = resp.text or ""
        if resp.status_code >= 400:
            reason = f"HTTP {resp.status_code}: {body_text[:200]}"
            if _is_size_related_error(resp.status_code, body_text):
                return False, "image_too_small", None
            return False, reason, None

        text = extract_vision_message_content(resp.json())
        if text and text.strip():
            return True, "", attempt.hints.to_dict()
        return False, "empty_content", None
    except Exception as e:
        return False, str(e), None


def adaptive_probe_vision(
    client: Any,
    *,
    vendor_id: str | None = None,
    cached_hints: dict[str, Any] | None = None,
) -> tuple[bool, dict[str, Any]]:
    """
    自适应识图探测，返回 (supports_vision, meta)。
    meta 含 supports_vision、vision_hints（成功时）、probe_note（失败时）。
    """
    if not client.chat_url or not client.model:
        return False, {"supports_vision": False, "probe_note": "配置不完整"}

    last_reason = ""
    size_failed = False
    attempts = list(
        iter_probe_attempts(
            client.base_url,
            client.model,
            vendor_id=vendor_id,
            cached_hints=cached_hints,
        )
    )

    for i, attempt in enumerate(attempts):
        ok, reason, hints = run_vision_probe_attempt(client, attempt)
        if ok and hints:
            print(
                f"[VisionAdapter] 识图探测成功 ({attempt.label}) "
                f"model={client.model}"
            )
            return True, {
                "supports_vision": True,
                "vision_hints": hints,
            }

        last_reason = reason or last_reason
        if reason == "image_too_small":
            size_failed = True
            # 优先只追加更大尺寸尝试
            base_h = attempt.hints
            extra: list[VisionProbeAttempt] = []
            for side in (128, 64):
                if side > base_h.probe_side and side in PROBE_IMAGES:
                    h = VisionHints.from_dict(
                        {**base_h.to_dict(), "probe_side": side}
                    )
                    extra.append(_attempt_from_hints(h, f"size_retry_{side}"))
            attempts[i + 1 : i + 1] = extra
            continue

    note = last_reason or "未知错误"
    if size_failed:
        note = "探测图尺寸不被该模型接受，已尝试更大尺寸仍失败。" + note
    print(
        f"[VisionAdapter] 识图探测未通过 model={client.model} "
        f"last={note[:120]}"
    )
    return False, {
        "supports_vision": False,
        "probe_note": note[:300],
    }
