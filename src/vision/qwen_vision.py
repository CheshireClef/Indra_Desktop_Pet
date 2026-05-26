# src/vision/qwen_vision.py
"""
视觉模型客户端（兼容层）。
已委托 OpenAICompatibleClient；保留 QwenVisionClient 类名供旧代码导入。
"""
from pathlib import Path

from llm.clients.openai_compatible import OpenAICompatibleClient
from llm.clients.url_utils import chat_completions_url, normalize_base_url


class QwenVisionClient:
    """
    Qwen 视觉客户端类（薄封装）
    封装了 API 请求构建、图片 Base64 编码和响应解析。
    """

    def __init__(self, api_url: str, api_key: str, model: str):
        base = normalize_base_url(api_url) or api_url
        if "chat/completions" in (api_url or ""):
            base = normalize_base_url(api_url)
        self._client = OpenAICompatibleClient(base, api_key, model)
        self.api_url = chat_completions_url(base) or api_url
        self.api_key = api_key
        self.model = model

    def describe_image(self, image_path: Path) -> str | None:
        """将截图发送给视觉模型，返回文字概括；失败返回 None。"""
        return self._client.describe_image(image_path)
