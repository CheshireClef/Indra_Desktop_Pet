"""
对话管理模块
负责处理与 LLM 的交互，包括：
1. 构建 Prompt (System Persona + User Input)
2. 调用 RAG 检索知识库 (KnowledgeBase)
3. 提取和处理情绪标签 (Emotion Tag) / JSON 结构化输出
4. 管理对话历史 (History)
"""
import json
import re
import requests
import os
import threading
from pathlib import Path
from utils import resource_path
from .knowledge_base import KnowledgeBase
from .long_term_memory import LongTermMemory

class ChatManager:
    """
    对话管理器
    整合了人设 (Persona)、知识库 (RAG) 和 LLM API 调用。
    """
    VALID_EMOTION_TAGS = ["喜爱", "开心", "干杯", "疑问", "伤心", "无聊", "尴尬", "生气", "平常"]
    EMOTION_TAG_FORMAT = "【{}】"  # 标签固定包裹格式
    
    # 通用情绪标签 Prompt（用于屏幕观察等非 JSON 场景）
    def _get_emotion_tag_prompt(self) -> str:
        """
        生成统一的情绪标签输出要求 Prompt，屏幕观察等场景使用。
        """
        return (
            "\n\n【情绪标签输出要求】"
            "1. 请严格分析回复内容的情绪倾向，哪怕只有轻微的情绪（如一点点开心、轻微疑问），也必须选择对应情绪标签，禁止滥用「平常」；"
            "2. 仅当回复内容完全无任何情绪倾向（纯客观陈述、无主观情感）时，才能选择【平常】；"
            "3. 标签必须从以下列表中选择：{}，格式为【标签名】，必须放在回复最后一行，仅含标签无其他内容；"
            "4. 若回复的内容适合【平常】标签，但包含饮酒的情节，请优先选择【干杯】标签；"
            "5. 标签仅用于后台统计，不要体现在对话内容中。"
        ).format(','.join(self.VALID_EMOTION_TAGS))

    # ---------- JSON 结构化输出（聊天场景） ----------
    def _get_json_output_instruction(self) -> str:
        """
        生成「只输出一个 JSON 对象」的说明，含 reply、emotion、memory_to_save、favorability_delta。
        memory_to_save 由 LLM 根据用户本轮（及对话上下文）发言判断是否值得写入长期记忆。
        """
        tags = "、".join(self.VALID_EMOTION_TAGS)
        return (
            "\n\n【输出格式】你必须只输出一个 JSON 对象，不要输出 JSON 以外的任何文字。"
            "输出 JSON 结果时一定要用 Markdown 代码块包裹，例如：\n```json\n{\"reply\":\"……\",\"emotion\":\"开心\",\"memory_to_save\":null,\"memory_topic\":null,\"favorability_delta\":null}\n```"
            "\n字段说明："
            "\n- reply（必填）：你作为角色对用户说的正文。"
            f"\n- emotion（必填）：从以下列表选一个情绪标签：{tags}。请根据回复内容的情绪倾向选择，仅当完全无情绪时选「平常」；若涉及饮酒情节优先选「干杯」。"
            "\n- memory_to_save（可选）：仅当用户本轮或对话中提到了值得长期记住的信息（如偏好、习惯、重要事项）时，填写一条简短概括句；否则填 null。由你根据用户发言判断。"
            "\n- memory_topic（可选）：若填写了 memory_to_save，可同时填写简短主题词便于归类（如「饮酒」「偏好」「工作」），否则填 null。"
            "\n- favorability_delta（可选）：整数或 null，预留字段。"
            '\n示例：{"reply":"……","emotion":"开心","memory_to_save":null,"memory_topic":null,"favorability_delta":null}'
        )
    
    def __init__(self, settings_manager=None, persona_path: str = ""):
        if settings_manager:
            self.sm = settings_manager
        else:
            from settings_manager import SettingsManager
            self.sm = SettingsManager.get_instance()
            
        self.persona_path = resource_path(persona_path)

        self.chat_history = []
        self._load_persona()

        # ========== 知识库初始化 ==========
        self.knowledge_base = KnowledgeBase()
        # 长期记忆模块（SQLite+向量），合并时通过 merge_llm_caller 调用 LLM 做同主题精简
        self._long_term_memory = LongTermMemory(
            self.knowledge_base,
            merge_llm_caller=lambda msgs: self._request_llm(msgs, response_format_json=True),
        )

        # ========== 提取并剥离情绪标签 ==========
    def _extract_and_strip_emotion_tag(self, reply: str) -> tuple[str, str]:
        """
        从LLM回复中提取情绪标签，并返回「剥离标签后的纯回复」+「情绪标签」
        逻辑：
        1. 匹配回复末尾的【标签】格式内容
        2. 校验标签是否在VALID_EMOTION_TAGS中，无效则默认「平常」
        3. 剥离标签后返回纯回复内容
        """
        if not reply.strip():
            return "", "平常"
        
        # 去除回复末尾的空白字符（避免LLM加换行/空格导致匹配失败）
        reply_processed = reply.strip()
        
        # 正则匹配：所有位置的【标签】，标签内容在VALID_EMOTION_TAGS中
        import re
        # 构建有效标签的正则匹配组（避免匹配无效标签）
        valid_tags_pattern = "|".join(re.escape(tag) for tag in self.VALID_EMOTION_TAGS)
        # 匹配【有效标签】，支持标签前后有空格
        pattern = re.compile(r"\s*【(" + valid_tags_pattern + r")】\s*")
        
        # 提取所有匹配到的有效标签
        matches = pattern.findall(reply_processed)
        # 确定最终情绪标签：有匹配则取最后一个，无则默认平常
        emotion_tag = matches[-1].strip() if matches else "平常"
    
        # 剥离所有【标签】格式内容，清理多余空格（多个空格合并为一个）
        pure_reply = pattern.sub("", reply_processed)
        # 合并连续空格/换行，保证回复格式整洁
        pure_reply = re.sub(r"\s+", " ", pure_reply).strip()
    
        # 兜底：若剥离后为空，纯回复置空，标签默认平常
        if not pure_reply:
            pure_reply = ""
            emotion_tag = "平常"
    
        return pure_reply, emotion_tag

    def _parse_llm_response(self, content: str) -> tuple[str | None, str, str | None, str | None, int | None, bool]:
        """
        优先将 LLM 返回内容解析为 JSON；失败则回退到情绪标签剥离+幻觉剔除。
        返回 (reply, emotion, memory_to_save, memory_topic, favorability_delta, json_ok)。
        """
        if not (content or "").strip():
            return "", "平常", None, None, None, False
        raw = content.strip()
        # 尝试去掉可选的 ```json ... ``` 包裹
        if raw.startswith("```"):
            for prefix in ("```json", "```"):
                if raw.startswith(prefix):
                    raw = raw[len(prefix):].strip()
                    break
            if raw.endswith("```"):
                raw = raw[:-3].strip()
        try:
            obj = json.loads(raw)
            if not isinstance(obj, dict):
                raise ValueError("not a dict")
            reply = (obj.get("reply") or "").strip() if obj.get("reply") is not None else ""
            emotion = (obj.get("emotion") or "").strip() or "平常"
            if emotion not in self.VALID_EMOTION_TAGS:
                emotion = "平常"
            memory_to_save = obj.get("memory_to_save")
            if memory_to_save is not None and isinstance(memory_to_save, str):
                memory_to_save = memory_to_save.strip() or None
            else:
                memory_to_save = None
            memory_topic = obj.get("memory_topic")
            if memory_topic is not None and isinstance(memory_topic, str):
                memory_topic = memory_topic.strip() or None
            else:
                memory_topic = None
            favorability_delta = obj.get("favorability_delta")
            if favorability_delta is not None and not isinstance(favorability_delta, int):
                favorability_delta = None
            print(f"[LLM-JSON] 解析成功 | emotion={emotion} | reply_len={len(reply)} | memory_to_save={memory_to_save!r} | memory_topic={memory_topic!r} | favorability_delta={favorability_delta}")
            return reply, emotion, memory_to_save, memory_topic, favorability_delta, True
        except Exception:
            pass
        # 回退：幻觉截断 + 情绪标签剥离
        hallucination_marker = "【刚刚对屏幕的评论】"
        if hallucination_marker in raw:
            pos = raw.find(hallucination_marker)
            raw = raw[:pos].strip()
        clean_reply, emotion_tag = self._extract_and_strip_emotion_tag(raw)
        print(f"[LLM-JSON] 回退到标签解析 | emotion={emotion_tag} | reply_len={len(clean_reply)}")
        return clean_reply, emotion_tag, None, None, None, False

    def get_long_term_memory(self) -> LongTermMemory | None:
        """供设置页记忆管理 UI 使用"""
        return getattr(self, "_long_term_memory", None)
    
    # ---------- Persona（原有逻辑，无改动） ----------
    def _load_persona(self):
        """从文件加载基础人设"""
        try:
            with open(self.persona_path, "r", encoding="utf-8") as f:
                self.base_persona = f.read().strip()
        except Exception:
            self.base_persona = ""

    def _build_persona(self) -> str:
        """构建完整的 System Prompt，包含用户昵称"""
        user_name = self.sm.get("user", "display_name", default="主人")
        return (
            f"{self.base_persona}\n\n"
            f"你必须始终称呼用户为「{user_name}」，不要使用其他称呼。"
        )
    
    def _retrieve_knowledge(self, query: str) -> str:
        """检索知识库，返回相关片段"""
        return self.knowledge_base.retrieve(query)
    
    # 带情绪标签返回的聊天方法；返回 (reply, emotion_tag, error_message)，error_message 非空时仅展示红色气泡
    def chat_with_tag(self, user_text: str) -> tuple[str | None, str, str | None]:
        self._append_user(user_text)
        messages = self._build_chat_messages()
        reply_raw = self._request_llm(messages, response_format_json=True)
        if not (reply_raw or "").strip():
            print("[LLM-聊天] API 返回空")
            return None, "平常", "LLM 返回了空回复"
        reply, emotion, memory_to_save, memory_topic, favorability_delta, json_ok = self._parse_llm_response(reply_raw)
        # 解析成功但 reply 为空
        if json_ok and not (reply or "").strip():
            print("[LLM-聊天] JSON 中 reply 为空")
            return None, "平常", "LLM 返回了空回复"
        self._append_assistant(reply or "")
        # 长期记忆写入：若开关开启且 LLM 返回了 memory_to_save 则写入（带 topic 便于同主题合并）
        if json_ok and (memory_to_save or "").strip() and self.sm.get("behavior", "long_term_memory_enabled", default=False) and self._long_term_memory:
            try:
                self._long_term_memory.add_or_update(
                    (memory_to_save or "").strip(),
                    topic=(memory_topic or "").strip() or None,
                )
            except Exception as e:
                print(f"[ChatManager] 长期记忆写入失败: {e}")
        if json_ok:
            print(f"[LLM-聊天回复] 情绪：{emotion} | 内容预览：{(reply or '')[:50]}...")
            return reply, emotion, None
        print(f"[LLM-聊天回复] 回退解析 情绪：{emotion} | 内容预览：{(reply or '')[:50]}...")
        return reply, emotion, None

    def chat(self, user_text: str) -> str | None:
        pure_reply, _, _ = self.chat_with_tag(user_text)
        return pure_reply

    def _extract_memory_from_screen_description(self, description: str) -> None:
        """
        从屏幕截图的描述中抽取长期记忆，规则与聊天一致：非每次必抽、半结构化（topic+content）。
        仅当长期记忆开关开启且描述非空时调用；抽取结果若有 memory_to_save 则写入记忆库。
        """
        if not (description or "").strip() or not self._long_term_memory:
            return
        prompt = (
            "下面是对用户电脑屏幕内容的客观描述。\n"
            "若其中包含与**用户本人**相关的、值得长期记住的信息（如用户偏好、习惯、正在做的重要事项、工作/学习内容等），"
            "请输出 JSON：{\"memory_to_save\":\"一条简短概括句\",\"memory_topic\":\"主题词（如饮酒、偏好、工作）\"}；"
            "若无则输出 {\"memory_to_save\":null,\"memory_topic\":null}。\n"
            "只输出 JSON，且用 Markdown 代码块包裹，例如：\n```json\n{\"memory_to_save\":\"……\",\"memory_topic\":\"……\"}\n```"
        )
        messages = [
            {"role": "system", "content": "你只输出一个 JSON 对象，包含 memory_to_save 和 memory_topic；无值得记忆的内容时二者为 null。输出时用 Markdown 代码块包裹：```json\n{...}\n```"},
            {"role": "user", "content": prompt + "\n\n屏幕描述：\n" + (description or "").strip()[:2000]},
        ]
        raw = self._request_llm(messages, response_format_json=True)
        if not (raw or "").strip():
            return
        raw = raw.strip()
        if raw.startswith("```"):
            for prefix in ("```json", "```"):
                if raw.startswith(prefix):
                    raw = raw[len(prefix):].strip()
                    break
            if raw.endswith("```"):
                raw = raw[:-3].strip()
        try:
            obj = json.loads(raw)
            if not isinstance(obj, dict):
                return
            memory_to_save = obj.get("memory_to_save")
            if memory_to_save is not None and isinstance(memory_to_save, str):
                memory_to_save = memory_to_save.strip()
            else:
                memory_to_save = ""
            memory_topic = obj.get("memory_topic")
            if memory_topic is not None and isinstance(memory_topic, str):
                memory_topic = memory_topic.strip() or None
            else:
                memory_topic = None
            if memory_to_save:
                self._long_term_memory.add_or_update(memory_to_save, topic=memory_topic)
                print(f"[长期记忆-屏幕] 抽取写入 | topic={memory_topic!r} | content={memory_to_save[:50]}...")
        except Exception as e:
            print(f"[ChatManager] 屏幕描述记忆抽取解析失败: {e}")

    # 带情绪标签返回的屏幕观察方法；可选从屏幕描述中抽取长期记忆（规则与聊天一致）
    def send_screen_observation_with_tag(self, description: str) -> tuple[str | None, str]:
        knowledge_context = self._retrieve_knowledge(description)
        emotion_instruction = self._get_emotion_tag_prompt()
        system_content = self._build_persona() + knowledge_context + emotion_instruction
        messages = [
            {"role": "system", "content": system_content},
            {
                "role": "user",
                "content": (
                    "你刚刚观察了用户的电脑屏幕。"
                    "下面是对屏幕内容的客观描述。"
                    "请你以角色的口吻，对用户正在做的事情进行自然、即时的评论，"
                    "不要延展成剧情，评论控制在 150 字以内。"
                    f"\n\n{description}"
                ),
            },
        ]
        reply = self._request_llm(messages)
        if reply:
            pure_reply, emotion_tag = self._extract_and_strip_emotion_tag(reply)
            if not pure_reply.startswith("【刚刚对屏幕的评论】"):
                import re
                screen_comment_pattern = r'\s*【刚刚对屏幕的评论】.*'
                pure_reply = re.sub(
                    screen_comment_pattern,
                    '',
                    pure_reply,
                    flags=re.DOTALL
                ).strip()
            assistant_msg = f"【刚刚对屏幕的评论】\n{pure_reply}" if pure_reply else ""
            self._append_assistant(assistant_msg)
            print(f"[LLM-屏幕观察] 情绪标签：{emotion_tag} | 内容预览：{pure_reply[:50]}...")
            # 长期记忆：从屏幕描述中抽取（与聊天规则一致，非每次必抽、半结构化）
            if self.sm.get("behavior", "long_term_memory_enabled", default=False) and self._long_term_memory and (description or "").strip():
                try:
                    self._extract_memory_from_screen_description(description)
                except Exception as e:
                    print(f"[ChatManager] 屏幕观察长期记忆抽取失败: {e}")
            return pure_reply, emotion_tag
        # 即使评论失败也尝试从描述抽取记忆（若开启长期记忆）
        if self.sm.get("behavior", "long_term_memory_enabled", default=False) and self._long_term_memory and (description or "").strip():
            try:
                self._extract_memory_from_screen_description(description)
            except Exception as e:
                print(f"[ChatManager] 屏幕观察长期记忆抽取失败: {e}")
        return None, "平常"

    # 原有screen_observation方法兼容
    def send_screen_observation(self, description: str) -> str | None:
        pure_reply, _ = self.send_screen_observation_with_tag(description)
        return pure_reply

    def _append_user(self, text: str):
        self.chat_history.append(
            {"role": "user", "content": text.strip() + "\n\n"}
        )
        self._trim_history()

    def _append_assistant(self, text: str):
        """
        将助手回复添加到聊天历史，包含以下处理：
        1. 剔除LLM幻觉产生的【刚刚对屏幕的评论】片段
        2. 过滤重复的屏幕评论
        """
        import re
        processed_text = text.strip()
    
        # 仅保留重复屏幕评论的去重逻辑
        if processed_text.startswith("【刚刚对屏幕的评论】"):
            # 提取核心评论内容（剔除前缀+清理空格）
            core_content = re.sub(r"【刚刚对屏幕的评论】\s*", "", processed_text).strip()
            core_content = re.sub(r"\s+", " ", core_content)
        
            # 检查历史中是否已有相同核心内容的屏幕评论
            for msg in self.chat_history:
                if msg["role"] == "assistant":
                    # 提取历史消息的核心内容（同规则）
                    history_core = re.sub(r"【刚刚对屏幕的评论】\s*", "", msg["content"]).strip()
                    history_core = re.sub(r"\s+", " ", history_core)
                    if history_core == core_content:
                        print(f"[去重] 跳过重复的屏幕评论：{core_content[:50]}")
                        return
    
        self.chat_history.append(
            {"role": "assistant", "content": processed_text + "\n\n"}
        )
        self._trim_history()

    def _trim_history(self):
        max_rounds = int(self.sm.get("llm", "history_rounds", default=6))
        max_msgs = max_rounds * 2
        if len(self.chat_history) > max_msgs:
            self.chat_history = self.chat_history[-max_msgs:]

    def _build_chat_messages(self):
        query = self.chat_history[-1]["content"].split("\n", 1)[0].strip() if (self.chat_history and self.chat_history[-1]["role"] == "user") else ""
        knowledge_context = self._retrieve_knowledge(query)
        # 长期记忆：若开关开启则检索并注入「关于该用户的已知信息」
        memory_block = ""
        if self.sm.get("behavior", "long_term_memory_enabled", default=False) and self._long_term_memory:
            try:
                hits_with_scores = self._long_term_memory.search_with_scores(query, top_k=5)
                hits = [c for c, _ in hits_with_scores]
                if hits:
                    memory_block = "\n\n【关于该用户的已知信息】\n" + "\n".join(hits) + "\n（仅作参考，回答须符合角色人设。）"
                    # 调试：打印匹配到的长期记忆及综合得分
                    print("[ChatManager] 长期记忆注入（参考）:", [(c[:50] + ("…" if len(c) > 50 else ""), round(s, 4)) for c, s in hits_with_scores])
            except Exception as e:
                print(f"[ChatManager] 长期记忆检索失败: {e}")
        json_instruction = self._get_json_output_instruction()
        system_content = self._build_persona() + knowledge_context + memory_block + json_instruction
        return [
            {"role": "system", "content": system_content},
            *self.chat_history,
        ]

    def _request_llm(self, messages: list[dict], response_format_json: bool = False) -> str | None:
        """
        发起 LLM 请求。response_format_json 为 True 时（仅聊天场景）才在 payload 中加入
        response_format: json_object；屏幕观察使用情绪标签格式，不传此参数，避免 400。
        """
        provider = self.sm.get("llm", "provider", default="deepseek")
        api_key = self.sm.get("llm", "api_key", default="")
        base_url = self.sm.get("llm", "base_url", default="")
        model = self.sm.get("llm", "model", default="")
        temperature = float(self.sm.get("llm", "temperature", default=1.0))
        max_tokens = int(self.sm.get("llm", "max_tokens", default=512))

        if not api_key or not base_url or not model:
            print("[ChatManager] LLM 配置不完整")
            return None

        base_url = base_url.rstrip("/")

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
        # 仅聊天场景要求 JSON 输出；屏幕观察使用【情绪标签】格式，不设 response_format 避免接口 400
        if response_format_json:
            payload["response_format"] = {"type": "json_object"}

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