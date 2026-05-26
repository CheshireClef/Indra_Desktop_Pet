# src/llm/providers/registry.py
"""
Vendor 注册表：预置服务商的 base_url、协议类型（不硬编码 model id）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REGISTRY_CACHE: dict[str, dict[str, Any]] | None = None


def load_registry() -> dict[str, dict[str, Any]]:
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is not None:
        return _REGISTRY_CACHE
    path = Path(__file__).resolve().parent / "registry.json"
    with open(path, "r", encoding="utf-8") as f:
        _REGISTRY_CACHE = json.load(f)
    return _REGISTRY_CACHE


def list_vendor_ids() -> list[str]:
    return list(load_registry().keys())


def get_vendor(vendor_id: str) -> dict[str, Any] | None:
    return load_registry().get(vendor_id)


def vendor_label(vendor_id: str) -> str:
    v = get_vendor(vendor_id)
    return (v or {}).get("label") or vendor_id


def default_base_url(vendor_id: str) -> str:
    v = get_vendor(vendor_id)
    return (v or {}).get("base_url") or ""


def requires_api_key(vendor_id: str) -> bool:
    v = get_vendor(vendor_id)
    if not v:
        return True
    return bool(v.get("requires_api_key", True))
