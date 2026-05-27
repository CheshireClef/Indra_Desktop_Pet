"""
长期记忆模块（SQLite + 向量）
存储与用户对话相关的重要信息与用户偏好；不替代 RAG（lore/style）与人设。
向量用于检索「与当前对话最相关的记忆」，embedding 复用 KnowledgeBase 的 gte-multilingual-base。
支持半结构化：topic（主题）+ content（自由描述）；同主题按 topic 向量相似度聚类，
当同一主题下条数达到 5 的倍数时触发合并，由 LLM 输出精简合并句（每条≤50 字，可多条）并写回。
检索：双路召回（向量混合分 + 近 7 日新近）合并去重；命中后 ref_count 强化。
整理：设置页手动预览后合并/删除；pinned 永久保留；ref_count NULL 表示升级前遗留条。
"""
import json
import math
import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Any, Callable, Tuple, Dict, Set

from utils import resource_path
from llm.clients.text_sanitize import extract_json_payload


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

# 双路检索
RECALL_VECTOR_TOP = 5
RECALL_RECENCY_DAYS = 7
RECALL_RECENCY_TOP = 3
W_PINNED_BOOST = 0.1  # 永久保留条目向量路加分

# 手动整理
ORGANIZE_DELETE_IDLE_DAYS = 90
ORGANIZE_MERGE_MIN_CLUSTER = 2

# 混合评分：时间衰减（艾宾浩斯遗忘曲线）
HALF_LIFE_DAYS = 30  # 半衰期（天）
LAMBDA = math.log(2) / HALF_LIFE_DAYS  # 衰减系数
W_SEM = 1.2   # 语义相似度权重
W_TIME = 0.3  # 时间衰减权重


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _parse_updated_at(updated_at: Optional[str]) -> Optional[datetime]:
    if not (updated_at or "").strip():
        return None
    try:
        s = (updated_at or "").strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _days_since_updated_at(updated_at: Optional[str]) -> float:
    dt = _parse_updated_at(updated_at)
    if dt is None:
        return 0.0
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0)


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
        """创建表结构；若表已存在则补列（兼容旧库）"""
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
            cur = conn.execute("PRAGMA table_info(memories)")
            cols = [row[1] for row in cur.fetchall()]
            if "topic" not in cols:
                conn.execute("ALTER TABLE memories ADD COLUMN topic TEXT")
                conn.commit()
            if "topic_embedding" not in cols:
                conn.execute("ALTER TABLE memories ADD COLUMN topic_embedding BLOB")
                conn.commit()
            if "ref_count" not in cols:
                conn.execute("ALTER TABLE memories ADD COLUMN ref_count INTEGER")
                conn.commit()
                # 升级前已有行保持 NULL（遗留保护，不参与默认删除候选）
            if "pinned" not in cols:
                conn.execute("ALTER TABLE memories ADD COLUMN pinned INTEGER DEFAULT 0")
                conn.commit()
                conn.execute("UPDATE memories SET pinned = 0 WHERE pinned IS NULL")
                conn.commit()
        finally:
            conn.close()

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """委托给知识库获取向量，未就绪返回 None"""
        return self.kb.get_embedding(text) if self.kb else None

    def _fetch_all_rows(self, conn: sqlite3.Connection) -> List[dict]:
        rows = conn.execute(
            """SELECT id, content, embedding, created_at, updated_at, topic, topic_embedding,
                      ref_count, COALESCE(pinned, 0) FROM memories ORDER BY id"""
        ).fetchall()
        return [
            {
                "id": r[0],
                "content": r[1] or "",
                "embedding": r[2],
                "created_at": r[3] or "",
                "updated_at": r[4] or "",
                "topic": r[5] or "",
                "topic_embedding": r[6],
                "ref_count": r[7],
                "pinned": int(r[8] or 0),
            }
            for r in rows
        ]

    def _get_cluster_by_topic_embedding(
        self, conn: sqlite3.Connection, topic_embedding: List[float], *, exclude_ids: Optional[Set[int]] = None
    ) -> List[dict]:
        """按 topic 向量相似度聚类，返回与该 topic 同簇的所有行"""
        exclude_ids = exclude_ids or set()
        rows = conn.execute(
            "SELECT id, content, topic, topic_embedding, created_at FROM memories WHERE topic_embedding IS NOT NULL"
        ).fetchall()
        cluster = []
        for row in rows:
            rid, content, topic, te_blob, created_at = row
            if rid in exclude_ids or not te_blob:
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

    def _build_topic_merge_groups(self, conn: sqlite3.Connection) -> List[dict]:
        """扫描全表，构建待合并的 topic 簇（≥ ORGANIZE_MERGE_MIN_CLUSTER）"""
        rows = conn.execute(
            "SELECT id, topic, topic_embedding FROM memories WHERE topic_embedding IS NOT NULL"
        ).fetchall()
        assigned: Set[int] = set()
        groups: List[dict] = []
        for rid, topic, te_blob in rows:
            if rid in assigned or not te_blob:
                continue
            try:
                te = _blob_to_embedding(te_blob)
            except Exception:
                continue
            cluster = self._get_cluster_by_topic_embedding(conn, te, exclude_ids=assigned)
            if len(cluster) < ORGANIZE_MERGE_MIN_CLUSTER:
                continue
            ids = {c["id"] for c in cluster}
            assigned |= ids
            groups.append({
                "ids": sorted(ids),
                "topic": (topic or cluster[0].get("topic") or "未分类"),
                "items": cluster,
            })
        return groups

    def _find_duplicate_delete_candidates(self, rows: List[dict]) -> List[dict]:
        """内容相似度≥阈值：保留 updated_at 较新者，另一条进删除候选（未 pinned）"""
        candidates: List[dict] = []
        n = len(rows)
        marked_delete: Set[int] = set()
        for i in range(n):
            if rows[i]["id"] in marked_delete or rows[i].get("pinned"):
                continue
            emb_i = rows[i].get("embedding")
            if not emb_i:
                continue
            try:
                vi = _blob_to_embedding(emb_i)
            except Exception:
                continue
            for j in range(i + 1, n):
                if rows[j]["id"] in marked_delete or rows[j].get("pinned"):
                    continue
                emb_j = rows[j].get("embedding")
                if not emb_j:
                    continue
                try:
                    vj = _blob_to_embedding(emb_j)
                except Exception:
                    continue
                if _cosine_similarity(vi, vj) < SIMILARITY_THRESHOLD:
                    continue
                a, b = rows[i], rows[j]
                da = _parse_updated_at(a.get("updated_at"))
                db = _parse_updated_at(b.get("updated_at"))
                if da and db:
                    keep, drop = (a, b) if da >= db else (b, a)
                else:
                    keep, drop = (a, b)
                if drop["id"] not in marked_delete:
                    marked_delete.add(drop["id"])
                    candidates.append({
                        "id": drop["id"],
                        "content": drop["content"],
                        "reason": "duplicate",
                        "keep_id": keep["id"],
                    })
        return candidates

    def _delete_candidates_for_rows(
        self, rows: List[dict], *, include_legacy: bool = False
    ) -> Tuple[List[dict], List[dict]]:
        """
        返回 (标准删除候选, 遗留条删除候选)。
        标准：pinned=0, ref_count=0, 闲置≥ ORGANIZE_DELETE_IDLE_DAYS
        遗留：ref_count IS NULL，仅 include_legacy 时返回
        """
        standard: List[dict] = []
        legacy: List[dict] = []
        for r in rows:
            if r.get("pinned"):
                continue
            rc = r.get("ref_count")
            idle = _days_since_updated_at(r.get("updated_at")) >= ORGANIZE_DELETE_IDLE_DAYS
            if rc is None:
                if include_legacy and idle:
                    legacy.append({
                        "id": r["id"],
                        "content": r["content"],
                        "reason": "legacy_idle",
                    })
            elif rc == 0 and idle:
                standard.append({
                    "id": r["id"],
                    "content": r["content"],
                    "reason": "idle_unreferenced",
                })
        return standard, legacy

    def _merge_cluster(
        self, conn: sqlite3.Connection, cluster: List[dict], *, force: bool = False
    ) -> bool:
        """
        将同主题多条记忆交给 LLM 合并为≤50 字/条的精简句（可多条），写回并删旧行。
        force=True 时允许小簇（手动整理）；写入路径仍要求 ≥ MERGE_COUNT_MULTIPLE。
        """
        min_size = ORGANIZE_MERGE_MIN_CLUSTER if force else MERGE_COUNT_MULTIPLE
        if not self._merge_llm_caller or len(cluster) < min_size:
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
            raw = extract_json_payload(raw.strip())
            if not raw:
                return False
            obj = json.loads(raw)
            topic = (obj.get("topic") or "").strip() or "未分类"
            memories = obj.get("memories")
            if not isinstance(memories, list) or not memories:
                return False
            now = _utc_now_iso()
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
            inserted = 0
            for item in memories:
                text = (item if isinstance(item, str) else str(item)).strip()
                if not text or len(text) > MERGE_MAX_CHARS_PER_ITEM * 2:
                    continue
                vec = self._get_embedding(text)
                if vec is None:
                    continue
                conn.execute(
                    """INSERT INTO memories (
                           content, embedding, created_at, updated_at, topic, topic_embedding,
                           ref_count, pinned)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (text, _embedding_to_blob(vec), created_at_min, now, topic, topic_blob, 0, 0),
                )
                inserted += 1
            conn.commit()
            print(f"[长期记忆] 合并完成：{len(ids)} 条 → {inserted} 条 | topic={topic}")
            return inserted > 0
        except Exception as e:
            print(f"[长期记忆] 合并失败（已保留原数据）: {e}")
            return False

    def _reinforce_ids(self, conn: sqlite3.Connection, ids: List[int]) -> None:
        """对话检索命中：ref_count += 1，updated_at 刷新"""
        if not ids:
            return
        now = _utc_now_iso()
        for rid in ids:
            conn.execute(
                """UPDATE memories SET
                   ref_count = COALESCE(ref_count, 0) + 1,
                   updated_at = ?
                   WHERE id = ?""",
                (now, rid),
            )
        conn.commit()

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
        now = _utc_now_iso()
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
                        """UPDATE memories SET content=?, embedding=?, updated_at=?, topic=?, topic_embedding=?
                           WHERE id=?""",
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
                    """INSERT INTO memories (
                           content, embedding, created_at, updated_at, topic, topic_embedding,
                           ref_count, pinned)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (content, blob, now, now, (topic or "").strip() or None, topic_blob, 0, 0),
                )
                conn.commit()
                print(f"[长期记忆] 写入新记忆 | content={content[:50]}... | topic={topic or '-'}")
            if best_id is None and topic_vec is not None and self._merge_llm_caller:
                cluster = self._get_cluster_by_topic_embedding(conn, topic_vec)
                n = len(cluster)
                if n >= MERGE_COUNT_MULTIPLE and n % MERGE_COUNT_MULTIPLE == 0:
                    self._merge_cluster(conn, cluster, force=False)
        finally:
            conn.close()

    def search_with_scores(self, query: str, top_k: int = DEFAULT_TOP_K) -> List[Tuple[str, float]]:
        """
        双路检索：向量混合分 + 近 RECALL_RECENCY_DAYS 日新近；按 id 去重合并后 reinforce。
        返回 [(content, score), ...]。
        """
        vec = self._get_embedding(query)
        if vec is None:
            return []
        conn = sqlite3.connect(str(self.db_path))
        try:
            rows = conn.execute(
                """SELECT id, content, embedding, updated_at, pinned FROM memories"""
            ).fetchall()
            vector_scored: List[Tuple[int, str, float]] = []
            for row in rows:
                rid, content, emb_blob, updated_at, pinned = row
                if not emb_blob or not content:
                    continue
                try:
                    ev = _blob_to_embedding(emb_blob)
                    sim = _cosine_similarity(vec, ev)
                    time_decay = _time_decay_from_updated_at(updated_at)
                    score = W_SEM * sim + W_TIME * time_decay
                    if pinned:
                        score += W_PINNED_BOOST
                    vector_scored.append((rid, content, score))
                except Exception:
                    continue
            vector_scored.sort(key=lambda x: -x[2])
            vector_top = vector_scored[:RECALL_VECTOR_TOP]

            cutoff = datetime.now(timezone.utc).timestamp() - RECALL_RECENCY_DAYS * 86400
            recency_rows: List[Tuple[int, str, float]] = []
            for row in rows:
                rid, content, _, updated_at, pinned = row
                if not content:
                    continue
                dt = _parse_updated_at(updated_at)
                if dt is None or dt.timestamp() < cutoff:
                    continue
                recency_rows.append((rid, content, dt.timestamp()))
            recency_rows.sort(key=lambda x: -x[2])
            recency_top = recency_rows[:RECALL_RECENCY_TOP]

            merged_ids: List[int] = []
            merged_content: Dict[int, str] = {}
            merged_score: Dict[int, float] = {}
            for rid, content, score in vector_top:
                if rid not in merged_ids:
                    merged_ids.append(rid)
                    merged_content[rid] = content
                    merged_score[rid] = score
            for rid, content, _ in recency_top:
                if len(merged_ids) >= top_k:
                    break
                if rid not in merged_ids:
                    merged_ids.append(rid)
                    merged_content[rid] = content
                    merged_score[rid] = 0.5

            final_ids = merged_ids[:top_k]
            self._reinforce_ids(conn, final_ids)
            return [(merged_content[i], merged_score.get(i, 0.0)) for i in final_ids]
        finally:
            conn.close()

    def search(self, query: str, top_k: int = DEFAULT_TOP_K) -> List[str]:
        """按混合评分检索，仅返回 content 列表（委托至 search_with_scores）"""
        return [c for c, _ in self.search_with_scores(query, top_k)]

    def set_pinned(self, id: int, pinned: bool) -> bool:
        """设置永久保留标记"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.execute(
                "UPDATE memories SET pinned=? WHERE id=?",
                (1 if pinned else 0, id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def preview_organize(self, *, include_legacy: bool = False) -> dict:
        """
        预览手动整理：合并组、重复项删除候选、闲置删除候选、遗留候选。
        不修改数据库。
        """
        conn = sqlite3.connect(str(self.db_path))
        try:
            rows = self._fetch_all_rows(conn)
            merge_groups = self._build_topic_merge_groups(conn)
            dup_deletes = self._find_duplicate_delete_candidates(rows)
            dup_ids = {d["id"] for d in dup_deletes}
            standard, legacy = self._delete_candidates_for_rows(rows, include_legacy=include_legacy)
            # 合并组内的 id 不计入闲置删除（将由合并删除）
            merge_ids: Set[int] = set()
            for g in merge_groups:
                merge_ids |= set(g["ids"])
            standard = [d for d in standard if d["id"] not in merge_ids and d["id"] not in dup_ids]
            legacy = [d for d in legacy if d["id"] not in merge_ids and d["id"] not in dup_ids]
            dup_deletes = [d for d in dup_deletes if d["id"] not in merge_ids]
            pinned_excluded = sum(1 for r in rows if r.get("pinned"))
            return {
                "merge_groups": merge_groups,
                "delete_candidates": dup_deletes + standard,
                "legacy_delete_candidates": legacy,
                "pinned_count": pinned_excluded,
                "total_count": len(rows),
            }
        finally:
            conn.close()

    def run_organize(
        self,
        *,
        merge_group_ids: Optional[List[List[int]]] = None,
        delete_ids: Optional[List[int]] = None,
    ) -> dict:
        """
        执行用户确认后的整理：按组合并、按 id 删除。
        merge_group_ids: 每组为要合并的 id 列表
        """
        merge_group_ids = merge_group_ids or []
        delete_ids = delete_ids or []
        stats = {
            "merged_groups": 0,
            "merged_from_rows": 0,
            "deleted_count": 0,
            "errors": [],
        }
        conn = sqlite3.connect(str(self.db_path))
        try:
            for id_list in merge_group_ids:
                if len(id_list) < ORGANIZE_MERGE_MIN_CLUSTER:
                    continue
                placeholders = ",".join("?" * len(id_list))
                rows = conn.execute(
                    f"SELECT id, content, topic, created_at FROM memories WHERE id IN ({placeholders})",
                    id_list,
                ).fetchall()
                cluster = [
                    {"id": r[0], "content": r[1] or "", "topic": r[2], "created_at": r[3] or ""}
                    for r in rows
                ]
                if len(cluster) < ORGANIZE_MERGE_MIN_CLUSTER:
                    continue
                n_before = len(cluster)
                if self._merge_cluster(conn, cluster, force=True):
                    stats["merged_groups"] += 1
                    stats["merged_from_rows"] += n_before
                else:
                    stats["errors"].append(f"合并失败 ids={id_list}")
            for did in delete_ids:
                row = conn.execute(
                    "SELECT pinned, ref_count FROM memories WHERE id=?", (did,)
                ).fetchone()
                if not row:
                    continue
                if row[0]:
                    stats["errors"].append(f"跳过已保留 id={did}")
                    continue
                conn.execute("DELETE FROM memories WHERE id=?", (did,))
                stats["deleted_count"] += 1
            conn.commit()
        except Exception as e:
            stats["errors"].append(str(e))
        finally:
            conn.close()
        return stats

    def get_by_id(self, id: int) -> Optional[dict]:
        """按 id 查询一条记忆"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute(
                """SELECT id, content, created_at, updated_at, topic, ref_count,
                          COALESCE(pinned, 0) FROM memories WHERE id=?""",
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
                "ref_count": row[5],
                "pinned": int(row[6] or 0),
            }
        finally:
            conn.close()

    def update_content_by_id(self, id: int, new_content: str) -> bool:
        """更新正文并刷新 embedding 与 updated_at"""
        new_content = (new_content or "").strip()
        if not new_content:
            return False
        vec = self._get_embedding(new_content)
        if vec is None:
            return False
        now = _utc_now_iso()
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
        """返回所有记忆，供管理 UI 使用"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            return self._fetch_all_rows(conn)
        finally:
            conn.close()

    def is_merge_llm_available(self) -> bool:
        """整理合并是否可调用 LLM"""
        return self._merge_llm_caller is not None
