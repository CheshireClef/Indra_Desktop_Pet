# src/llm/chat_manager.py
import requests


class ChatManager:
    def __init__(self, settings_manager, persona_path: str):
        self.settings = settings_manager
        self.persona_path = persona_path
        self.persona_text = self._load_persona()
        self.history = []

    # ---------- persona ----------
    def _load_persona(self) -> str:
        try:
            with open(self.persona_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return ""

    def _build_persona_prompt(self) -> str:
        user_name = self.settings.get(
            "user", "display_name", default="主人"
        )

        extra = (
            f"\n\n【重要规则】\n"
            f"你必须始终称呼用户为「{user_name}」，"
            f"无论任何场景下都不要使用其他称呼。\n"
        )

        return (self.persona_text or "") + extra

    # ---------- history ----------
    def _max_history_messages(self) -> int:
        rounds = self.settings.get("llm", "history_rounds", default=10)
        try:
            rounds = int(rounds)
        except Exception:
            rounds = 6
        return max(1, rounds) * 2

    def _trim_history(self):
        max_len = self._max_history_messages()
        if len(self.history) > max_len:
            self.history = self.history[-max_len:]

    # ---------- public: 普通聊天 ----------
    def chat(self, user_text: str) -> str:
        self.history.append({
            "role": "user",
            "content": user_text
        })
        self._trim_history()

        messages = [{
            "role": "system",
            "content": self._build_persona_prompt()
        }]
        messages.extend(self.history)

        reply = self._call_llm(messages)

        if reply:
            reply = reply.rstrip() + "\n\n"
            self.history.append({
                "role": "assistant",
                "content": reply
            })
            self._trim_history()

        return reply

    # ---------- public: 屏幕观察 ----------
    def send_screen_observation(self, description: str) -> str:
        messages = [
            {
                "role": "system",
                "content": self._build_persona_prompt()
            },
            {
                "role": "system",
                "content": (
                    "你刚刚观察了用户的电脑屏幕。"
                    "下面是对屏幕内容的客观描述。"
                    "请你以角色的口吻，对用户正在做的事情进行自然、即时的评论，"
                    "不要延展成剧情，不要回忆过去的对话，"
                    "评论控制在 150 字以内。"
                )
            },
            {
                "role": "system",
                "content": f"屏幕内容描述：{description}"
            }
        ]

        reply = self._call_llm(messages)

        if reply:
            reply = reply.rstrip() + "\n\n"

        return reply

    # ---------- LLM dispatch ----------
    def _call_llm(self, messages: list[dict]) -> str:
        provider = self.settings.get("llm", "provider", default="deepseek")
        temperature = self.settings.get("llm", "temperature", default=1.0)

        if provider == "deepseek":
            return self._call_deepseek(messages, temperature)
        elif provider == "openai":
            return self._call_openai(messages, temperature)
        elif provider == "custom":
            return self._call_custom(messages, temperature)
        else:
            return "[未配置语言模型]"

    # ---------- DeepSeek ----------
    def _call_deepseek(self, messages, temperature):
        api_key = self.settings.get("llm", "api_key", default="")
        base_url = self.settings.get("llm", "base_url", default="https://api.deepseek.com")
        model = self.settings.get("llm", "model", default="deepseek-chat")
        max_tokens = self.settings.get("llm", "max_tokens", default=512)

        if not api_key:
            return "[未设置 DeepSeek API Key]"

        url = base_url.rstrip("/") + "/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[DeepSeek 请求失败：{e}]"

    # ---------- OpenAI ----------
    def _call_openai(self, messages, temperature):
        api_key = self.settings.get("llm", "api_key", default="")
        base_url = self.settings.get("llm", "base_url", default="https://api.openai.com")
        model = self.settings.get("llm", "model", default="gpt-4o-mini")
        max_tokens = self.settings.get("llm", "max_tokens", default=512)

        if not api_key:
            return "[未设置 OpenAI API Key]"

        url = base_url.rstrip("/") + "/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[OpenAI 请求失败：{e}]"

    # ---------- Custom ----------
    def _call_custom(self, messages, temperature):
        api_key = self.settings.get("llm", "api_key", default="")
        url = self.settings.get("llm", "base_url", default="").strip()
        model = self.settings.get("llm", "model", default="")
        max_tokens = self.settings.get("llm", "max_tokens", default=512)

        if not url or not model:
            return "[自定义 LLM 配置不完整]"

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[Custom LLM 请求失败：{e}]"
