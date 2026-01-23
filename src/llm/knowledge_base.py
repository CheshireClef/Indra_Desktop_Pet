import os
import json
import random
import threading
from pathlib import Path
from llama_index.core import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    StorageContext,
    load_index_from_storage,
)
from llama_index.core.schema import Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from utils import resource_path

class KnowledgeBase:
    def __init__(self):
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
            print(f"[KnowledgeBase] 本地模型目录不存在：{local_model_dir}")
            return
        if not list(local_model_dir.glob("*.bin")) and not list(local_model_dir.glob("*.safetensors")):
            print(f"[KnowledgeBase] 本地模型目录 {local_model_dir} 中未找到模型权重文件")
            return
        
        # 确认配置文件和自定义代码文件存在
        required_files = ["config.json", "modeling.py", "configuration.py"]
        missing_files = [f for f in required_files if not (local_model_dir / f).exists()]
        if missing_files:
            print(f"[KnowledgeBase] 本地模型目录缺少必要文件：{missing_files}")
            return

        # 加载本地模型
        print(f"[KnowledgeBase] 使用本地多语言模型（离线模式）：{local_model_dir}")
        try:
            embed_model = HuggingFaceEmbedding(
                model_name=str(local_model_dir),
                trust_remote_code=True,
                embed_batch_size=16,
            )
            
            # 手动将模型移动到CPU
            import torch
            embed_model._model = embed_model._model.to("cpu")
            print(f"[KnowledgeBase] 模型已手动移动到CPU设备")
        except Exception as e:
            print(f"[KnowledgeBase] 模型加载失败：{e}")
            return

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
        """辅助函数：计算数据目录下所有文件的最后修改时间总和"""
        total_mtime = 0.0
        for file in data_dir.rglob("*"):
            if file.is_file() and not file.name.startswith("."):
                try:
                    total_mtime += os.path.getmtime(file)
                except Exception:
                    continue
        return total_mtime

    def _load_or_build_index(self, data_dir: Path, persist_dir: Path, embed_model, name: str, is_lore: bool = False):
        if not data_dir.exists():
            print(f"[KnowledgeBase] {name} 目录不存在，跳过")
            return None

        mtime_file = persist_dir / "data_mtime.json"
        current_mtime = self._get_data_dir_mtime(data_dir)
        need_rebuild = False

        if persist_dir.exists():
            try:
                with open(mtime_file, "r", encoding="utf-8") as f:
                    saved_mtime = json.load(f).get("total_mtime", 0.0)
                if abs(current_mtime - saved_mtime) > 0.1:
                    print(f"[KnowledgeBase] {name} 数据文件已更新，将重建索引")
                    need_rebuild = True
            except (FileNotFoundError, json.JSONDecodeError):
                print(f"[KnowledgeBase] {name} 无更新记录/记录损坏，将重建索引")
                need_rebuild = True
        else:
            need_rebuild = True

        if is_lore:
            node_parser = SentenceSplitter(
                chunk_size=800,
                chunk_overlap=200,
                paragraph_separator="\n\n",
                separator="。"
            )
            reader = SimpleDirectoryReader(
                str(data_dir),
                recursive=True,
                encoding="utf-8",
                file_metadata=lambda file_path: {
                    "file_name": Path(file_path).name,
                    "file_type": "facts" if Path(file_path).name.endswith(".facts.txt") else "story"
                }
            )
        else:
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

        if persist_dir.exists() and not need_rebuild:
            try:
                storage = StorageContext.from_defaults(persist_dir=str(persist_dir))
                index = load_index_from_storage(storage, embed_model=embed_model)
                print(f"[KnowledgeBase] 加载已有 {name} Index")
                return index
            except Exception as e:
                print(f"[KnowledgeBase] 加载{name} Index失败：{e}，将重建")
                need_rebuild = True

        documents = reader.load_data()
        if not documents:
            print(f"[KnowledgeBase] {name} 目录为空")
            return None

        index = VectorStoreIndex.from_documents(
            documents,
            embed_model=embed_model,
            transformations=[node_parser],
            show_progress=True
        )

        index.storage_context.persist(persist_dir=str(persist_dir))
        persist_dir.mkdir(parents=True, exist_ok=True)
        with open(mtime_file, "w", encoding="utf-8") as f:
            json.dump({"total_mtime": current_mtime}, f, ensure_ascii=False)
        
        print(f"[KnowledgeBase] 构建 {name} Index，文档数 {len(documents)}")
        return index

    def retrieve(self, query: str) -> str:
        if not query.strip():
            return ""

        contexts = []
        
        # 1. Lore：混合检索策略
        if self.lore_index:
            lore_engine = self.lore_index.as_retriever(
                similarity_top_k=12,
                similarity_cutoff=0.15
            )
            lore_nodes = lore_engine.retrieve(query)
            
            facts_nodes = []
            story_nodes = []
            
            for node in lore_nodes:
                metadata = node.metadata or {}
                file_type = metadata.get("file_type", "story")
                
                if file_type == "facts":
                    facts_nodes.append(node)
                else:
                    story_nodes.append(node)
            
            selected_nodes = []
            
            # 优先取facts节点
            for node in facts_nodes[:2]:
                content = node.get_content().strip()
                if len(content) > 30:
                    selected_nodes.append(node)
                    print(f"[RAG-Lore-Facts] 匹配结果：{node.score:.3f} | {content[:50]}...")
            
            # 补充story节点
            for node in story_nodes[:2]:
                content = node.get_content().strip()
                if len(content) > 50:
                    selected_nodes.append(node)
                    print(f"[RAG-Lore-Story] 匹配结果：{node.score:.3f} | {content[:50]}...")
            
            if selected_nodes:
                contexts.append("【剧情记忆】")
                seen_content = set()
                for n in selected_nodes:
                    content = n.get_content().strip()
                    if content not in seen_content:
                        seen_content.add(content)
                        contexts.append(content)

        # 2. Style：降低重复频率
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
                print(f"[KnowledgeBase] 随机采样Style失败：{e}")

        if not contexts:
            return ""

        return "\n\n".join(contexts) + "\n\n"
