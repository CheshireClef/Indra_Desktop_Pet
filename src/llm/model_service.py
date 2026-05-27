# src/llm/model_service.py
"""
模型服务门面：从 SettingsManager 解析 connection，提供统一 OpenAI 兼容客户端。
"""
from __future__ import annotations

from typing import Any

from llm.clients.openai_compatible import OpenAICompatibleClient
from llm.clients.url_utils import chat_completions_url, normalize_base_url


class ModelService:
    _instance: "ModelService | None" = None

    def __init__(self, settings_manager):
        self.sm = settings_manager
        self._client_cache: dict[str, OpenAICompatibleClient] = {}

    @classmethod
    def get_instance(cls, settings_manager=None) -> "ModelService":
        if cls._instance is None:
            if settings_manager is None:
                from settings_manager import SettingsManager
                settings_manager = SettingsManager.get_instance()
            cls._instance = cls(settings_manager)
        return cls._instance

    @classmethod
    def reset_cache(cls):
        """配置变更后清空客户端缓存。"""
        if cls._instance:
            cls._instance._client_cache.clear()

    def _connection_by_id(self, conn_id: str) -> dict[str, Any] | None:
        models = self.sm.get_models_block()
        for c in models.get("connections") or []:
            if isinstance(c, dict) and c.get("id") == conn_id:
                return c
        return None

    def resolve_connection(self, role: str = "chat") -> dict[str, Any] | None:
        """role: chat | vision"""
        models = self.sm.get_models_block()
        if role == "vision":
            vision = models.get("vision") or {}
            if vision.get("same_connection_as_chat", True):
                conn_id = (models.get("chat") or {}).get("connection_id", "default")
            else:
                conn_id = vision.get("connection_id", "default")
        else:
            conn_id = (models.get("chat") or {}).get("connection_id", "default")
        return self._connection_by_id(conn_id)

    def get_chat_client(self) -> OpenAICompatibleClient | None:
        binding = self.sm.get_chat_binding()
        if not binding.get("model"):
            return None
        return self._client_for_binding(binding)

    def get_vision_client(self) -> OpenAICompatibleClient | None:
        binding = self.sm.get_vision_binding()
        if not binding.get("model"):
            return None
        api_key = binding.get("api_key") or ""
        base = binding.get("base_url") or ""
        if not base:
            return None
        # 本地服务可无 key
        from llm.providers.registry import requires_api_key
        vendor = binding.get("vendor", "custom_openai")
        if requires_api_key(vendor) and not api_key:
            return None
        client = self._client_for_binding(binding)
        if client:
            client.vision_hints = self.get_vision_hints(binding)
        return client

    def get_vision_hints(self, binding: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """读取当前识图模型在 capabilities_cache 中探测成功的请求参数。"""
        binding = binding or self.sm.get_vision_binding()
        models = self.sm.get_models_block()
        vision = models.get("vision") or {}
        if vision.get("same_connection_as_chat", True):
            conn_id = (models.get("chat") or {}).get("connection_id", "default")
        else:
            conn_id = vision.get("connection_id", "default")
        model = binding.get("model") or ""
        if not model:
            return None
        cache = self.sm.get_capability_cache(conn_id, model) or {}
        hints = cache.get("vision_hints")
        return hints if isinstance(hints, dict) else None

    def _client_for_binding(self, binding: dict[str, Any]) -> OpenAICompatibleClient:
        base = normalize_base_url(binding.get("base_url") or "")
        model = binding.get("model") or ""
        api_key = binding.get("api_key") or ""
        cache_key = f"{base}|{api_key}|{model}"
        if cache_key not in self._client_cache:
            self._client_cache[cache_key] = OpenAICompatibleClient(
                base, api_key, model
            )
        return self._client_cache[cache_key]

    def chat_completions(
        self,
        messages: list[dict],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format_json: bool = False,
    ) -> str | None:
        binding = self.sm.get_chat_binding()
        client = self._client_for_binding(binding) if binding.get("model") else None
        if not client:
            print("[ModelService] 对话模型配置不完整")
            return None
        t = temperature if temperature is not None else float(binding.get("temperature", 1.0))
        m = max_tokens if max_tokens is not None else int(binding.get("max_tokens", 512))
        return client.chat_completions(
            messages,
            temperature=t,
            max_tokens=m,
            response_format_json=response_format_json,
        )

    # 兼容旧代码：返回完整 chat/completions URL
    def legacy_chat_completions_url(self) -> str:
        binding = self.sm.get_chat_binding()
        return chat_completions_url(binding.get("base_url") or "")
