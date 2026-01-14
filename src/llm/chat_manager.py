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


class ChatManager:
    def __init__(self, settings_manager, persona_path: str):
        self.sm = settings_manager
        self.persona_path = persona_path

        self.chat_history = []
        self._load_persona()

        # ========== 知识库初始化 ==========
        self.knowledge_dir = Path("src/llm/knowledge")
        self.knowledge_db_dir = Path("src/llm/knowledge_db")
        
        # 初始化索引（异步执行，避免启动卡顿）
        self.lore_index = None
        self.style_index = None
        self.style_sample_history = []  # 记录近期抽取的style内容，降低重复频率
        index_thread = threading.Thread(target=self._init_indices_async)
        index_thread.daemon = True
        index_thread.start()

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
        """异步初始化索引，适配中日双语Embedding（兼容旧版本依赖）"""
        # multilingual-e5-small 原生支持中日双语，移除不兼容的encode_kwargs参数
        embed_model = HuggingFaceEmbedding(
            model_name=self.sm.get(
                "knowledge", "embedding_model", default="intfloat/multilingual-e5-small"
            )
            # 移除encode_kwargs，适配旧版本SentenceTransformer
        )

        self.lore_index = self._load_or_build_index(
            data_dir=Path("src/llm/knowledge/lore"),
            persist_dir=Path("src/llm/knowledge_db/lore"),
            embed_model=embed_model,
            name="Lore",
            is_lore=True
        )
        self.style_index = self._load_or_build_index(
            data_dir=Path("src/llm/knowledge/style"),
            persist_dir=Path("src/llm/knowledge_db/style"),
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
        mtime_file = persist_dir / "data_mtime.json"  # 记录数据文件最后修改时间的文件
        current_mtime = self._get_data_dir_mtime(data_dir)
        need_rebuild = False  # 是否需要重建索引

        # 检查是否需要重建索引
        if persist_dir.exists():
            try:
                # 读取已保存的修改时间
                with open(mtime_file, "r", encoding="utf-8") as f:
                    saved_mtime = json.load(f).get("total_mtime", 0.0)
                # 对比时间：如果当前数据文件修改时间总和不同，说明有更新
                if abs(current_mtime - saved_mtime) > 0.1:  # 浮点精度容错
                    print(f"[ChatManager] {name} 数据文件已更新，将重建索引")
                    need_rebuild = True
            except (FileNotFoundError, json.JSONDecodeError):
                # 无记录文件/文件损坏 → 重建并生成新记录
                print(f"[ChatManager] {name} 无更新记录/记录损坏，将重建索引")
                need_rebuild = True
        else:
            # 无索引目录 → 首次构建
            need_rebuild = True

        # ========== 原有分块逻辑（完全保留） ==========
        if is_lore:
            # Lore：通用剧情/事实分块，优先按空行拆分
            node_parser = SentenceSplitter(
                chunk_size=1000,
                chunk_overlap=150,
                # 仅用单个字符串（旧版本要求）
                paragraph_separator="\n\n",
                separator="。"  # 中文核心句子分隔符（单个字符串）
            )
            reader = SimpleDirectoryReader(
                str(data_dir),
                recursive=True,
                encoding="utf-8",
                # 关键修正：将字符串路径转Path对象后再取name
                file_metadata=lambda file_path: {"file_name": Path(file_path).name}
            )
        else:
            # Style：日文语料分块，适配短台词
            node_parser = SentenceSplitter(
                chunk_size=300,
                chunk_overlap=50,
                # 仅用单个字符串（旧版本要求）
                paragraph_separator="\n",
                separator="、"  # 日文核心句子分隔符（单个字符串）
            )
            reader = SimpleDirectoryReader(
                str(data_dir),
                recursive=True,
                encoding="utf-8"
            )

        # ========== 加载/重建索引逻辑（新增更新检测） ==========
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
        # 确保persist_dir存在（首次构建时创建）
        persist_dir.mkdir(parents=True, exist_ok=True)
        # 写入修改时间记录
        with open(mtime_file, "w", encoding="utf-8") as f:
            json.dump({"total_mtime": current_mtime}, f, ensure_ascii=False)
        
        print(f"[ChatManager] 构建 {name} Index，文档数 {len(documents)}")
        return index

    def _retrieve_knowledge(self, query: str) -> str:
        if not query.strip():
            return ""

        contexts = []
        # 1. Lore：纯向量检索（优化参数适配旧版本）
        if self.lore_index:
            lore_engine = self.lore_index.as_retriever(
                similarity_top_k=8,
                similarity_cutoff=0.2
            )
            lore_nodes = lore_engine.retrieve(query)
            
            unique_nodes = []
            seen_content = set()
            for node in lore_nodes:
                content = node.get_content().strip()
                if content not in seen_content and len(content) > 50:
                    seen_content.add(content)
                    unique_nodes.append(node)

            if unique_nodes:
                contexts.append("【剧情记忆】")
                for n in unique_nodes[:3]:
                    contexts.append(n.get_content().strip())
                    print(f"[RAG-Lore] 匹配结果：{n.score:.3f} | {n.get_content()[:50]}...")

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

    # ---------- 以下所有方法完全保留原有逻辑，无改动 ----------
    def chat(self, user_text: str) -> str | None:
        self._append_user(user_text)
        messages = self._build_chat_messages()
        reply = self._request_llm(messages)
        if reply:
            self._append_assistant(reply)
        return reply

    def send_screen_observation(self, description: str) -> str | None:
        knowledge_context = self._retrieve_knowledge(description)
        system_content = self._build_persona() + knowledge_context
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
            self._append_assistant(f"【刚刚对屏幕的评论】\n{reply}")
        return reply

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
        max_rounds = int(self.sm.get("llm", "history_rounds", default=6))
        max_msgs = max_rounds * 2
        if len(self.chat_history) > max_msgs:
            self.chat_history = self.chat_history[-max_msgs:]

    def _build_chat_messages(self):
        query = self.chat_history[-1]["content"].split("\n", 1)[0].strip() if (self.chat_history and self.chat_history[-1]["role"] == "user") else ""
        knowledge_context = self._retrieve_knowledge(query)
        system_content = self._build_persona() + knowledge_context
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