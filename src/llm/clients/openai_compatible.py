# src/llm/clients/openai_compatible.py
"""
OpenAI 兼容 Chat Completions 客户端（对话 + 多模态识图）。
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import requests

from llm.clients.response_utils import extract_message_content, extract_vision_message_content
from llm.clients.url_utils import chat_completions_url
from llm.clients.vision_adapter import VisionHints, merge_vision_hints
from llm.clients.vision_request import (
    build_vision_chat_payload,
    build_vision_user_message_with_hints,
    guess_image_mime,
)
from utils import resource_path

_SCREEN_DESCRIBE_PROMPT = (
    "请客观、简要地描述这张屏幕截图的内容，描述用户此时可能在做什么，"
    "如果看到视频和游戏窗口，将一部分重点放在视频和游戏窗口的描述上。"
    "回答字数控制在200字以内不要分段。"
)


class OpenAICompatibleClient:
    """统一封装 chat/completions 与识图请求。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout: int = 120,
    ):
        self.base_url = base_url
        self.api_key = api_key or ""
        self.model = model
        self.timeout = timeout
        self.chat_url = chat_completions_url(base_url)
        # 由 ModelService 注入：capabilities_cache 中探测成功的 vision_hints
        self.vision_hints: dict[str, Any] | None = None

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def chat_completions(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 1.0,
        max_tokens: int = 512,
        response_format_json: bool = False,
    ) -> str | None:
        if not self.chat_url or not self.model:
            return None
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if response_format_json:
            payload["response_format"] = {"type": "json_object"}

        try:
            return self._post_chat(payload, allow_format_retry=response_format_json)
        except Exception as e:
            print(f"[OpenAICompatibleClient] chat 失败: {e} url={self.chat_url}")
            return None

    def _post_chat(self, payload: dict[str, Any], *, allow_format_retry: bool) -> str | None:
        resp = requests.post(
            self.chat_url,
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        if allow_format_retry and "response_format" in payload and resp.status_code >= 400:
            payload = {k: v for k, v in payload.items() if k != "response_format"}
            print("[OpenAICompatibleClient] response_format 失败，降级重试")
            resp = requests.post(
                self.chat_url,
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
        resp.raise_for_status()
        text = extract_message_content(resp.json())
        return text if text else None

    def describe_image(self, image_path: Path) -> str | None:
        if not self.chat_url or not self.model:
            return None
        abs_path = Path(resource_path(str(image_path)))
        with open(abs_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
        mime = guess_image_mime(abs_path)
        hints = merge_vision_hints(
            self.base_url,
            self.model,
            cached=self.vision_hints,
        )
        # 正式截图用较高细节；探测阶段用 low 省 token
        screen_hints = VisionHints.from_dict(
            {**hints.to_dict(), "detail": "high"}
        )
        user_msg = build_vision_user_message_with_hints(
            _SCREEN_DESCRIBE_PROMPT,
            image_b64,
            screen_hints,
            mime=mime,
        )
        payload = build_vision_chat_payload(
            self.model,
            user_msg,
            base_url=self.base_url,
            max_tokens=512,
            temperature=0.2,
            vision_hints=screen_hints.to_dict(),
        )
        try:
            resp = requests.post(
                self.chat_url,
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
            if resp.status_code >= 400:
                print(
                    f"[OpenAICompatibleClient] describe_image HTTP {resp.status_code}: "
                    f"{(resp.text or '')[:400]}"
                )
                return None
            resp.raise_for_status()
            text = extract_vision_message_content(resp.json())
            if not text:
                print("[OpenAICompatibleClient] describe_image 返回空正文（请确认模型支持多模态）")
            return text if text else None
        except Exception as e:
            print(f"[OpenAICompatibleClient] describe_image 失败: {e}")
            return None
