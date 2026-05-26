# src/llm/providers/catalog.py
"""
从 OpenAI 兼容端点动态拉取模型列表；识图候选启发式过滤。
"""
from __future__ import annotations

import re
from typing import Any

import requests

from llm.clients.url_utils import models_list_url

# 识图模型 id 启发式（软过滤，非硬拒绝）
_VISION_HINT = re.compile(
    r"(vl|vision|gpt-4o|gpt-4\.1|gemini-.*-(pro|flash)|glm-4v|internvl|qwen.*vl)",
    re.IGNORECASE,
)


def fetch_model_ids(
    base_url: str,
    api_key: str = "",
    timeout: int = 30,
) -> list[str]:
    """GET /v1/models，返回模型 id 列表；失败返回空列表。"""
    url = models_list_url(base_url)
    if not url:
        return []
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[ModelCatalog] 拉取模型列表失败: {e}")
        return []
    ids: list[str] = []
    for item in data.get("data") or []:
        if isinstance(item, dict):
            mid = item.get("id")
            if isinstance(mid, str) and mid.strip():
                ids.append(mid.strip())
        elif isinstance(item, str):
            ids.append(item.strip())
    return sorted(set(ids))


def filter_vision_candidates(model_ids: list[str]) -> list[str]:
    """优先展示可能支持识图的模型。"""
    matched = [m for m in model_ids if _VISION_HINT.search(m)]
    return matched if matched else list(model_ids)


def model_supports_vision_heuristic(model_id: str) -> bool:
    return bool(_VISION_HINT.search(model_id or ""))
