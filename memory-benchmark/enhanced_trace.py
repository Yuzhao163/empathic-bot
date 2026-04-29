#!/usr/bin/env python3
"""
Memory Benchmark - 增强版详细过程追踪
输出每个系统每一步的具体行为，而非只有统计结果
"""

import json
import sys
import time
import random
import math
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from conversation_generator import ConversationGenerator


# ==================== 增强的记忆系统实现 ====================

class TraceMemorySystem:
    """带详细追踪的记忆系统基类"""

    def __init__(self, name, system_type):
        self.name = name
        self.system_type = system_type
        self.records = {}
        self.store_trace = []   # 每一次存储的详细记录
        self.recall_trace = []  # 每一次召回的详细记录
        self.state_snapshots = []  # 每个关键时间点的状态快照
        self.current_day = 0
        self._stats = {"stores": 0, "recalls": 0, "dedup": 0}

    def _new_record_id(self, turn_id):
        return f"{self.name.lower().replace('-', '_').replace(' ', '_')}_{turn_id}"

    def _snapshot(self, day, event):
        self.state_snapshots.append({
            "day": day,
            "event": event,
            "record_count": len(self.records),
            "timestamp": datetime.now().isoformat()
        })

    def store(self, content, category, importance, day, turn_id, topic, tags=None):
        raise NotImplementedError

    def recall(self, query, limit=5, day=None):
        raise NotImplementedError

    def get_all_traces(self):
        return {
            "system": self.name,
            "type": self.system_type,
            "store_trace": self.store_trace,
            "recall_trace": self.recall_trace,
            "state_snapshots": self.state_snapshots,
            "final_stats": {
                "total_stored": len(self.records),
                "total_store_ops": self._stats["stores"],
                "total_recall_ops": self._stats["recalls"],
                "deduplications": self._stats["dedup"],
            }
        }


class FileMemory(TraceMemorySystem):
    """文件记忆系统"""

    def __init__(self):
        super().__init__("Memory-File", "file-based")
        self.by_category = {"preference": [], "decision": [], "fact": [], "error": [], "recall_trigger": []}
        self.by_day = {}
        self.file_index = {}  # content_hash -> record_id

    def store(self, content, category, importance, day, turn_id, topic, tags=None):
        start = time.perf_counter()

        # 去重检查
        content_hash = hash(content)
        if content_hash in self.file_index:
            self._stats["dedup"] += 1
            dup_id = self.file_index[content_hash]
            self.store_trace.append({
                "day": day, "turn_id": turn_id, "event": "DEDUP",
                "content_preview": content[:40],
                "Bulled_record_id": dup_id,
                "latency_ms": (time.perf_counter() - start) * 1000
            })
            return

        record_id = self._new_record_id(turn_id)
        record = {
            "id": record_id,
            "content": content,
            "category": category,
            "importance": importance,
            "day": day,
            "turn_id": turn_id,
            "topic": topic,
            "tags": tags or [],
            "content_hash": content_hash
        }

        self.records[record_id] = record
        self.by_category.setdefault(category, []).append(record_id)
        self.by_day.setdefault(day, []).append(record_id)
        self.file_index[content_hash] = record_id
        self._stats["stores"] += 1

        latency = (time.perf_counter() - start) * 1000

        # 写入文件的模拟操作
        self.store_trace.append({
            "day": day, "turn_id": turn_id, "event": "STORE",
            "record_id": record_id,
            "category": category,
            "importance": importance,
            "content_preview": content[:50],
            "file_path": f"memory/by_category/{category}/{record_id}.json",
            "latency_ms": round(latency, 3),
            "day_record_count": len(self.by_day.get(day, [])),
            "total_records": len(self.records)
        })

        if day != self.current_day:
            self.current_day = day
            self._snapshot(day, f"new_day_store_count={len(self.by_day.get(day, []))}")

    def recall(self, query, limit=5, day=None):
        start = time.perf_counter()
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored = []
        for rid, record in self.records.items():
            if day and record["day"] != day:
                continue
            content_words = set(record["content"].lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                score = overlap / len(query_words)
                scored.append((score, record))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = scored[:limit]

        latency = (time.perf_counter() - start) * 1000
        self._stats["recalls"] += 1

        self.recall_trace.append({
            "query": query[:60],
            "query_words": list(query_words),
            "results_count": len(results),
            "top_results": [
                {
                    "record_id": r["id"],
                    "content_preview": r["content"][:50],
                    "score": round(s, 3),
                    "category": r["category"],
                    "day": r["day"]
                } for s, r in results
            ],
            "latency_ms": round(latency, 3),
            "method": "keyword_match"
        })

        return [r for _, r in results]


class QdrantMemory(TraceMemorySystem):
    """Qdrant向量记忆系统"""

    def __init__(self):
        super().__init__("Memory-Qdrant", "vector_database")
        self.vectors = {}  # record_id -> (mock_vector, record)
        self.collection_info = {"name": "benchmark_memory", "dim": 384, "vectors_count": 0}

    def _mock_embed(self, text):
        """生成伪向量 - 基于内容生成固定seed的向量"""
        random.seed(hash(text) % (2**31))
        return [random.uniform(-1, 1) for _ in range(384)]

    def _cosine_sim(self, v1, v2):
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        return dot / (norm1 * norm2) if norm1 and norm2 else 0

    def store(self, content, category, importance, day, turn_id, topic, tags=None):
        start = time.perf_counter()

        # 内容去重
        for rid, (vec, rec) in self.vectors.items():
            if rec["content"] == content:
                self._stats["dedup"] += 1
                self.store_trace.append({
                    "day": day, "turn_id": turn_id, "event": "DEDUP",
                    "content_preview": content[:40],
                    "dedup_record_id": rid,
                    "latency_ms": (time.perf_counter() - start) * 1000
                })
                return

        record_id = self._new_record_id(turn_id)
        vector = self._mock_embed(content)

        record = {
            "id": record_id,
            "content": content,
            "category": category,
            "importance": importance,
            "day": day,
            "turn_id": turn_id,
            "topic": topic,
            "vector_norm": round(math.sqrt(sum(v*v for v in vector)), 3)
        }

        self.vectors[record_id] = (vector, record)
        self.collection_info["vectors_count"] = len(self.vectors)
        self._stats["stores"] += 1

        latency = (time.perf_counter() - start) * 1000 + 8.0  # 向量生成开销

        self.store_trace.append({
            "day": day, "turn_id": turn_id, "event": "STORE",
            "record_id": record_id,
            "category": category,
            "importance": importance,
            "vector_preview": vector[:5],
            "vector_norm": record["vector_norm"],
            "collection": f"{self.collection_info['name']} ({self.collection_info['vectors_count']} vectors)",
            "latency_ms": round(latency, 3),
            "total_vectors": self.collection_info["vectors_count"]
        })

        if day != self.current_day:
            self.current_day = day
            self._snapshot(day, f"collection_size={self.collection_info['vectors_count']}")

    def recall(self, query, limit=5, day=None):
        start = time.perf_counter()
        query_vector = self._mock_embed(query)

        scored = []
        for rid, (vec, record) in self.vectors.items():
            if day and record["day"] != day:
                continue
            sim = self._cosine_sim(query_vector, vec)
            # 综合评分：向量相似度*0.4 + 重要性*0.3 + 时效性*0.3
            recency = 1.0 - (30 - record["day"]) / 30
            score = sim * 0.4 + record["importance"] * 0.3 + recency * 0.3
            scored.append((score, sim, record))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = scored[:limit]

        latency = (time.perf_counter() - start) * 1000 + 12.0
        self._stats["recalls"] += 1

        self.recall_trace.append({
            "query": query[:60],
            "results_count": len(results),
            "top_results": [
                {
                    "record_id": r["id"],
                    "content_preview": r["content"][:50],
                    "cosine_sim": round(sim, 3),
                    "final_score": round(score, 3),
                    "importance": r["importance"],
                    "day": r["day"]
                } for score, sim, r in results
            ],
            "latency_ms": round(latency, 3),
            "method": "dense_vector_cosine_similarity",
            "vector_dim": self.collection_info["dim"]
        })

        return [r for _, _, r in results]


class LettaMemory(TraceMemorySystem):
    """Letta分层记忆系统"""

    def __init__(self):
        super().__init__("Letta", "layered_memory")
        self.core_memory = []  # 高优先级，常驻
        self.archival_memory = []
        self.recall_index = []
        self.core_token_limit = 500
        self.core_tokens = 0

    def _estimate_tokens(self, content):
        return len(content.split()) * 1.3

    def store(self, content, category, importance, day, turn_id, topic, tags=None):
        start = time.perf_counter()

        record = {
            "id": self._new_record_id(turn_id),
            "content": content,
            "category": category,
            "importance": importance,
            "day": day,
            "turn_id": turn_id,
            "topic": topic,
            "tokens": self._estimate_tokens(content)
        }

        self._stats["stores"] += 1

        # 分层决策
        if importance > 0.85:
            # 放入核心记忆
            if self.core_tokens + record["tokens"] > self.core_token_limit:
                # 压缩核心记忆
                sorted_core = sorted(self.core_memory, key=lambda r: r["importance"], reverse=True)
                kept = []
                moved = []
                accumulated = 0
                for r in sorted_core:
                    if accumulated + r["tokens"] <= self.core_token_limit * 0.6:
                        kept.append(r)
                        accumulated += r["tokens"]
                    else:
                        moved.append(r)
                self.core_memory = kept
                self.archival_memory.extend(moved)
                compacts = len(moved)

                self.store_trace.append({
                    "day": day, "turn_id": turn_id, "event": "CORE_COMPACT",
                    "core_count_before": len(kept) + len(moved),
                    "core_count_after": len(kept),
                    "moved_to_archival": compacts,
                    "tokens_before": accumulated + sum(r["tokens"] for r in moved),
                    "tokens_after": accumulated
                })
            else:
                compacts = 0

            self.core_memory.append(record)
            self.core_tokens = sum(r["tokens"] for r in self.core_memory)
            layer = "CORE"
        else:
            self.archival_memory.append(record)
            layer = "ARCHIVAL"
            compacts = 0

        self.recall_index.append(record)

        latency = (time.perf_counter() - start) * 1000 + 5.0

        self.store_trace.append({
            "day": day, "turn_id": turn_id, "event": "STORE",
            "record_id": record["id"],
            "layer": layer,
            "importance": importance,
            "tokens": round(record["tokens"], 1),
            "content_preview": content[:50],
            "core_memory_size": len(self.core_memory),
            "core_tokens_used": round(self.core_tokens, 1),
            "core_token_limit": self.core_token_limit,
            "archival_size": len(self.archival_memory),
            "compact_triggered": compacts > 0,
            "latency_ms": round(latency, 3)
        })

        if day != self.current_day:
            self.current_day = day
            self._snapshot(day, f"core={len(self.core_memory)}({round(self.core_tokens)}tok), arch={len(self.archival_memory)}")

    def recall(self, query, limit=5, day=None):
        start = time.perf_counter()
        query_words = set(query.lower().split())

        all_records = self.recall_index

        scored = []
        for record in all_records:
            content_words = set(record["content"].lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                base_score = overlap / len(query_words)
                # 核心记忆加权
                in_core = record in self.core_memory
                score = base_score * (1.3 if in_core else 1.0)
                scored.append((score, record))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = scored[:limit]

        latency = (time.perf_counter() - start) * 1000 + 10.0
        self._stats["recalls"] += 1

        self.recall_trace.append({
            "query": query[:60],
            "query_words": list(query_words),
            "results_count": len(results),
            "top_results": [
                {
                    "record_id": r["id"],
                    "content_preview": r["content"][:50],
                    "layer": "CORE" if r in self.core_memory else "ARCHIVAL",
                    "score": round(s, 3),
                    "importance": r["importance"],
                    "day": r["day"]
                } for s, r in results
            ],
            "core_in_results": sum(1 for _, r in scored[:limit] if r in self.core_memory),
            "latency_ms": round(latency, 3),
            "method": "layered_search_core优先"
        })

        return [r for _, r in results]


class FluidMemory(TraceMemorySystem):
    """Fluid记忆 - 遗忘曲线系统"""

    def __init__(self):
        super().__init__("FluidMem", "ebbinghaus_decay")
        self.records = {}
        self.decay_rate = 0.1
        self.access_boost = 0.05

    def _calc_strength(self, record, current_day):
        days_since = current_day - record["day"]
        base = math.exp(-days_since * self.decay_rate)
        access = 1 + record.get("access_count", 0) * self.access_boost
        return min(base * access, 1.0)

    def store(self, content, category, importance, day, turn_id, topic, tags=None):
        start = time.perf_counter()

        # 去重
        for rid, rec in self.records.items():
            if rec["content"] == content:
                self._stats["dedup"] += 1
                self.store_trace.append({
                    "day": day, "turn_id": turn_id, "event": "DEDUP",
                    "content_preview": content[:40],
                    "existing_record_id": rid,
                    "latency_ms": (time.perf_counter() - start) * 1000
                })
                return

        record = {
            "id": self._new_record(turn_id),
            "content": content,
            "category": category,
            "importance": importance,
            "day": day,
            "turn_id": turn_id,
            "topic": topic,
            "access_count": 0,
            "strength_history": [(day, 1.0)]  # 初始强度
        }

        self.records[record["id"]] = record
        self._stats["stores"] += 1

        strength = self._calc_strength(record, day)
        latency = (time.perf_counter() - start) * 1000 + 3.0

        self.store_trace.append({
            "day": day, "turn_id": turn_id, "event": "STORE",
            "record_id": record["id"],
            "category": category,
            "importance": importance,
            "initial_strength": round(strength, 4),
            "content_preview": content[:50],
            "total_records": len(self.records),
            "latency_ms": round(latency, 3)
        })

        if day != self.current_day:
            self.current_day = day
            self._snapshot(day, f"records={len(self.records)}")

    def recall(self, query, limit=5, day=None):
        start = time.perf_counter()
        current_day = day or 30
        query_words = set(query.lower().split())

        scored = []
        for record in self.records.values():
            content_words = set(record["content"].lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                keyword_score = overlap / len(query_words)
                strength = self._calc_strength(record, current_day)
                # 最终分数 = 关键词分 × 记忆强度 × 重要性
                score = keyword_score * strength * (0.5 + record["importance"] * 0.5)

                # 强化：访问次数+1
                record["access_count"] += 1
                record["strength_history"].append((current_day, self._calc_strength(record, current_day)))

                scored.append((score, strength, record))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = scored[:limit]

        latency = (time.perf_counter() - start) * 1000 + 5.0
        self._stats["recalls"] += 1

        self.recall_trace.append({
            "query": query[:60],
            "current_day": current_day,
            "results_count": len(results),
            "top_results": [
                {
                    "record_id": r["id"],
                    "content_preview": r["content"][:50],
                    "keyword_score": round(keyword_score, 3),
                    "strength": round(str, 4),
                    "strength_after_access": round(self._calc_strength(r, current_day), 4),
                    "access_count": r["access_count"],
                    "importance": r["importance"],
                    "final_score": round(score, 4),
                    "day": r["day"]
                } for score, str, r in results
            ],
            "latency_ms": round(latency, 3),
            "method": "ebbinghaus_decay_curve"
        })

        return [r for _, _, r in results]

    def _new_record_id(self, turn_id):
        return f"fluid_{turn_id}"


class NeuralMemory(TraceMemorySystem):
    """Neural联想记忆 - 图谱系统"""

    def __init__(self):
        super().__init__("NeuralMem", "associative_graph")
        self.records = {}
        self.synapses = {}  # record_id -> [connected_record_ids]
        self.synapse_log = []
        self.synapse_types = ["BEFORE", "AFTER", "CAUSED_BY", "LEADS_TO", "IS_A", "HAS_PROPERTY", "RELATED"]

    def _build_synapses(self, new_record, existing_records):
        connections = []
        new_words = set(new_record["content"].lower().split())

        for existing in existing_records[-30:]:
            if existing["id"] == new_record["id"]:
                continue
            existing_words = set(existing["content"].lower().split())
            overlap = len(new_words & existing_words)

            if overlap > 0:
                synapse_type = self.synapse_types[overlap % len(self.synapse_types)]
                strength = overlap / max(len(new_words), len(existing_words))
                connections.append({
                    "to": existing["id"],
                    "type": synapse_type,
                    "strength": round(strength, 3),
                    "shared_words": overlap
                })
                self.synapse_log.append({
                    "from": new_record["id"],
                    "to": existing["id"],
                    "type": synapse_type,
                    "strength": round(strength, 3)
                })

        return connections

    def store(self, content, category, importance, day, turn_id, topic, tags=None):
        start = time.perf_counter()

        record = {
            "id": self._new_record_id(turn_id),
            "content": content,
            "category": category,
            "importance": importance,
            "day": day,
            "turn_id": turn_id,
            "topic": topic,
            "synapse_count": 0
        }

        # 建突触连接
        connections = self._build_synapses(record, list(self.records.values()))
        self.synapses[record["id"]] = [c["to"] for c in connections]
        record["synapse_count"] = len(connections)

        self.records[record["id"]] = record
        self._stats["stores"] += 1

        latency = (time.perf_counter() - start) * 1000 + 8.0

        self.store_trace.append({
            "day": day, "turn_id": turn_id, "event": "STORE",
            "record_id": record["id"],
            "category": category,
            "importance": importance,
            "content_preview": content[:50],
            "new_synapses_created": len(connections),
            "synapse_types_used": list(set(c["type"] for c in connections)),
            "total_nodes": len(self.records),
            "total_synapses": sum(len(v) for v in self.synapses.values()),
            "latency_ms": round(latency, 3)
        })

        if day != self.current_day:
            self.current_day = day
            self._snapshot(day, f"nodes={len(self.records)}, synapses={sum(len(v) for v in self.synapses.values())}")

    def recall(self, query, limit=5, day=None):
        start = time.perf_counter()
        query_words = set(query.lower().split())

        # 第一层：直接匹配
        direct_scores = {}
        for rid, record in self.records.items():
            if day and record["day"] != day:
                continue
            content_words = set(record["content"].lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                direct_scores[rid] = (overlap / len(query_words), record)

        # 第二层：突触扩散
        activated = dict(direct_scores)
        for rid, (score, _) in direct_scores.items():
            for synapse_id in self.synapses.get(rid, []):
                if synapse_id in self.records:
                    activated[synapse_id] = (
                        activated.get(synapse_id, (0, None))[0] + score * 0.3,
                        self.records[synapse_id]
                    )

        scored = [(s, r) for r, (s, _) in [(rid, (score, rec)) for rid, (score, rec) in activated.items()]]
        scored.sort(key=lambda x: x[0], reverse=True)
        results = scored[:limit]

        latency = (time.perf_counter() - start) * 1000 + 15.0
        self._stats["recalls"] += 1

        self.recall_trace.append({
            "query": query[:60],
            "query_words": list(query_words),
            "direct_hits": len(direct_scores),
            "spread_activations": len(activated) - len(direct_scores),
            "results_count": len(results),
            "top_results": [
                {
                    "record_id": r["id"],
                    "content_preview": r["content"][:50],
                    "activation_score": round(s, 3),
                    "synapse_connections": len(self.synapses.get(r["id"], [])),
                    "category": r["category"],
                    "day": r["day"]
                } for s, r in results
            ],
            "latency_ms": round(latency, 3),
            "method": "spreading_activation_graph"
        })

        return [r for _, r in results]

    def _new_record_id(self, turn_id):
        return f"neural_{turn_id}"


class Mem0Memory(TraceMemorySystem):
    """Mem0 - 模拟语义记忆"""

    def __init__(self):
        super().__init__("mem0", "vector_semantic")
        self.records = {}
        self.user_id = "benchmark_user"

    def store(self, content, category, importance, day, turn_id, topic, tags=None):
        start = time.perf_counter()

        record = {
            "id": self._new_record_id(turn_id),
            "content": content,
            "category": category,
            "importance": importance,
            "day": day,
            "turn_id": turn_id,
            "topic": topic,
            "metadata": {
                "user_id": self.user_id,
                "category": category,
                "importance": importance,
                "topic": topic,
                "tags": tags or []
            }
        }

        self.records[record["id"]] = record
        self._stats["stores"] += 1

        # 模拟 API 调用
        latency = (time.perf_counter() - start) * 1000 + 15.0

        self.store_trace.append({
            "day": day, "turn_id": turn_id, "event": "API_STORE",
            "record_id": record["id"],
            "category": category,
            "importance": importance,
            "content_preview": content[:50],
            "api_endpoint": "POST /v1/memories",
            "embedding_model": "text-embedding-3-small",
            "storage_backend": "Qdrant (cloud)",
            "deduplicated": False,  # 模拟不做去重
            "latency_ms": round(latency, 3),
            "total_memories": len(self.records)
        })

        if day != self.current_day:
            self.current_day = day
            self._snapshot(day, f"total_memories={len(self.records)}")

    def recall(self, query, limit=5, day=None):
        start = time.perf_counter()

        # 模拟语义检索：基于关键词+语义相似度
        query_words = set(query.lower().split())
        scored = []

        for record in self.records.values():
            content_words = set(record["content"].lower().split())
            overlap = len(query_words & content_words)

            # 模拟语义分数：关键词重叠 + 随机语义相关(因为真实API会理解含义)
            semantic_boost = 0.2 if any(w in record["content"].lower() for w in query_words) else 0
            score = (overlap / len(query_words) if query_words else 0) + semantic_boost

            if score > 0:
                scored.append((score, record))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = scored[:limit]

        # 模拟 API 调用延迟
        latency = (time.perf_counter() - start) * 1000 + 80.0
        self._stats["recalls"] += 1

        self.recall_trace.append({
            "query": query[:60],
            "results_count": len(results),
            "top_results": [
                {
                    "record_id": r["id"],
                    "content_preview": r["content"][:50],
                    "semantic_score": round(s, 3),
                    "category": r["category"],
                    "importance": r["importance"],
                    "day": r["day"]
                } for s, r in results
            ],
            "latency_ms": round(latency, 3),
            "method": "semantic_search_api",
            "api_endpoint": "GET /v1/memories/search",
            "note": "实际API会返回embedding相似度更高但无关键词重叠的结果"
        })

        return [r for _, r in results]

    def _new_record_id(self, turn_id):
        return f"mem0_{turn_id}"


class MnemonicMemory(TraceMemorySystem):
    """Mnemonic - Claude Code文件系统记忆，YAML frontmatter + bi-temporal"""

    def __init__(self):
        super().__init__("Mnemonic", "file_yaml_bitemporal")
        self.files = {}  # file_path -> content_with_yaml
        self.bi_temporal_log = []  # valid_time, tx_time records

    def store(self, content, category, importance, day, turn_id, topic, tags=None):
        start = time.perf_counter()

        file_path = f"memory/{category}/{topic}_{turn_id}.md"
        yaml_frontmatter = f"""---
valid_from: "2026-03-{day:02d}"
tx_time: "{datetime.now().isoformat()}"
category: {category}
importance: {importance}
tags: {tags or []}
topic: {topic}
turn_id: {turn_id}
---
"""
        file_content = yaml_frontmatter + content

        record_id = self._new_record_id(turn_id)
        record = {
            "id": record_id,
            "content": content,
            "yaml": yaml_frontmatter,
            "file_path": file_path,
            "category": category,
            "importance": importance,
            "day": day,
            "turn_id": turn_id,
            "topic": topic,
            "valid_from": f"2026-03-{day:02d}"
        }

        self.files[file_path] = record
        self.bi_temporal_log.append({
            "tx_time": datetime.now().isoformat(),
            "valid_from": f"2026-03-{day:02d}",
            "file": file_path,
            "action": "CREATE"
        })
        self._stats["stores"] += 1

        latency = (time.perf_counter() - start) * 1000 + 1.0

        self.store_trace.append({
            "day": day, "turn_id": turn_id, "event": "WRITE_FILE",
            "record_id": record_id,
            "file_path": file_path,
            "category": category,
            "importance": importance,
            "yaml_preview": yaml_frontmatter[:80],
            "content_preview": content[:40],
            "valid_time": f"2026-03-{day:02d}",
            "tx_time": "current",
            "total_files": len(self.files),
            "latency_ms": round(latency, 3)
        })

        if day != self.current_day:
            self.current_day = day
            self._snapshot(day, f"files={len(self.files)}")

    def recall(self, query, limit=5, day=None):
        start = time.perf_counter()
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored = []
        for fp, record in self.files.items():
            content_words = set(record["content"].lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                # bi-temporal: 支持按有效时间过滤
                score = overlap / len(query_words)
                scored.append((score, record))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = scored[:limit]

        latency = (time.perf_counter() - start) * 1000 + 2.0
        self._stats["recalls"] += 1

        self.recall_trace.append({
            "query": query[:60],
            "results_count": len(results),
            "top_results": [
                {
                    "file_path": r["file_path"],
                    "content_preview": r["content"][:50],
                    "valid_from": r["valid_from"],
                    "score": round(s, 3),
                    "category": r["category"]
                } for s, r in results
            ],
            "latency_ms": round(latency, 3),
            "method": "grep_yaml_metadata"
        })

        return [r for _, r in results]

    def _new_record_id(self, turn_id):
        return f"mnemonic_{turn_id}"


class MemPMemory(TraceMemorySystem):
    """MemP - 程序性记忆系统，记忆操作步骤序列"""

    def __init__(self):
        super().__init__("MemP", "procedural")
        self.episodes = {}  # episode_id -> steps
        self.procedures = {}  # pattern -> learned_procedure
        self.current_episode = []

    def store(self, content, category, importance, day, turn_id, topic, tags=None):
        start = time.perf_counter()

        # 收集为 episode
        step = {
            "step_id": f"{turn_id}",
            "content": content,
            "category": category,
            "day": day,
            "turn_id": turn_id
        }
        self.current_episode.append(step)

        record_id = self._new_record_id(turn_id)
        record = {
            "id": record_id,
            "content": content,
            "category": category,
            "importance": importance,
            "day": day,
            "turn_id": turn_id,
            "topic": topic,
            "episode_id": f"ep_{day}",
            "step_in_episode": len(self.current_episode)
        }

        self._stats["stores"] += 1

        latency = (time.perf_counter() - start) * 1000 + 2.0

        self.store_trace.append({
            "day": day, "turn_id": turn_id, "event": "APPEND_STEP",
            "record_id": record_id,
            "category": category,
            "content_preview": content[:50],
            "episode_id": f"ep_{day}",
            "step_number": len(self.current_episode),
            "episode_length": len(self.current_episode),
            "latency_ms": round(latency, 3)
        })

        # 每10步或新的一天，固化episode
        if len(self.current_episode) >= 10 or day != self.current_day:
            episode_id = f"ep_{day}"
            self.episodes[episode_id] = list(self.current_episode)
            self.store_trace.append({
                "day": day, "turn_id": turn_id, "event": "EPISODE_COMMIT",
                "episode_id": episode_id,
                "episode_length": len(self.current_episode),
                "total_episodes": len(self.episodes)
            })
            self.current_episode = []

        if day != self.current_day:
            self.current_day = day
            self._snapshot(day, f"episodes={len(self.episodes)}, proc={len(self.procedures)}")

    def recall(self, query, limit=5, day=None):
        start = time.perf_counter()
        query_words = set(query.lower().split())

        scored = []
        for ep_id, episode in self.episodes.items():
            for step in episode:
                content_words = set(step["content"].lower().split())
                overlap = len(query_words & content_words)
                if overlap > 0:
                    score = overlap / len(query_words)
                    scored.append((score, step, ep_id))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = scored[:limit]

        latency = (time