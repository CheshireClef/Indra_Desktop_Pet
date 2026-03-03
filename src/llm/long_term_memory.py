"""
长期记忆模块（SQLite + 向量）
存储与用户对话相关的重要信息与用户偏好；不替代 RAG（lore/style）与人设。
向量用于检索「与当前对话最相关的记忆」，embedding 复用 KnowledgeBase 的 gte-multilingual-base。
支持半结构化：topic（主题）+ content（自由描述）；同主题按 topic 向量相似度聚类，
当同一主题下条数达到 5 的倍数时触发合并，由 LLM 输出精简合并句（每条≤50 字，可多条）并写回。
检索采用混合评分：语义相似度 + 时间衰减（艾宾浩斯曲线）。
"""
import json
import math
import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Any, Callable, Tuple

from utils import resource_path


# 内容相似度超过此阈值视为重复，执行更新而非新增
SIMILARITY_THRESHOLD = 0.92
# 主题相似度超过此阈值视为同一 topic（用于聚类与合并触发）
TOPIC_SIMILARITY_THRESHOLD = 0.85
# 同一 topic 下条数达到此数的倍数时触发合并（5、10、15…）
MERGE_COUNT_MULTIPLE = 5
# 合并后单条记忆最大字数
MERGE_MAX_CHARS_PER_ITEM = 50
# 检索时返回的最大条数
DEFAULT_TOP_K = 5

# 混合评分：时间衰减（艾宾浩斯遗忘曲线）
HALF_LIFE_DAYS = 30  # 半衰期（天）
LAMBDA = math.log(2) / HALF_LIFE_DAYS  # 衰减系数
W_SEM = 1.2   # 语义相似度权重
W_TIME = 0.3  # 时间衰减权重


def _embedding_to_blob(vec: List[float]) -> bytes:
    """将 float 列表转为 BLOB（float32 小端）"""
    return struct.pack(f"{len(vec)}f", *vec)


def _blob_to_embedding(blob: bytes) -> List[float]:
    """将 BLOB 转回 float 列表"""
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """假设向量已归一化，点积即余弦相似度"""
    if not a or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def _time_decay_from_updated_at(updated_at: Optional[str]) -> float:
    """
    基于艾宾浩斯遗忘曲线，根据 updated_at 计算时间衰减因子。
    半衰期 HALF_LIFE_DAYS 天：越新的记忆 time_decay 越接近 1，越旧越接近 0。
    若 updated_at 缺失或解析失败则返回 0.5（折中）。
    """
    if not (updated_at or "").strip():
        return 0.5
    try:
        s = (updated_at or "").strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta_days = (now - dt).total_seconds() / 86400.0
        if delta_days < 0:
            delta_days = 0.0
        return math.exp(-LAMBDA * delta_days)
    except Exception:
        return 0.5


class LongTermMemory:
    """
    长期记忆：SQLite 单表 + 向量 BLOB，支持 topic 半结构化与按主题聚类合并。
    依赖 KnowledgeBase.get_embedding 获取向量；合并时通过 merge_llm_caller 调用 LLM。
    """

    def __init__(
        self,
        knowledge_base: Any,
        db_path: Optional[Path] = None,
        merge_llm_caller: Optional[Callable[[list], Optional[str]]] = None,
    ):
        if db_path is None:
            config_dir = Path(resource_path("config"))
            config_dir.mkdir(parents=True, exist_ok=True)
            db_path = config_dir / "user_memory.db"
        self.db_path = Path(db_path)
        self.kb = knowledge_base
        self._merge_llm_caller = merge_llm_caller
        self._init_db()

    def _init_db(self) -> None:
        """创建表结构；若表已存在则补列 topic、topic_embedding（兼容旧库）"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    embedding BLOB,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    topic TEXT,
                    topic_embedding BLOB
                )
            """)
            conn.commit()
            # 兼容旧表：若无 topic 列则追加
            cur = conn.execute("PRAGMA table_info(memories)")
            cols = [row[1] for row in cur.fetchall()]
            if "topic" not in cols:
                conn.execute("ALTER TABLE memories ADD COLUMN topic TEXT")
                conn.commit()
            if "topic_embedding" not in cols:
                conn.execute("ALTER TABLE memories ADD COLUMN topic_embedding BLOB")
                conn.commit()
        finally:
            conn.close()

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """委托给知识库获取向量，未就绪返回 None"""
        return self.kb.get_embedding(text) if self.kb else None

    def _get_cluster_by_topic_embedding(
        self, conn: sqlite3.Connection, topic_embedding: List[float]
    ) -> List[dict]:
        """按 topic 向量相似度聚类，返回与该 topic 同簇的所有行（含 id、content、topic、created_at）"""
        rows = conn.execute(
            "SELECT id, content, topic, topic_embedding, created_at FROM memories WHERE topic_embedding IS NOT NULL"
        ).fetchall()
        cluster = []
        for row in rows:
            rid, content, topic, te_blob, created_at = row
            if not te_blob:
                continue
            try:
                te = _blob_to_embedding(te_blob)
                sim = _cosine_similarity(topic_embedding, te)
                if sim >= TOPIC_SIMILARITY_THRESHOLD:
                    cluster.append({
                        "id": rid,
                        "content": content or "",
                        "topic": topic,
                        "created_at": created_at or "",
                    })
            except Exception:
                continue
        return cluster

    def _merge_cluster(self, conn: sqlite3.Connection, cluster: List[dict]) -> bool:
        """
        将同主题多条记忆交给 LLM 合并为≤50 字/条的精简句（可多条），写回并删旧行。
        要求 LLM 输出 JSON 且用 Markdown 代码块包裹，减少幻觉。
        成功返回 True，失败不删数据并返回 False。
        """
        if not self._merge_llm_caller or len(cluster) < MERGE_COUNT_MULTIPLE:
            return False
        contents = [c["content"] for c in cluster if (c.get("content") or "").strip()]
        if not contents:
            return False
        prompt = (
            "你负责合并精炼用户记忆。下面是与某用户相关的多条记忆（主题相近），请合并为一条或数条精炼句，"
            f"每条不超过{MERGE_MAX_CHARS_PER_ITEM}字，保留要点；若信息多可拆成多条。\n"
            "输出必须为 JSON，且用 Markdown 代码块包裹，例如：\n```json\n{\"topic\":\"规范主题词\",\"memories\":[\"句1\",\"句2\"]}\n```\n"
            "只输出该 JSON，不要其他文字。\n\n请合并以下记忆：\n"
            + "\n".join(f"- {c}" for c in contents)
        )
        messages = [
            {"role": "system", "content": "你只输出一个 JSON 对象，包含 topic（简短主题词）和 memories（字符串数组，每条≤50字）。输出时用 Markdown 代码块包裹：```json\n{...}\n```"},
            {"role": "user", "content": prompt},
        ]
        try:
            raw = self._merge_llm_caller(messages)
            if not (raw or "").strip():
                return False
            raw = raw.strip()
            if raw.startswith("```"):
                for prefix in ("```json", "```"):
                    if raw.startswith(prefix):
                        raw = raw[len(prefix):].strip()
                        break
                if raw.endswith("```"):
                    raw = raw[:-3].strip()
            obj = json.loads(raw)
            topic = (obj.get("topic") or "").strip() or "未分类"
            memories = obj.get("memories")
            if not isinstance(memories, list) or not memories:
                return False
            now = datetime.utcnow().isoformat() + "Z"
            # 合并时保留簇内最早的 created_at（思路 A：合并=复习，updated_at 为 now）
            created_at_min = min(
                (c.get("created_at") or "").strip() or now for c in cluster
            )
            if not created_at_min:
                created_at_min = now
            topic_embedding = self._get_embedding(topic)
            if not topic_embedding:
                return False
            topic_blob = _embedding_to_blob(topic_embedding)
            ids = [c["id"] for c in cluster]
            for row_id in ids:
                conn.execute("DELETE FROM memories WHERE id=?", (row_id,))
            for item in memories:
                text = (item if isinstance(item, str) else str(item)).strip()
                if not text or len(text) > MERGE_MAX_CHARS_PER_ITEM * 2:
                    continue
                vec = self._get_embedding(text)
                if vec is None:
                    continue
                conn.execute(
                    """INSERT INTO memories (content, embedding, created_at, updated_at, topic, topic_embedding)
                       VALUES (?,?,?,?,?,?)""",
                    (text, _embedding_to_blob(vec), created_at_min, now, topic, topic_blob),
                )
            conn.commit()
            print(f"[长期记忆] 合并完成：{len(ids)} 条 → {len(memories)} 条 | topic={topic}")
            return True
        except Exception as e:
            print(f"[长期记忆] 合并失败（已保留原数据）: {e}")
            return False

    def add_or_update(self, content: str, topic: Optional[str] = None) -> None:
        """
        若新记忆与已有某条内容语义高度相似则更新该条，否则新增。
        topic 可选；若提供则存为主题并用于聚类，当同主题（按 topic 向量相似度）条数达到 5 的倍数时触发合并。
        若 embedding 不可用则跳过写入。
        """
        content = (content or "").strip()
        if not content:
            return
        vec = self._get_embedding(content)
        if vec is None:
            return
        blob = _embedding_to_blob(vec)
        topic_blob = None
        topic_vec: Optional[List[float]] = None
        if (topic or "").strip():
            topic_vec = self._get_embedding((topic or "").strip())
            if topic_vec is not None:
                topic_blob = _embedding_to_blob(topic_vec)
        from datetime import datetime
        now = datetime.utcnow().isoformat() + "Z"
        conn = sqlite3.connect(str(self.db_path))
        try:
            rows = conn.execute(
                "SELECT id, content, embedding FROM memories"
            ).fetchall()
            best_id = None
            best_sim = -1.0
            for row in rows:
                rid, _, emb_blob = row[0], row[1], row[2]
                if emb_blob:
                    try:
                        ev = _blob_to_embedding(emb_blob)
                        sim = _cosine_similarity(vec, ev)
                        if sim > best_sim:
                            best_sim = sim
                            best_id = rid
                    except Exception:
                        continue
            if best_id is not None and best_sim >= SIMILARITY_THRESHOLD:
                if topic_blob is not None:
                    conn.execute(
                        "UPDATE memories SET content=?, embedding=?, updated_at=?, topic=?, topic_embedding=? WHERE id=?",
                        (content, blob, now, (topic or "").strip() or None, topic_blob, best_id),
                    )
                else:
                    conn.execute(
                        "UPDATE memories SET content=?, embedding=?, updated_at=? WHERE id=?",
                        (content, blob, now, best_id),
                    )
                conn.commit()
                print(f"[长期记忆] 更新已有记忆 id={best_id} | content={content[:50]}...")
            else:
                conn.execute(
                    """INSERT INTO memories (content, embedding, created_at, updated_at, topic, topic_embedding)
                       VALUES (?,?,?,?,?,?)""",
                    (content, blob, now, now, (topic or "").strip() or None, topic_blob),
                )
                conn.commit()
                print(f"[长期记忆] 写入新记忆 | content={content[:50]}... | topic={topic or '-'}")
            # 仅在新插入且提供了 topic 时检查是否触发合并（同主题条数为 5 的倍数）
            if best_id is None and topic_vec is not None and self._merge_llm_caller:
                cluster = self._get_cluster_by_topic_embedding(conn, topic_vec)
                n = len(cluster)
                if n >= MERGE_COUNT_MULTIPLE and n % MERGE_COUNT_MULTIPLE == 0:
                    self._merge_cluster(conn, cluster)
        finally:
            conn.close()

    def search_with_scores(self, query: str, top_k: int = DEFAULT_TOP_K) -> List[Tuple[str, float]]:
        """
        混合评分检索：score = W_SEM×语义相似度 + W_TIME×时间衰减。
        时间衰减基于艾宾浩斯曲线，以 updated_at 距今天数计算。
        返回 [(content, score), ...]，按 score 降序。
        """
        vec = self._get_embedding(query)
        if vec is None:
            return []
        conn = sqlite3.connect(str(self.db_path))
        try:
            rows = conn.execute(
                "SELECT id, content, embedding, updated_at FROM memories"
            ).fetchall()
            scored = []
            for row in rows:
                rid, content, emb_blob, updated_at = row
                if not emb_blob or not content:
                    continue
                try:
                    ev = _blob_to_embedding(emb_blob)
                    sim = _cosine_similarity(vec, ev)
                    time_decay = _time_decay_from_updated_at(updated_at)
                    score = W_SEM * sim + W_TIME * time_decay
                    scored.append((content, score))
                except Exception:
                    continue
            scored.sort(key=lambda x: -x[1])
            return scored[:top_k]
        finally:
            conn.close()

    def search(self, query: str, top_k: int = DEFAULT_TOP_K) -> List[str]:
        """按混合评分检索，仅返回 content 列表（委托至 search_with_scores）"""
        return [c for c, _ in self.search_with_scores(query, top_k)]

    def get_by_id(self, id: int) -> Optional[dict]:
        """按 id 查询一条记忆，返回 dict（id, content, topic, created_at, updated_at），不存在返回 None"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute(
                "SELECT id, content, created_at, updated_at, topic FROM memories WHERE id=?",
                (id,),
            ).fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "content": row[1] or "",
                "created_at": row[2],
                "updated_at": row[3],
                "topic": row[4] if len(row) > 4 else "",
            }
        finally:
            conn.close()

    def update_content_by_id(self, id: int, new_content: str) -> bool:
        """
        仅更新指定 id 的记忆正文内容（不修改 topic）；会重新计算 content 的 embedding 并更新 updated_at。
        返回是否成功更新（若 id 不存在或 new_content 为空则返回 False）。
        """
        new_content = (new_content or "").strip()
        if not new_content:
            return False
        vec = self._get_embedding(new_content)
        if vec is None:
            return False
        from datetime import datetime
        now = datetime.utcnow().isoformat() + "Z"
        blob = _embedding_to_blob(vec)
        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.execute(
                "UPDATE memories SET content=?, embedding=?, updated_at=? WHERE id=?",
                (new_content, blob, now, id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def delete_by_id(self, id: int) -> None:
        """按 id 删除一条记忆"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("DELETE FROM memories WHERE id=?", (id,))
            conn.commit()
        finally:
            conn.close()

    def clear_all(self) -> None:
        """清空所有记忆"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("DELETE FROM memories")
            conn.commit()
        finally:
            conn.close()

    def list_all(self) -> List[dict]:
        """返回所有记忆的 id、content、topic、created_at、updated_at，供管理 UI 使用"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            rows = conn.execute(
                "SELECT id, content, created_at, updated_at, topic FROM memories ORDER BY id"
            ).fetchall()
            return [
                {
                    "id": r[0],
                    "content": r[1] or "",
                    "created_at": r[2],
                    "updated_at": r[3],
                    "topic": r[4] if len(r) > 4 else "",
                }
                for r in rows
            ]
        finally:
            conn.close()
