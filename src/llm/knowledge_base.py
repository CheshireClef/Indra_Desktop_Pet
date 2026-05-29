import os
import json
import random
import threading
import sys
import hashlib
from contextlib import contextmanager
from typing import List
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from llama_index.core import (
    VectorStoreIndex,
    StorageContext,
    load_index_from_storage,
)
from llama_index.core.ingestion import run_transformations
from llama_index.core.schema import Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from utils import resource_path

try:
    import tiktoken_ext.openai_public  # noqa: F401
except Exception:
    pass

# RAG 检索 query 最大长度（与 HuggingFaceEmbedding 默认 max_length 对齐）
RAG_QUERY_MAX_LEN = 512


class KnowledgeBase(QObject):
    indices_loaded = Signal()
    model_loaded_to_cpu = Signal()
    load_failed = Signal(str)
    rebuild_started = Signal(str)

    def __init__(self):
        super().__init__()
        # ========== 知识库初始化 ==========
        self.knowledge_dir = Path(resource_path("src/llm/knowledge"))
        self.knowledge_db_dir = Path(resource_path("src/llm/knowledge_db"))
        
        # 初始化索引（异步执行，避免启动卡顿）
        self.lore_index = None
        self.style_index = None
        self.style_sample_history = []  # 记录近期抽取的style内容，降低重复频率
        # 供长期记忆模块复用的嵌入模型，在 _init_indices_async 中赋值
        self._embed_model = None
        # 嵌入模型与索引构建/检索互斥，避免多线程并发 encode 导致 IndexError
        self._embed_lock = threading.Lock()
        self._embed_ready = False
        self._indices_ready = False
        self._rebuild_in_progress = False
        self._rebuild_depth = 0

    @contextmanager
    def _embed_lock_ctx(self):
        self._embed_lock.acquire()
        try:
            yield
        finally:
            self._embed_lock.release()

    def _begin_rebuild(self, name: str) -> None:
        """索引重建开始（可嵌套 lore/style）。"""
        self._rebuild_depth += 1
        self._rebuild_in_progress = True
        if self._rebuild_depth == 1:
            try:
                self.rebuild_started.emit(name)
            except Exception:
                pass

    def _end_rebuild(self) -> None:
        self._rebuild_depth = max(0, self._rebuild_depth - 1)
        self._rebuild_in_progress = self._rebuild_depth > 0

    def _normalize_rag_query(self, query: str) -> str:
        """截断 RAG 检索用 query，避免超长文本进入嵌入模型。"""
        q = (query or "").strip()
        if len(q) > RAG_QUERY_MAX_LEN:
            print(
                f"[KnowledgeBase] RAG query 过长（{len(q)} 字符），已截断至 {RAG_QUERY_MAX_LEN} 字符"
            )
            return q[:RAG_QUERY_MAX_LEN]
        return q

    def _rag_skip_reason(self) -> str | None:
        """未满足检索条件时返回原因文案，否则 None。"""
        if not self._embed_ready:
            return "嵌入模型未就绪"
        if self._rebuild_in_progress:
            return "知识库索引重建中"
        if not self._indices_ready:
            return "知识库索引未加载完成"
        return None

    def start_loading(self):
        """启动异步加载线程"""
        print("[KnowledgeBase] 后台开始加载嵌入模型与索引（不阻塞桌宠显示）…")
        index_thread = threading.Thread(target=self._init_indices_async)
        index_thread.daemon = True
        index_thread.start()

    def get_embedding(self, text: str) -> List[float] | None:
        """
        获取文本的向量表示，供长期记忆等模块复用。未加载完成时返回 None。
        """
        if not text or not self._embed_ready:
            return None
        normalized = self._normalize_rag_query(text)
        if not normalized:
            return None
        with self._embed_lock_ctx():
            if not self._embed_model:
                return None
            try:
                return self._embed_model.get_query_embedding(normalized)
            except Exception as e:
                print(f"[KnowledgeBase] get_embedding 失败: {e}")
                return None

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
            msg = f"本地模型目录不存在：{local_model_dir}"
            print(f"[KnowledgeBase] {msg}")
            self.load_failed.emit(msg)
            return
        if not list(local_model_dir.glob("*.bin")) and not list(local_model_dir.glob("*.safetensors")):
            msg = f"本地模型目录 {local_model_dir} 中未找到模型权重文件"
            print(f"[KnowledgeBase] {msg}")
            self.load_failed.emit(msg)
            return
        
        # 确认配置文件和自定义代码文件存在
        required_files = ["config.json", "modeling.py", "configuration.py"]
        missing_files = [f for f in required_files if not (local_model_dir / f).exists()]
        if missing_files:
            msg = f"本地模型目录缺少必要文件：{missing_files}"
            print(f"[KnowledgeBase] {msg}")
            self.load_failed.emit(msg)
            return

        # 加载本地模型
        print(f"[KnowledgeBase] 使用本地多语言模型（离线模式）：{local_model_dir}")
        try:
            # 抑制 transformers 的权重未加载警告（这是正常的，因为我们只需要embedding层）
            from transformers import logging as transformers_logging
            transformers_logging.set_verbosity_error()

            embed_model = HuggingFaceEmbedding(
                model_name=str(local_model_dir),
                trust_remote_code=True,
                embed_batch_size=16,
            )
            
            # 手动将模型移动到CPU
            import torch
            embed_model._model = embed_model._model.to("cpu")
            print(f"[KnowledgeBase] 模型已手动移动到CPU设备")
            with self._embed_lock_ctx():
                # 保存引用供长期记忆模块复用，避免重复加载
                self._embed_model = embed_model
                self._embed_ready = True
        except Exception as e:
            msg = f"模型加载失败：{e}"
            print(f"[KnowledgeBase] {msg}")
            self.load_failed.emit(msg)
            return
        # 模型就绪信号在锁外发送，避免持锁期间触发 UI 回调
        self.model_loaded_to_cpu.emit()
        try:
            with self._embed_lock_ctx():
                self.lore_index = self._load_or_build_index(
                    data_dir=Path(resource_path("src/llm/knowledge/lore")),
                    persist_dir=self._get_persist_dir("lore"),
                    embed_model=embed_model,
                    name="Lore",
                    is_lore=True,
                )
                self.style_index = self._load_or_build_index(
                    data_dir=Path(resource_path("src/llm/knowledge/style")),
                    persist_dir=self._get_persist_dir("style"),
                    embed_model=embed_model,
                    name="Style",
                    is_lore=False,
                )
            self._indices_ready = True
            print("[KnowledgeBase] 索引加载完成，发送信号...")
            self.indices_loaded.emit()
        except Exception as e:
            msg = f"索引初始化失败：{e}"
            print(f"[KnowledgeBase] {msg}")
            self.load_failed.emit(msg)

    def _get_data_dir_mtime(self, data_dir: Path) -> float:
        total_mtime = 0.0
        for file in data_dir.rglob("*"):
            if file.is_file() and not file.name.startswith("."):
                try:
                    total_mtime += os.path.getmtime(file)
                except Exception:
                    continue
        return total_mtime

    def _get_data_dir_hash(self, data_dir: Path) -> str:
        hasher = hashlib.sha256()
        files = sorted([p for p in data_dir.rglob("*") if p.is_file() and not p.name.startswith(".")])
        for file in files:
            rel_path = file.relative_to(data_dir).as_posix()
            hasher.update(rel_path.encode("utf-8"))
            try:
                hasher.update(str(file.stat().st_size).encode("utf-8"))
            except Exception:
                pass
            try:
                with open(file, "rb") as f:
                    while True:
                        chunk = f.read(1024 * 1024)
                        if not chunk:
                            break
                        hasher.update(chunk)
            except Exception:
                continue
        return hasher.hexdigest()

    def _get_file_hash(self, file_path: Path) -> str:
        hasher = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    hasher.update(chunk)
        except Exception:
            return ""
        return hasher.hexdigest()

    def _get_rel_path(self, data_dir: Path, file_path: Path) -> str:
        try:
            return file_path.relative_to(data_dir).as_posix()
        except Exception:
            return file_path.name

    def _load_file_manifest(self, persist_dir: Path) -> dict:
        manifest_path = persist_dir / "file_manifest.json"
        if not manifest_path.exists():
            return {}
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            return {}
        return {}

    def _save_file_manifest(self, persist_dir: Path, manifest: dict) -> None:
        try:
            persist_dir.mkdir(parents=True, exist_ok=True)
            with open(persist_dir / "file_manifest.json", "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False)
        except Exception:
            pass

    def _build_file_manifest(self, data_dir: Path, old_manifest: dict) -> dict:
        manifest = {}
        for file in data_dir.rglob("*"):
            if file.is_file() and not file.name.startswith("."):
                rel_path = self._get_rel_path(data_dir, file)
                try:
                    stat = file.stat()
                    size = stat.st_size
                    mtime = stat.st_mtime
                except Exception:
                    size = 0
                    mtime = 0.0
                old_entry = old_manifest.get(rel_path) if isinstance(old_manifest, dict) else None
                if old_entry and old_entry.get("size") == size and old_entry.get("mtime") == mtime:
                    file_hash = old_entry.get("hash", "")
                else:
                    file_hash = self._get_file_hash(file)
                manifest[rel_path] = {
                    "size": size,
                    "mtime": mtime,
                    "hash": file_hash
                }
        return manifest

    def _diff_file_manifest(self, old_manifest: dict, new_manifest: dict):
        old_keys = set(old_manifest.keys()) if isinstance(old_manifest, dict) else set()
        new_keys = set(new_manifest.keys()) if isinstance(new_manifest, dict) else set()
        added = sorted(new_keys - old_keys)
        deleted = sorted(old_keys - new_keys)
        changed = []
        for key in sorted(new_keys & old_keys):
            old_hash = old_manifest.get(key, {}).get("hash")
            new_hash = new_manifest.get(key, {}).get("hash")
            if old_hash != new_hash:
                changed.append(key)
        return added, changed, deleted

    def _get_manifest_hash(self, manifest: dict) -> str:
        hasher = hashlib.sha256()
        for key in sorted(manifest.keys()):
            entry = manifest.get(key, {})
            hasher.update(key.encode("utf-8"))
            hasher.update(str(entry.get("hash", "")).encode("utf-8"))
        return hasher.hexdigest()

    def _build_documents_from_files(self, data_dir: Path, rel_paths: list, is_lore: bool) -> List[Document]:
        documents = []
        for rel_path in rel_paths:
            file_path = data_dir / rel_path
            if not file_path.exists() or not file_path.is_file():
                continue
            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception:
                continue
            file_name = file_path.name
            if is_lore:
                file_type = "facts" if file_name.endswith(".facts.json") or file_name.endswith(".facts.txt") else "story"
                metadata = {
                    "file_name": file_name,
                    "file_type": file_type,
                    "source_path": rel_path
                }
            else:
                metadata = {
                    "file_name": file_name,
                    "file_type": "style",
                    "source_path": rel_path
                }
            doc = Document(text=content, metadata=metadata, id_=rel_path)
            documents.append(doc)
        return documents

    def _get_persist_dir(self, subdir: str) -> Path:
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            return Path(resource_path(f"src/llm/knowledge_db/{subdir}"))
        else:
            base = self.knowledge_db_dir
            base.mkdir(parents=True, exist_ok=True)
            return base / subdir

    def _load_or_build_index(self, data_dir: Path, persist_dir: Path, embed_model, name: str, is_lore: bool = False):
        if not data_dir.exists():
            print(f"[KnowledgeBase] {name} 目录不存在，跳过")
            return None

        data_hash_file = persist_dir / "data_hash.json"
        mtime_file = persist_dir / "data_mtime.json"
        old_manifest = self._load_file_manifest(persist_dir)
        current_manifest = self._build_file_manifest(data_dir, old_manifest)
        added, changed, deleted = self._diff_file_manifest(old_manifest, current_manifest)
        has_changes = bool(added or changed or deleted)

        if is_lore:
            node_parser = SentenceSplitter(
                chunk_size=800,
                chunk_overlap=200,
                paragraph_separator="\n\n",
                separator="。"
            )
        else:
            node_parser = SentenceSplitter(
                chunk_size=300,
                chunk_overlap=50,
                paragraph_separator="\n",
                separator="。"
            )

        if persist_dir.exists() and not old_manifest and current_manifest:
            try:
                storage = StorageContext.from_defaults(persist_dir=str(persist_dir))
                index = load_index_from_storage(storage, embed_model=embed_model)
                self._save_file_manifest(persist_dir, current_manifest)
                current_mtime = self._get_data_dir_mtime(data_dir)
                with open(mtime_file, "w", encoding="utf-8") as f:
                    json.dump({"total_mtime": current_mtime}, f, ensure_ascii=False)
                try:
                    data_hash = self._get_manifest_hash(current_manifest)
                    with open(data_hash_file, "w", encoding="utf-8") as f:
                        json.dump({"data_hash": data_hash}, f, ensure_ascii=False)
                except Exception:
                    pass
                print(f"[KnowledgeBase] 加载已有 {name} Index")
                return index
            except Exception as e:
                print(f"[KnowledgeBase] 加载{name} Index失败：{e}，将重建")

        if persist_dir.exists() and not has_changes:
            try:
                storage = StorageContext.from_defaults(persist_dir=str(persist_dir))
                index = load_index_from_storage(storage, embed_model=embed_model)
                print(f"[KnowledgeBase] 加载已有 {name} Index")
                return index
            except Exception as e:
                print(f"[KnowledgeBase] 加载{name} Index失败：{e}，将重建")
                has_changes = True

        if persist_dir.exists() and has_changes:
            self._begin_rebuild(name)
            try:
                storage = StorageContext.from_defaults(persist_dir=str(persist_dir))
                index = load_index_from_storage(storage, embed_model=embed_model)
                to_delete = deleted + changed
                for rel_path in to_delete:
                    try:
                        index.delete_ref_doc(rel_path, delete_from_docstore=True)
                    except Exception:
                        pass
                to_add = added + changed
                if to_add:
                    documents = self._build_documents_from_files(data_dir, to_add, is_lore)
                    if documents:
                        for doc in documents:
                            try:
                                index.docstore.set_document_hash(doc.id_, doc.hash)
                            except Exception:
                                pass
                        nodes = run_transformations(
                            documents,
                            transformations=[node_parser],
                            show_progress=True
                        )
                        index.insert_nodes(nodes)
                index.storage_context.persist(persist_dir=str(persist_dir))
                current_mtime = self._get_data_dir_mtime(data_dir)
                with open(mtime_file, "w", encoding="utf-8") as f:
                    json.dump({"total_mtime": current_mtime}, f, ensure_ascii=False)
                try:
                    data_hash = self._get_manifest_hash(current_manifest)
                    with open(data_hash_file, "w", encoding="utf-8") as f:
                        json.dump({"data_hash": data_hash}, f, ensure_ascii=False)
                except Exception:
                    pass
                self._save_file_manifest(persist_dir, current_manifest)
                print(f"[KnowledgeBase] 增量更新 {name} Index 完成")
                return index
            except Exception as e:
                print(f"[KnowledgeBase] 增量更新{name} Index失败：{e}，将重建")
            finally:
                self._end_rebuild()

        self._begin_rebuild(name)
        try:
            all_files = [
                self._get_rel_path(data_dir, p)
                for p in data_dir.rglob("*")
                if p.is_file() and not p.name.startswith(".")
            ]
            documents = self._build_documents_from_files(data_dir, all_files, is_lore)
            if not documents:
                print(f"[KnowledgeBase] {name} 目录为空")
                return None

            for doc in documents:
                try:
                    doc.id_ = doc.id_ or doc.metadata.get("source_path")
                except Exception:
                    pass

            index = VectorStoreIndex.from_documents(
                documents,
                embed_model=embed_model,
                transformations=[node_parser],
                show_progress=True,
            )

            index.storage_context.persist(persist_dir=str(persist_dir))
            persist_dir.mkdir(parents=True, exist_ok=True)
            current_mtime = self._get_data_dir_mtime(data_dir)
            with open(mtime_file, "w", encoding="utf-8") as f:
                json.dump({"total_mtime": current_mtime}, f, ensure_ascii=False)
            try:
                data_hash = self._get_manifest_hash(current_manifest)
                with open(data_hash_file, "w", encoding="utf-8") as f:
                    json.dump({"data_hash": data_hash}, f, ensure_ascii=False)
            except Exception:
                pass
            self._save_file_manifest(persist_dir, current_manifest)

            print(f"[KnowledgeBase] 构建 {name} Index，文档数 {len(documents)}")
            return index
        finally:
            self._end_rebuild()

    def retrieve(self, query: str) -> str:
        """检索知识库片段；未就绪或重建中时返回空字符串。"""
        query = self._normalize_rag_query(query)
        if not query:
            return ""
        skip = self._rag_skip_reason()
        if skip:
            print(f"[KnowledgeBase] 跳过 RAG 检索：{skip}")
            return ""
        with self._embed_lock_ctx():
            return self._retrieve_locked(query)

    def _retrieve_locked(self, query: str) -> str:
        """在嵌入锁内执行向量检索与 style 采样。"""
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
