import requests


import requests


class ChatManager:
    def __init__(self, settings_manager, persona_path: str):
        self.sm = settings_manager
        self.persona_path = persona_path

        self.chat_history = []
        self._load_persona()

    # ---------- Persona ----------
    def _load_persona(self):
        try:
            with open(self.persona_path, "r", encoding="utf-8") as f:
                self.base_persona = f.read().strip()
        except Exception:
            self.base_persona = ""

    def _build_persona(self) -> str:
        user_name = self.sm.get("user", "display_name", default="主人")
        return (
            f"{self.base_persona}\n\n"
            f"你必须始终称呼用户为「{user_name}」，不要使用其他称呼。"
        )

    # ---------- Public: Chat ----------
    def chat(self, user_text: str) -> str | None:
        self._append_user(user_text)

        messages = self._build_chat_messages()

        reply = self._request_llm(messages)
        if reply:
            self._append_assistant(reply)
        return reply

    # ---------- Public: Screen Observation ----------
    def send_screen_observation(self, description: str) -> str | None:
        """
        ⚠️ 屏幕评论：
        - 不读取 chat_history
        - 只基于 persona + 当前截图描述
        """

        messages = [
            {"role": "system", "content": self._build_persona()},
            {
                "role": "user",
                "content": (
                    "你刚刚观察了用户的电脑屏幕。"
                    "下面是对屏幕内容的客观描述。"
                    "请你以角色的口吻，对用户正在做的事情进行自然、即时的评论，"
                    "不要延展成剧情，不要回忆过去的对话，"
                    "评论控制在 150 字以内。"
                    f"\n\n{description}"
                ),
            },
        ]

        reply = self._request_llm(messages)
        if reply:
            # ✅ 写回聊天历史（单向）
            self._append_assistant(
                f"【刚刚对屏幕的评论】\n{reply}"
            )
        return reply

    # ---------- History ----------
    def _append_user(self, text: str):
        self.chat_history.append(
            {"role": "user", "content": text.strip() + "\n\n"}
        )
        self._trim_history()

    def _append_assistant(self, text: str):
        self.chat_history.append(
            {"role": "assistant", "content": text.strip() + "\n\n"}
        )
        self._trim_history()

    def _trim_history(self):
        max_rounds = int(
            self.sm.get("llm", "history_rounds", default=6)
        )
        max_msgs = max_rounds * 2
        if len(self.chat_history) > max_msgs:
            self.chat_history = self.chat_history[-max_msgs:]

    def _build_chat_messages(self):
        return [
            {"role": "system", "content": self._build_persona()},
            *self.chat_history,
        ]

    # ---------- LLM ----------
    def _request_llm(self, messages: list[dict]) -> str | None:
        provider = self.sm.get("llm", "provider", default="deepseek")
        api_key = self.sm.get("llm", "api_key", default="")
        base_url = self.sm.get("llm", "base_url", default="")
        model = self.sm.get("llm", "model", default="")
        temperature = float(
            self.sm.get("llm", "temperature", default=1.0)
        )
        max_tokens = int(
            self.sm.get("llm", "max_tokens", default=512)
        )

        if not api_key or not base_url or not model:
            print("[ChatManager] LLM 配置不完整")
            return None

        base_url = base_url.rstrip("/")

        # -------- URL 处理逻辑 --------
        # custom: 认为用户给的是完整 endpoint
        # 其他 provider: 自动补全 /v1/chat/completions
        if provider == "custom":
            url = base_url
        else:
            if base_url.endswith("/v1/chat/completions"):
                url = base_url
            else:
                url = f"{base_url}/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        try:
            resp = requests.post(
                url, headers=headers, json=payload, timeout=120
            )
            resp.raise_for_status()
            data = resp.json()
            return (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
        except Exception as e:
            print("[ChatManager] LLM 请求失败：", e)
            print("[ChatManager] 请求 URL：", url)
            return None
