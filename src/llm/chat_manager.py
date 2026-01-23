from ast import pattern
from pydoc import text
from pyexpat.errors import messages
import requests
import os
import random
import threading
import json  # 新增：用于读写文件修改时间记录
from pathlib import Path
from llama_index.core.schema import Document
from llama_index.core import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    StorageContext,
    load_index_from_storage,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from soupsieve import match
from sympy import re
from utils import resource_path

class ChatManager:
    VALID_EMOTION_TAGS = ["喜爱", "开心", "干杯", "疑问", "伤心", "无聊", "尴尬", "生气", "平常"]
    EMOTION_TAG_FORMAT = "【{}】"  # 标签固定包裹格式
    # 新增：通用情绪标签 Prompt 生成方法（唯一标准）
    def _get_emotion_tag_prompt(self) -> str:
        """
        生成统一的情绪标签输出要求 Prompt，所有场景共用这一套规则
        规则优先级：完整的5条细则（以屏幕观察场景的规则为准）
        """
        return (
            "\n\n【情绪标签输出要求】"
            "1. 请严格分析回复内容的情绪倾向，哪怕只有轻微的情绪（如一点点开心、轻微疑问），也必须选择对应情绪标签，禁止滥用「平常」；"
            "2. 仅当回复内容完全无任何情绪倾向（纯客观陈述、无主观情感）时，才能选择【平常】；"
            "3. 标签必须从以下列表中选择：{}，格式为【标签名】，必须放在回复最后一行，仅含标签无其他内容；"
            "4. 若回复的内容适合【平常】标签，但包含饮酒的情节，请优先选择【干杯】标签；"
            "5. 标签仅用于后台统计，不要体现在对话内容中。"
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

        # ========== 知识库初始化 ==========
        self.knowledge_dir = Path(resource_path("src/llm/knowledge"))
        self.knowledge_db_dir = Path(resource_path("src/llm/knowledge_db"))
        
        # 初始化索引（异步执行，避免启动卡顿）
        self.lore_index = None
        self.style_index = None
        self.style_sample_history = []  # 记录近期抽取的style内容，降低重复频率
        index_thread = threading.Thread(target=self._init_indices_async)
        index_thread.daemon = True
        index_thread.start()

        # ========== 新增：提取并剥离情绪标签 ==========
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
    
    # ---------- Persona（原有逻辑，无改动） ----------
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
    
    def _init_indices_async(self):
        """异步初始化索引，强制使用本地gte-multilingual-base离线模型"""
        # 强制开启离线模式，禁止任何联网行为
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["HF_DATASETS_OFFLINE"] = "1"

        # 本地模型目录（固定路径）
        local_model_dir = Path(resource_path("models/gte-multilingual-base"))
        
        # 校验本地模型目录是否存在且有内容
        if not local_model_dir.exists():
            raise FileNotFoundError(f"本地模型目录不存在：{local_model_dir}")
        if not list(local_model_dir.glob("*.bin")) and not list(local_model_dir.glob("*.safetensors")):
            raise FileNotFoundError(f"本地模型目录 {local_model_dir} 中未找到模型权重文件")
        
        # 确认配置文件和自定义代码文件存在（参考save_pretrained_alibaba_model逻辑）
        required_files = ["config.json", "modeling.py", "configuration.py"]
        missing_files = [f for f in required_files if not (local_model_dir / f).exists()]
        if missing_files:
            raise FileNotFoundError(f"本地模型目录缺少必要文件：{missing_files}，请先运行save_pretrained_alibaba_model下载完整模型")

        # 加载本地模型（强制trust_remote_code=True，移除device参数）
        print(f"[ChatManager] 使用本地多语言模型（离线模式）：{local_model_dir}")
        embed_model = HuggingFaceEmbedding(
            model_name=str(local_model_dir),
            trust_remote_code=True,  # 强制开启，适配阿里模型自定义代码
            # 关键修改：移除model_kwargs={"device": "cpu"}，改为后续手动设置设备
            embed_batch_size=16,  # 可选：添加批次大小配置，提升效率
        )
    
        # 手动将模型移动到CPU（解决device参数不兼容问题）
        try:
            import torch
            embed_model._model = embed_model._model.to("cpu")
            print(f"[ChatManager] 模型已手动移动到CPU设备")
        except Exception as e:
            print(f"[ChatManager] 手动设置模型设备失败（非致命）：{e}")
    
        self.lore_index = self._load_or_build_index(
            data_dir=Path(resource_path("src/llm/knowledge/lore")),
            persist_dir=Path(resource_path("src/llm/knowledge_db/lore")),
            embed_model=embed_model,
            name="Lore",
            is_lore=True
        )
        self.style_index = self._load_or_build_index(
            data_dir=Path(resource_path("src/llm/knowledge/style")),
            persist_dir=Path(resource_path("src/llm/knowledge_db/style")),
            embed_model=embed_model,
            name="Style",
            is_lore=False
        )
        
    def _get_data_dir_mtime(self, data_dir: Path) -> float:
        """辅助函数：计算数据目录下所有文件的最后修改时间总和（用于检测更新）"""
        total_mtime = 0.0
        for file in data_dir.rglob("*"):
            if file.is_file() and not file.name.startswith("."):  # 跳过隐藏文件
                try:
                    total_mtime += os.path.getmtime(file)
                except Exception:
                    continue
        return total_mtime

    def _load_or_build_index(self, data_dir: Path, persist_dir: Path, embed_model, name: str, is_lore: bool = False):
        if not data_dir.exists():
            print(f"[ChatManager] {name} 目录不存在，跳过")
            return None

        # ========== 新增：检测数据文件更新 ==========
        mtime_file = persist_dir / "data_mtime.json"
        current_mtime = self._get_data_dir_mtime(data_dir)
        need_rebuild = False

        if persist_dir.exists():
            try:
                with open(mtime_file, "r", encoding="utf-8") as f:
                    saved_mtime = json.load(f).get("total_mtime", 0.0)
                if abs(current_mtime - saved_mtime) > 0.1:
                    print(f"[ChatManager] {name} 数据文件已更新，将重建索引")
                    need_rebuild = True
            except (FileNotFoundError, json.JSONDecodeError):
                print(f"[ChatManager] {name} 无更新记录/记录损坏，将重建索引")
                need_rebuild = True
        else:
            need_rebuild = True

        # ========== 优化分块策略（核心改进）==========
        if is_lore:
            # Lore：针对长篇故事优化
            node_parser = SentenceSplitter(
                chunk_size=800,      # 调小chunk，提高精度（原1000）
                chunk_overlap=200,   # 增大overlap，保留上下文（原150）
                paragraph_separator="\n\n",
                separator="。"
            )
            reader = SimpleDirectoryReader(
                str(data_dir),
                recursive=True,
                encoding="utf-8",
                # 🔥 关键改进：标记文件类型
                file_metadata=lambda file_path: {
                    "file_name": Path(file_path).name,
                    "file_type": "facts" if Path(file_path).name.endswith(".facts.txt") else "story"
                }
            )
        else:
            # Style：保持原有策略
            node_parser = SentenceSplitter(
                chunk_size=300,
                chunk_overlap=50,
                paragraph_separator="\n",
                separator="。"
            )
            reader = SimpleDirectoryReader(
                str(data_dir),
                recursive=True,
                encoding="utf-8"
            )

        # ========== 加载/重建索引逻辑（新增更新检测）==========
        if persist_dir.exists() and not need_rebuild:
            try:
                storage = StorageContext.from_defaults(persist_dir=str(persist_dir))
                index = load_index_from_storage(storage, embed_model=embed_model)
                print(f"[ChatManager] 加载已有 {name} Index")
                return index
            except Exception as e:
                print(f"[ChatManager] 加载{name} Index失败：{e}，将重建")
                need_rebuild = True

        # 重建索引（首次构建/数据更新/加载失败）
        documents = reader.load_data()
        if not documents:
            print(f"[ChatManager] {name} 目录为空")
            return None

        index = VectorStoreIndex.from_documents(
            documents,
            embed_model=embed_model,
            transformations=[node_parser],
            show_progress=True
        )

        # 保存索引 + 记录当前数据文件修改时间
        index.storage_context.persist(persist_dir=str(persist_dir))
        persist_dir.mkdir(parents=True, exist_ok=True)
        with open(mtime_file, "w", encoding="utf-8") as f:
            json.dump({"total_mtime": current_mtime}, f, ensure_ascii=False)
        
        print(f"[ChatManager] 构建 {name} Index，文档数 {len(documents)}")
        return index

    def _retrieve_knowledge(self, query: str) -> str:
        if not query.strip():
            return ""

        contexts = []
        
        # 1. Lore：混合检索策略（优化后）
        if self.lore_index:
            # 🔥 策略1：向量检索（语义相似）
            lore_engine = self.lore_index.as_retriever(
                similarity_top_k=12,     # 增加召回数量（原8）
                similarity_cutoff=0.15   # 降低阈值，提高召回（原0.2）
            )
            lore_nodes = lore_engine.retrieve(query)
            
            # 🔥 策略2：优先选择facts文件的结果
            facts_nodes = []
            story_nodes = []
            
            for node in lore_nodes:
                metadata = node.metadata or {}
                file_type = metadata.get("file_type", "story")
                
                if file_type == "facts":
                    facts_nodes.append(node)
                else:
                    story_nodes.append(node)
            
            # 🔥 策略3：智能组合（facts提供关键信息，story提供细节）
            selected_nodes = []
            
            # 优先取facts节点（结构化，准确度高）
            for node in facts_nodes[:2]:
                content = node.get_content().strip()
                if len(content) > 30:
                    selected_nodes.append(node)
                    print(f"[RAG-Lore-Facts] 匹配结果：{node.score:.3f} | {content[:50]}...")
            
            # 补充story节点（提供细节）
            for node in story_nodes[:2]:
                content = node.get_content().strip()
                if len(content) > 50:
                    selected_nodes.append(node)
                    print(f"[RAG-Lore-Story] 匹配结果：{node.score:.3f} | {content[:50]}...")
            
            # 去重并拼接
            if selected_nodes:
                contexts.append("【剧情记忆】")
                seen_content = set()
                for n in selected_nodes:
                    content = n.get_content().strip()
                    if content not in seen_content:
                        seen_content.add(content)
                        contexts.append(content)

        # 2. Style：降低重复频率（核心逻辑保留）
        if self.style_index:
            try:
                all_style_nodes = list(self.style_index.docstore.docs.values())
                all_style_contents = []
                for node in all_style_nodes:
                    content = node.get_content().strip()
                    if 20 <= len(content) <= 300:
                        all_style_contents.append(content)

                if all_style_contents:
                    candidate_contents = [c for c in all_style_contents if c not in self.style_sample_history]
                    if not candidate_contents:
                        self.style_sample_history = []
                        candidate_contents = all_style_contents

                    sample_count = random.randint(1, min(3, len(candidate_contents)))
                    sample_contents = random.sample(candidate_contents, sample_count)

                    self.style_sample_history.extend(sample_contents)
                    self.style_sample_history = self.style_sample_history[-15:]
                    
                    contexts.append("【语料参考】")
                    contexts.extend(sample_contents)
            except Exception as e:
                print(f"[ChatManager] 随机采样Style失败：{e}")

        if not contexts:
            return ""

        return "\n\n".join(contexts) + "\n\n"

    def _extract_general_keywords(self, query: str) -> list[str]:
        """通用关键词提取（无硬编码）"""
        keywords = []
        for word in query.split():
            if len(word) > 1:
                keywords.append(word)
        return list(dict.fromkeys(keywords))[:8]
    
    # 新增：带情绪标签返回的聊天方法
    def chat_with_tag(self, user_text: str) -> tuple[str | None, str]:
        self._append_user(user_text)
        messages = self._build_chat_messages()
        reply = self._request_llm(messages)
        if reply:
            import re
            
            # ========== 关键修复：剔除从第一个【刚刚对屏幕的评论】开始的所有内容 ==========
            # 策略：找到第一个【刚刚对屏幕的评论】的位置，直接截断后面所有内容
            hallucination_marker = '【刚刚对屏幕的评论】'
            
            if hallucination_marker in reply:
                # 找到第一个标记的位置，保留之前的内容
                first_marker_pos = reply.find(hallucination_marker)
                reply_without_hallucination = reply[:first_marker_pos].strip()
                print(f"[过滤LLM幻觉] 检测到幻觉标记，已截断")
                print(f"  原始长度: {len(reply)} | 清理后长度: {len(reply_without_hallucination)}")
            else:
                reply_without_hallucination = reply
            
            # 从清理后的内容中提取情绪标签
            clean_reply, emotion_tag = self._extract_and_strip_emotion_tag(reply_without_hallucination)
        
            # 保存清理后的内容到聊天历史
            self._append_assistant(clean_reply)
        
            print(f"[LLM-聊天回复] 情绪标签：{emotion_tag} | 内容预览：{clean_reply[:50]}...")
            return clean_reply, emotion_tag
        return None, "平常"

    # ---------- 以下所有方法完全保留原有逻辑，无改动 ----------
    def chat(self, user_text: str) -> str | None:
        pure_reply, _ = self.chat_with_tag(user_text)
        return pure_reply

    # 新增：带情绪标签返回的屏幕观察方法
    def send_screen_observation_with_tag(self, description: str) -> tuple[str | None, str]:
        knowledge_context = self._retrieve_knowledge(description)
        # 替换：删除原有重复的 Prompt，调用通用方法
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
            # ========== 第一步：先提取情绪标签（原始reply） ==========
            pure_reply, emotion_tag = self._extract_and_strip_emotion_tag(reply)
        
            # ========== 第二步：剔除幻觉内容（仅针对非屏幕观察场景） ==========
            # 注意：屏幕观察场景本身需要保留【刚刚对屏幕的评论】前缀，所以跳过剔除
            if not pure_reply.startswith("【刚刚对屏幕的评论】"):
                import re
                screen_comment_pattern = r'\s*【刚刚对屏幕的评论】.*'
                pure_reply = re.sub(
                    screen_comment_pattern,
                    '',
                    pure_reply,
                    flags=re.DOTALL
                ).strip()
        
            # ========== 第三步：拼接前缀并保存历史 ==========
            assistant_msg = f"【刚刚对屏幕的评论】\n{pure_reply}" if pure_reply else ""
            self._append_assistant(assistant_msg)
        
            print(f"[LLM-屏幕观察] 情绪标签：{emotion_tag} | 内容预览：{pure_reply[:50]}...")
            return pure_reply, emotion_tag
    
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
        # 替换：删除原有简化版 Prompt，调用通用方法
        emotion_instruction = self._get_emotion_tag_prompt()
        system_content = self._build_persona() + knowledge_context + emotion_instruction
        return [
            {"role": "system", "content": system_content},
            *self.chat_history,
        ]

    def _request_llm(self, messages: list[dict]) -> str | None:
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