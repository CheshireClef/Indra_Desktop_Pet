"""
对话管理模块
负责处理与 LLM 的交互，包括：
1. 构建 Prompt (System Persona + User Input)
2. 调用 RAG 检索知识库 (KnowledgeBase)
3. 提取和处理情绪标签 (Emotion Tag) / JSON 结构化输出
4. 管理对话历史 (History)
"""
import copy
import re
from collections import deque

from PySide6.QtCore import QObject, QTimer

from utils import resource_path
from .knowledge_base import KnowledgeBase
from .long_term_memory import LongTermMemory
from llm.clients.text_sanitize import strip_reasoning_artifacts
from llm.memory_extract_sampling import MemoryRoundBuffer
from llm.pipelines.chat_pipeline import (
    append_json_retry_to_messages,
    get_json_output_instruction,
    invoke_chat_with_policy,
    parse_chat_raw,
    should_use_markdown_json_instruction,
)
from llm.pipelines.chat_output_strategy import is_deepseek_chat_model

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
            "5. 标签仅用于后台统计，不要体现在对话内容中；"
            "6. 禁止输出思考过程、think 围栏或 chain-of-thought，只输出角色对用户说的评论正文与末尾情绪标签。"
        ).format(','.join(self.VALID_EMOTION_TAGS))

    def __init__(self, settings_manager=None, persona_path: str = ""):
        if settings_manager:
            self.sm = settings_manager
        else:
            from settings_manager import SettingsManager
            self.sm = SettingsManager.get_instance()
            
        self.persona_path = resource_path(persona_path)

        self.chat_history = []
        self._load_persona()

        # 聊天记忆后台抽取：用户聊天轮缓冲 + FIFO 队列（不含屏幕评论）
        self._memory_round_buffer = MemoryRoundBuffer()
        self._memory_extract_queue: deque[tuple[list[dict], int, int, int]] = deque()
        self._memory_extract_batch_seq = 0
        self._memory_chat_round_serial = 0
        self._memory_extract_worker = None
        # 主线程调度桥（ChatWorker 子线程入队时经 QTimer 投递到此对象所在线程）
        self._extract_ui_bridge = QObject()
        # 最近一次 LLM 调用的 API 级思考链（与正文分离，供 UI 展示）
        self._last_llm_reasoning: str | None = None

        # ========== 知识库初始化 ==========
        self.knowledge_base = KnowledgeBase()
        # 长期记忆：整理合并走记忆专用模型 API
        from llm.memory_extract import request_memory_llm_json

        self._long_term_memory = LongTermMemory(
            self.knowledge_base,
            merge_llm_caller=lambda msgs: request_memory_llm_json(self.sm, msgs),
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

        reply_processed = strip_reasoning_artifacts(reply)
        if not reply_processed:
            return "", "平常"
        
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

    def _max_reply_chars(self) -> int:
        return int(self.sm.get("llm", "max_reply_chars", default=800))

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
        """构建完整的 System Prompt，包含用户昵称与语言约束"""
        user_name = self.sm.get("user", "display_name", default="主人")
        return (
            f"{self.base_persona}\n\n"
            f"你必须始终称呼用户为「{user_name}」，不要使用其他称呼。\n"
            "【语言要求】无论用户输入何种语言，你回复的正文必须使用简体中文。"
            "禁止用日文、英文或其他语言作答（角色名、游戏专有名词可保留原文）。"
            "人设资料与语音参考中的日文仅用于理解语气，不得照搬日文句式或整段日文回复。"
        )
    
    def _retrieve_knowledge(self, query: str) -> str:
        """检索知识库，返回相关片段；失败时降级为空上下文，不中断聊天。"""
        try:
            return self.knowledge_base.retrieve(query) or ""
        except Exception as e:
            print(f"[ChatManager] 知识库检索失败，已跳过 RAG: {e}")
            return ""
    
    # 带情绪标签返回的聊天方法；返回 (reply, emotion, error_message, reasoning)
    def chat_with_tag(
        self, user_text: str
    ) -> tuple[str | None, str, str | None, str | None]:
        self._last_llm_reasoning = None
        self._append_user(user_text)
        binding = self.sm.get_chat_binding()
        cache = self.sm.get_capability_cache(
            binding.get("connection_id", "default"),
            binding.get("model", ""),
        ) or {}
        max_chars = self._max_reply_chars()

        def _call(msgs: list[dict], *, rf: bool) -> str | None:
            return self._request_llm(msgs, response_format_json=rf)

        base_url = binding.get("base_url") or ""
        model = binding.get("model") or ""
        vendor = binding.get("vendor")
        use_json_system = not is_deepseek_chat_model(base_url, model, vendor=vendor)

        messages = self._build_chat_messages(use_json=use_json_system)
        reply_raw, strategy = invoke_chat_with_policy(
            messages=messages,
            output_mode=binding.get("output_mode", "auto"),
            cached_json_mode=cache.get("json_mode"),
            llm_caller=lambda m: _call(m, rf=False),
            llm_caller_json_rf=lambda m: _call(m, rf=True),
            rebuild_messages_json=lambda _m: self._build_chat_messages(use_json=True),
            rebuild_messages_natural=lambda _m: self._build_chat_messages(use_json=False),
            base_url=base_url,
            model=model,
            vendor=vendor,
        )
        if not (reply_raw or "").strip():
            print("[LLM-聊天] API 返回空")
            return None, "平常", "LLM 返回了空回复", None

        parsed = parse_chat_raw(reply_raw, strategy=strategy, max_reply_chars=max_chars)
        reasoning = self._last_llm_reasoning

        # JSON 模式解析失败：自动重试 1 次（DeepSeek 改走自然语言，不再重试 JSON）
        if not parsed.ok and strategy != "natural":
            print(f"[LLM-聊天] 解析失败 ({parsed.parse_mode})，重试 1 次…")
            if is_deepseek_chat_model(base_url, model, vendor=vendor):
                retry_msgs = self._build_chat_messages(use_json=False)
                reply_raw2, strategy2 = invoke_chat_with_policy(
                    messages=retry_msgs,
                    output_mode="natural_only",
                    cached_json_mode="natural_only",
                    llm_caller=lambda m: _call(m, rf=False),
                    llm_caller_json_rf=lambda m: _call(m, rf=True),
                    rebuild_messages_json=lambda _m: self._build_chat_messages(use_json=True),
                    rebuild_messages_natural=lambda _m: self._build_chat_messages(
                        use_json=False
                    ),
                    base_url=base_url,
                    model=model,
                    vendor=vendor,
                )
            else:
                retry_msgs = append_json_retry_to_messages(messages)
                reply_raw2, strategy2 = invoke_chat_with_policy(
                    messages=retry_msgs,
                    output_mode="json_preferred",
                    cached_json_mode=cache.get("json_mode") or "response_format",
                    llm_caller=lambda m: _call(m, rf=False),
                    llm_caller_json_rf=lambda m: _call(m, rf=True),
                    rebuild_messages_json=lambda _m: append_json_retry_to_messages(
                        self._build_chat_messages(use_json=True)
                    ),
                    rebuild_messages_natural=lambda _m: self._build_chat_messages(
                        use_json=False
                    ),
                    base_url=base_url,
                    model=model,
                    vendor=vendor,
                )
            if (reply_raw2 or "").strip():
                parsed = parse_chat_raw(
                    reply_raw2, strategy=strategy2, max_reply_chars=max_chars
                )
                strategy = strategy2

        if not parsed.ok or not (parsed.reply or "").strip():
            err = (
                "模型回复格式异常（可能含残缺 JSON 或过长幻觉），本轮未记入对话上下文。"
                "请重试或缩短对话轮数。"
            )
            print(f"[LLM-聊天] 最终解析失败 | mode={parsed.parse_mode}")
            return None, "平常", err, reasoning

        self._append_assistant(parsed.reply)
        self._schedule_memory_extract()
        print(
            f"[LLM-聊天回复] mode={parsed.parse_mode} | 情绪：{parsed.emotion} | "
            f"预览：{parsed.reply[:50]}..."
        )
        return parsed.reply, parsed.emotion, None, reasoning

    def chat(self, user_text: str) -> str | None:
        pure_reply, _, _, _ = self.chat_with_tag(user_text)
        return pure_reply

    def _extract_memory_from_screen_description(self, description: str) -> None:
        """屏幕描述走记忆专用模型与 memory_extract 通道（与聊天 JSON 分离）。"""
        if not (description or "").strip() or not self._long_term_memory:
            return
        from llm.memory_extract import run_memory_extract

        screen_slice = [
            {
                "role": "user",
                "content": (
                    "【屏幕观察】以下是对用户电脑屏幕的客观描述。"
                    "请判断是否有关于用户本人的、值得长期记录的信息。\n"
                    + (description or "").strip()[:2000]
                ),
            },
            {
                "role": "assistant",
                "content": "好的，我会根据屏幕描述判断是否需要记录长期记忆。",
            },
        ]
        try:
            items = run_memory_extract(screen_slice, self.sm)
            written = 0
            for content, topic in items:
                if self._long_term_memory.add_or_update(content, topic=topic):
                    written += 1
            if written:
                print(f"[长期记忆-屏幕] 写入 {written} 条")
        except Exception as e:
            print(f"[ChatManager] 屏幕描述记忆抽取失败: {e}")

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

    def _build_chat_messages(self, *, use_json: bool = True):
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
        if use_json:
            conn_id = (self.sm.get_chat_binding() or {}).get("connection_id", "default")
            model = (self.sm.get_chat_binding() or {}).get("model", "")
            cache = self.sm.get_capability_cache(conn_id, model) or {}
            use_fence = should_use_markdown_json_instruction(cache.get("json_mode"))
            suffix = get_json_output_instruction(
                self.VALID_EMOTION_TAGS,
                use_markdown_fence=use_fence,
            )
        else:
            suffix = self._get_emotion_tag_prompt()
        system_content = self._build_persona() + knowledge_context + memory_block + suffix
        return [
            {"role": "system", "content": system_content},
            *self.chat_history,
        ]

    def _schedule_memory_extract(self) -> None:
        """
        用户聊天成功后：向 buffer 追加本轮，按 N 轮连续批次入队，主线程顺序执行 Worker。
        """
        QTimer.singleShot(0, self._extract_ui_bridge, self._schedule_memory_extract_on_main)

    def _schedule_memory_extract_on_main(self) -> None:
        if not self.sm.get("behavior", "long_term_memory_enabled", default=False):
            return
        if not self._long_term_memory:
            return
        if len(self.chat_history) < 2:
            return

        user_msg = self.chat_history[-2]
        assistant_msg = self.chat_history[-1]
        if user_msg.get("role") != "user" or assistant_msg.get("role") != "assistant":
            return

        self._memory_round_buffer.append_round(user_msg, assistant_msg)
        self._memory_chat_round_serial += 1

        n = self.sm.get_memory_extract_context_rounds()
        while self._memory_round_buffer.pending_count() >= n:
            history_slice = self._memory_round_buffer.pending_slice(n)
            if not history_slice:
                break
            pending_before = self._memory_round_buffer.pending_count()
            round_end = self._memory_chat_round_serial - pending_before + n
            round_start = round_end - n + 1
            self._memory_extract_batch_seq += 1
            batch_id = self._memory_extract_batch_seq
            self._memory_extract_queue.append(
                (history_slice, batch_id, round_start, round_end)
            )
            self._memory_round_buffer.commit(n)
            print(
                f"[MemoryExtract] 入队批次 #{batch_id}（第 {round_start}–{round_end} 轮用户对话，"
                f"共 {len(history_slice)} 条，不含屏幕评论）"
            )

        self._process_memory_extract_queue()

    def _enqueue_memory_extract(
        self,
        history_slice: list[dict],
        batch_id: int,
        round_start: int,
        round_end: int,
    ) -> None:
        """入队并在主线程唤醒 queue processor（供测试或扩展）。"""
        self._memory_extract_queue.append(
            (copy.deepcopy(history_slice), batch_id, round_start, round_end)
        )
        self._process_memory_extract_queue()

    def _process_memory_extract_queue(self) -> None:
        """FIFO：当前无 Worker 运行时取下一批启动。"""
        if self._memory_extract_worker is not None and self._memory_extract_worker.isRunning():
            return
        if not self._memory_extract_queue:
            return

        history_slice, batch_id, round_start, round_end = self._memory_extract_queue.popleft()
        from workers.memory_extract_worker import MemoryExtractWorker

        worker = MemoryExtractWorker(
            settings_manager=self.sm,
            long_term_memory=self._long_term_memory,
            history_slice=history_slice,
            batch_id=batch_id,
        )
        worker.finished.connect(self._on_memory_extract_finished)
        worker.error.connect(self._on_memory_extract_error)
        self._memory_extract_worker = worker
        print(
            f"[MemoryExtract] 开始抽取批次 #{batch_id}（第 {round_start}–{round_end} 轮）"
        )
        worker.start()

    def _on_memory_extract_finished(self, written_count: int, batch_id: int) -> None:
        if written_count:
            print(
                f"[ChatManager] 后台记忆抽取批次 #{batch_id} 完成，写入 {written_count} 条"
            )
        else:
            print(f"[ChatManager] 后台记忆抽取批次 #{batch_id} 完成，无新写入")
        self._process_memory_extract_queue()

    def _on_memory_extract_error(self, msg: str, batch_id: int) -> None:
        print(f"[ChatManager] 后台记忆抽取批次 #{batch_id} 失败: {msg}")
        self._process_memory_extract_queue()

    def _request_llm(self, messages: list[dict], response_format_json: bool = False) -> str | None:
        result = self._request_llm_result(messages, response_format_json=response_format_json)
        return result.content_or_none() if result else None

    def _request_llm_result(
        self, messages: list[dict], response_format_json: bool = False
    ):
        """
        发起 LLM 请求。经 ModelService 统一 OpenAI 兼容客户端；
        response_format_json 为 True 时尝试 json_object，不支持时客户端内降级重试。
        """
        from llm.model_service import ModelService

        binding = self.sm.get_chat_binding()
        if not binding.get("model") or not binding.get("base_url"):
            print("[ChatManager] LLM 配置不完整")
            return None
        api_key = binding.get("api_key") or ""
        from llm.providers.registry import requires_api_key

        if requires_api_key(binding.get("vendor", "")) and not api_key:
            print("[ChatManager] LLM API 密钥为空")
            return None

        ms = ModelService.get_instance(self.sm)
        parsed = ms.chat_completions(
            messages,
            temperature=float(binding.get("temperature", 1.0)),
            max_tokens=int(binding.get("max_tokens", 512)),
            response_format_json=response_format_json,
        )
        if parsed and parsed.has_reasoning:
            self._last_llm_reasoning = parsed.reasoning
        return parsed