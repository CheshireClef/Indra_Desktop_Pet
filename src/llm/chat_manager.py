import requests
import os
from pathlib import Path

# 替换原有LangChain导入（第5行开始）
from langchain_community.document_loaders import TextLoader, UnstructuredEPubLoader  # 核心修改
from langchain_text_splitters import RecursiveCharacterTextSplitter  # 分块模块（新版路径）
from langchain_community.embeddings import SentenceTransformerEmbeddings  # 嵌入模型（新版路径）
from langchain_chroma import Chroma  # Chroma集成（新版路径）
from langchain_core.documents import Document


class ChatManager:
    def __init__(self, settings_manager, persona_path: str):
        self.sm = settings_manager
        self.persona_path = persona_path

        self.chat_history = []
        self._load_persona()

        # ========== 新增：知识库初始化 ==========
        self.knowledge_dir = Path("src/llm/knowledge")  # 知识库文件目录
        self.knowledge_db_dir = Path("src/llm/knowledge_db")  # 向量库持久化目录
        self.embeddings = self._init_embeddings()  # 多语言嵌入模型
        self.vector_db = self._init_vector_db()  # 初始化向量库

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

    # ---------- 新增：知识库核心逻辑 ----------
    def _init_embeddings(self):
        """初始化多语言轻量嵌入模型（支持中日文）"""
        model_name = self.sm.get("knowledge", "embedding_model", default="all-MiniLM-L6-v2")
        return SentenceTransformerEmbeddings(model_name=model_name)

    def _load_knowledge_documents(self) -> list[Document]:
        """加载知识库中的TXT/EPUB文件"""
        documents = []
        if not self.knowledge_dir.exists():
            print(f"[ChatManager] 知识库目录不存在：{self.knowledge_dir}")
            return documents

        # 遍历并加载所有TXT/EPUB文件
        for file_path in self.knowledge_dir.glob("*"):
            file_suffix = file_path.suffix.lower()
            try:
                if file_suffix == ".txt":
                    loader = TextLoader(str(file_path), encoding="utf-8")
                    docs = loader.load()
                    documents.extend(docs)
                    print(f"[ChatManager] 加载TXT文档：{file_path.name}")
                elif file_suffix == ".epub":
                    # 兼容EPUB加载（自动提取文本）
                    loader = UnstructuredEPubLoader(str(file_path), encoding="utf-8")
                    docs = loader.load()
                    documents.extend(docs)
                    print(f"[ChatManager] 加载EPUB文档：{file_path.name}")
            except Exception as e:
                print(f"[ChatManager] 加载文档失败 {file_path.name}：{e}")
        return documents

    def _init_vector_db(self):
        """初始化向量库（首次构建，后续直接加载）"""
        # 检查向量库是否已持久化，避免重复构建
        if self.knowledge_db_dir.exists() and len(list(self.knowledge_db_dir.glob("*.bin"))) > 0:
            vector_db = Chroma(
                persist_directory=str(self.knowledge_db_dir),
                embedding_function=self.embeddings
            )
            print(f"[ChatManager] 加载现有向量库：{self.knowledge_db_dir}")
            return vector_db

        # 加载文档并分块（适配中日文分隔符）
        documents = self._load_knowledge_documents()
        if not documents:
            print("[ChatManager] 知识库无有效文档，跳过向量库构建")
            return None

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=int(self.sm.get("knowledge", "chunk_size", default=500)),
            chunk_overlap=int(self.sm.get("knowledge", "chunk_overlap", default=50)),
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", "、", ".", "!", "?", ";", ","]  # 中日文通用分隔符
        )
        split_docs = text_splitter.split_documents(documents)

        # 构建并持久化向量库
        vector_db = Chroma.from_documents(
            documents=split_docs,
            embedding=self.embeddings,
            persist_directory=str(self.knowledge_db_dir)
        )
        print(f"[ChatManager] 知识库构建完成，共处理 {len(split_docs)} 个文档块")
        return vector_db

    def _retrieve_knowledge(self, query: str) -> str:
        """检索知识库（返回相关文本，无结果则返回空）"""
        if not self.vector_db or not query.strip():
            return ""

        # 检索配置（可通过settings调整）
        top_k = int(self.sm.get("knowledge", "top_k", default=3))
        similarity_threshold = float(self.sm.get("knowledge", "similarity_threshold", default=0.35))

        # 相似性检索（过滤低相似度结果）
        results = self.vector_db.similarity_search_with_score(query, k=top_k)
        print("\n【RAG 原始命中结果】") #调试用代码-开始
        for doc, score in results:
            print("{:.3f} | {}".format(
                score,
                doc.page_content[:80].replace("\n", " ")
            ))
                #调试用代码-结束

        relevant_docs = [doc for doc, score in results if score >= similarity_threshold]
        if not relevant_docs:
            print("【RAG】命中但全部被 similarity_threshold 过滤") #调试代码
            return ""

        # 拼接检索结果（不改动原有prompt，仅追加参考资料）
        knowledge_context = "\n\n【参考资料】\n"
        for i, doc in enumerate(relevant_docs, 1):
            knowledge_context += f"{i}. {doc.page_content.strip()}\n\n"
        print("【RAG】最终注入 system prompt") #调试代码
        return knowledge_context

    # ---------- Public: Chat（原有逻辑，仅调整上下文构建） ----------
    def chat(self, user_text: str) -> str | None:
        self._append_user(user_text)
        messages = self._build_chat_messages()  # 内部已集成知识库检索
        reply = self._request_llm(messages)
        if reply:
            self._append_assistant(reply)
        return reply

    # ---------- Public: Screen Observation（微调上下文，无文案改动） ----------
    def send_screen_observation(self, description: str) -> str | None:
        """
        ⚠️ 屏幕评论：
        - 不读取 chat_history
        - 只基于 persona + 当前截图描述
        """
        # 新增：基于截图描述检索知识库
        knowledge_context = self._retrieve_knowledge(description)
        system_content = self._build_persona() + knowledge_context  # 追加参考资料，不改动原有persona

        messages = [
            {"role": "system", "content": system_content},
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
            self._append_assistant(f"【刚刚对屏幕的评论】\n{reply}")
        return reply

    # ---------- History（原有逻辑，无改动） ----------
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
        """微调：追加知识库检索结果到system prompt"""
        # 提取最后一条用户消息作为检索关键词
        query = self.chat_history[-1]["content"].strip() if (self.chat_history and self.chat_history[-1]["role"] == "user") else ""
        knowledge_context = self._retrieve_knowledge(query)
        # 原有persona + 参考资料（不改动原有prompt文案）
        system_content = self._build_persona() + knowledge_context
        return [
            {"role": "system", "content": system_content},
            *self.chat_history,
        ]

    # ---------- LLM（原有逻辑，无改动） ----------
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