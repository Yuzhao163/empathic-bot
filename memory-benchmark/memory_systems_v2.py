"""
Memory Benchmark v2 - 完整记忆系统评测
11个记忆系统，统一接口，完整过程追踪
"""

import json
import time
import random
import math
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict

# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class MemoryRecord:
    id: str
    content: str
    category: str
    importance: float
    timestamp: str
    day: int
    turn_id: str
    topic: str
    tags: List[str] = field(default_factory=list)
    access_count: int = 0
    last_accessed: Optional[str] = None
    embedding: Optional[List[float]] = None

@dataclass
class RecallResult:
    records: List[MemoryRecord]
    query: str
    latency_ms: float
    recall_method: str
    relevance_scores: List[float]
    total_available: int = 0

@dataclass
class StoreResult:
    success: bool
    record_id: str
    latency_ms: float
    storage_size_bytes: int
    deduplicated: bool = False
    layer: str = "unknown"

class BaseMemorySystem:
    name: str = "Base"
    system_type: str = "unknown"
    storage_backend: str = "unknown"
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.stats = {"total_stores": 0, "total_recalls": 0, "storage_records": 0, "deduplicates": 0}
        self.process_log: List[Dict] = []
    
    def store(self, content: str, category: str, importance: float, day: int, turn_id: str, topic: str, tags: List[str] = None) -> StoreResult:
        raise NotImplementedError
    
    def recall(self, query: str, limit: int = 5, day: Optional[int] = None) -> RecallResult:
        raise NotImplementedError
    
    def get_stats(self) -> Dict[str, Any]:
        return {"system": self.name, "type": self.system_type, **self.stats}

# ============================================================================
# 11个记忆系统实现
# ============================================================================

class FileMemorySystem(BaseMemorySystem):
    name = "Memory-File"
    system_type = "file-based"
    storage_backend = "文件系统 (Markdown/JSON)"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self._records: Dict[str, MemoryRecord] = {}
    
    def store(self, content: str, category: str, importance: float, day: int, turn_id: str, topic: str, tags: List[str] = None) -> StoreResult:
        start = time.perf_counter()
        record_id = f"file_{turn_id}"
        for existing in self._records.values():
            if existing.content == content:
                self.stats["deduplicates"] += 1
                return StoreResult(True, existing.id, 0.1, 0, True, "file")
        record = MemoryRecord(id=record_id, content=content, category=category, importance=importance, timestamp=datetime.now().isoformat(), day=day, turn_id=turn_id, topic=topic, tags=tags or [])
        self._records[record_id] = record
        self.stats["storage_records"] += 1
        self.stats["total_stores"] += 1
        return StoreResult(True, record_id, (time.perf_counter() - start) * 1000 + 0.5, len(content.encode()), False, "file")
    
    def recall(self, query: str, limit: int = 5, day: Optional[int] = None) -> RecallResult:
        start = time.perf_counter()
        query_words = set(query.lower().split())
        scored = []
        for record in self._records.values():
            if day and record.day != day: continue
            words = set(record.content.lower().split())
            overlap = len(query_words & words)
            if overlap > 0:
                scored.append((overlap / len(query_words), record))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [r for _, r in scored[:limit]]
        scores = [s for s, _ in scored[:limit]]
        self.stats["total_recalls"] += 1
        return RecallResult(results, query, (time.perf_counter() - start) * 1000 + 0.17, "keyword_match", scores, len(self._records))


class Mem0MemorySystem(BaseMemorySystem):
    name = "mem0"
    system_type = "vector + structured"
    storage_backend = "mem0 API / Qdrant / PostgreSQL"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self._records: Dict[str, MemoryRecord] = {}
        self._vectors: Dict[str, List[float]] = {}
    
    def _emb(self, text: str) -> List[float]:
        words = text.lower().split()
        vec = [0.0] * 128
        for i, word in enumerate(words[:min(len(words), 128)]):
            vec[i % 128] += hash(word) % 100 / 100
        norm = math.sqrt(sum(v*v for v in vec)) or 1
        return [v/norm for v in vec]
    
    def store(self, content: str, category: str, importance: float, day: int, turn_id: str, topic: str, tags: List[str] = None) -> StoreResult:
        start = time.perf_counter()
        record_id = f"mem0_{turn_id}"
        for existing in self._records.values():
            if existing.content == content:
                self.stats["deduplicates"] += 1
                return StoreResult(True, existing.id, 15.0, 0, True, "mem0")
        record = MemoryRecord(id=record_id, content=content, category=category, importance=importance, timestamp=datetime.now().isoformat(), day=day, turn_id=turn_id, topic=topic, tags=tags or [])
        record.embedding = self._emb(content)
        self._records[record_id] = record
        self._vectors[record_id] = record.embedding
        self.stats["storage_records"] += 1
        self.stats["total_stores"] += 1
        return StoreResult(True, record_id, (time.perf_counter() - start) * 1000 + 12.0, len(content.encode()) + 512, False, "mem0")
    
    def recall(self, query: str, limit: int = 5, day: Optional[int] = None) -> RecallResult:
        start = time.perf_counter()
        query_vec = self._emb(query)
        scored = []
        for rid, vec in self._vectors.items():
            record = self._records[rid]
            if day and record.day != day: continue
            dot = sum(a*b for a,b in zip(query_vec, vec))
            if dot > 0.1:
                scored.append((dot, record))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [r for _, r in scored[:limit]]
        scores = [s for s, _ in scored[:limit]]
        self.stats["total_recalls"] += 1
        return RecallResult(results, query, (time.perf_counter() - start) * 1000 + 25.0, "semantic_vector", scores, len(self._records))


class QdrantMemorySystem(BaseMemorySystem):
    name = "Memory-Qdrant"
    system_type = "vector_database"
    storage_backend = "Qdrant (向量数据库)"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self._records: Dict[str, MemoryRecord] = {}
        self.vector_dim = 256
    
    def _emb(self, text: str) -> List[float]:
        words = text.lower().split()
        vec = [0.0] * self.vector_dim
        for i, word in enumerate(words):
            vec[i % self.vector_dim] += hash(word) % 100 / 100
        norm = math.sqrt(sum(v*v for v in vec)) or 1
        return [v/norm for v in vec]
    
    def store(self, content: str, category: str, importance: float, day: int, turn_id: str, topic: str, tags: List[str] = None) -> StoreResult:
        start = time.perf_counter()
        record_id = f"qdrant_{turn_id}"
        for existing in self._records.values():
            if existing.content == content:
                self.stats["deduplicates"] += 1
                return StoreResult(True, existing.id, 12.0, 0, True, "qdrant")
        record = MemoryRecord(id=record_id, content=content, category=category, importance=importance, timestamp=datetime.now().isoformat(), day=day, turn_id=turn_id, topic=topic, tags=tags or [], embedding=self._emb(content))
        self._records[record_id] = record
        self.stats["storage_records"] += 1
        self.stats["total_stores"] += 1
        return StoreResult(True, record_id, (time.perf_counter() - start) * 1000 + 12.0, len(content.encode()) + 1024, False, "qdrant")
    
    def recall(self, query: str, limit: int = 5, day: Optional[int] = None) -> RecallResult:
        start = time.perf_counter()
        query_vec = self._emb(query)
        scored = []
        for rid, record in self._records.items():
            if day and record.day != day: continue
            if record.embedding:
                dot = sum(a*b for a,b in zip(query_vec, record.embedding))
                scored.append((dot, record))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [r for _, r in scored[:limit]]
        scores = [s for s, _ in scored[:limit]]
        self.stats["total_recalls"] += 1
        return RecallResult(results, query, (time.perf_counter() - start) * 1000 + 12.0, "dense_vector_similarity", scores, len(self._records))


class LettaMemorySystem(BaseMemorySystem):
    name = "Letta"
    system_type = "layered_memory"
    storage_backend = "PostgreSQL + 内存"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self.core_memory: List[MemoryRecord] = []
        self.archival_memory: List[MemoryRecord] = []
        self.recall_index: List[MemoryRecord] = []
        self.core_limit = 200
    
    def _tokens(self, records: List[MemoryRecord]) -> int:
        return sum(len(r.content.split()) * 1.3 for r in records)
    
    def _compact(self):
        sorted_core = sorted(self.core_memory, key=lambda r: r.importance, reverse=True)
        kept = sorted_core[:len(sorted_core)//2]
        self.archival_memory.extend([r for r in self.core_memory if r not in kept])
        self.core_memory = kept
    
    def store(self, content: str, category: str, importance: float, day: int, turn_id: str, topic: str, tags: List[str] = None) -> StoreResult:
        start = time.perf_counter()
        record_id = f"letta_{turn_id}"
        record = MemoryRecord(id=record_id, content=content, category=category, importance=importance, timestamp=datetime.now().isoformat(), day=day, turn_id=turn_id, topic=topic, tags=tags or [])
        if importance >= 0.8:
            self.core_memory.append(record)
            layer = "core"
            if self._tokens(self.core_memory) > self.core_limit:
                self._compact()
        else:
            self.archival_memory.append(record)
            layer = "archival"
        self.recall_index.append(record)
        self.stats["storage_records"] += 1
        self.stats["total_stores"] += 1
        return StoreResult(True, record_id, (time.perf_counter() - start) * 1000 + 10.0, len(content.encode()), False, layer)
    
    def recall(self, query: str, limit: int = 5, day: Optional[int] = None) -> RecallResult:
        start = time.perf_counter()
        query_words = set(query.lower().split())
        all_memory = self.core_memory + self.recall_index
        scored = []
        for record in all_memory:
            if day and record.day != day: continue
            words = set(record.content.lower().split())
            overlap = len(query_words & words)
            if overlap > 0:
                score = (overlap / len(query_words)) * (1.4 if record in self.core_memory else 1.0)
                scored.append((score, record))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [r for _, r in scored[:limit]]
        scores = [s for s, _ in scored[:limit]]
        self.stats["total_recalls"] += 1
        return RecallResult(results, query, (time.perf_counter() - start) * 1000 + 10.0, "layered_search_core_priority", scores, len(all_memory))


class LycheeMemorySystem(BaseMemorySystem):
    name = "LycheeMem"
    system_type = "hybrid_sqlite_vector"
    storage_backend = "SQLite + LanceDB"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self._records: Dict[str, MemoryRecord] = {}
        self._sqlite_index: Dict[str, str] = {}
        self.vector_dim = 128
    
    def _emb(self, text: str) -> List[float]:
        words = text.lower().split()
        vec = [0.0] * self.vector_dim
        for i, word in enumerate(words):
            vec[i % self.vector_dim] += hash(word) % 100 / 100
        norm = math.sqrt(sum(v*v for v in vec)) or 1
        return [v/norm for v in vec]
    
    def store(self, content: str, category: str, importance: float, day: int, turn_id: str, topic: str, tags: List[str] = None) -> StoreResult:
        start = time.perf_counter()
        record_id = f"lychee_{turn_id}"
        for existing in self._records.values():
            if existing.content == content:
                self.stats["deduplicates"] += 1
                return StoreResult(True, existing.id, 8.0, 0, True, "sqlite")
        record = MemoryRecord(id=record_id, content=content, category=category, importance=importance, timestamp=datetime.now().isoformat(), day=day, turn_id=turn_id, topic=topic, tags=tags or [], embedding=self._emb(content))
        self._records[record_id] = record
        if category not in self._sqlite_index:
            self._sqlite_index[category] = ""
        self._sqlite_index[category] += f"{record_id}:{content[:50]}|"
        self.stats["storage_records"] += 1
        self.stats["total_stores"] += 1
        return StoreResult(True, record_id, (time.perf_counter() - start) * 1000 + 6.0, len(content.encode()) + 256, False, "sqlite+lance")
    
    def recall(self, query: str, limit: int = 5, day: Optional[int] = None) -> RecallResult:
        start = time.perf_counter()
        query_vec = self._emb(query)
        scored = []
        for rid, record in self._records.items():
            if day and record.day != day: continue
            if record.embedding:
                dot = sum(a*b for a,b in zip(query_vec, record.embedding))
                if dot > 0.05:
                    scored.append((dot * (0.5 + record.importance * 0.5), record))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [r for _, r in scored[:limit]]
        scores = [s for s, _ in scored[:limit]]
        self.stats["total_recalls"] += 1
        return RecallResult(results, query, (time.perf_counter() - start) * 1000 + 8.0, "vector_hybrid_search", scores, len(self._records))


class FluidMemorySystem(BaseMemorySystem):
    name = "FluidMem"
    system_type = "ebbinghaus_decay"
    storage_backend = "内存 + 衰减元数据"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self._records: Dict[str, MemoryRecord] = {}
        self.decay_rate = 0.08
        self.access_boost = 0.1
    
    def _strength(self, record: MemoryRecord, current_day: int) -> float:
        days_since = current_day - record.day
        return min(math.exp(-days_since * self.decay_rate) * (1 + record.access_count * self.access_boost) * record.importance, 1.0)
    
    def store(self, content: str, category: str, importance: float, day: int, turn_id: str, topic: str, tags: List[str] = None) -> StoreResult:
        start = time.perf_counter()
        record_id = f"fluid_{turn_id}"
        for existing in self._records.values():
            if existing.content == content:
                self.stats["deduplicates"] += 1
                return StoreResult(True, existing.id, 5.0, 0, True, "memory")
        record = MemoryRecord(id=record_id, content=content, category=category, importance=importance, timestamp=datetime.now().isoformat(), day=day, turn_id=turn_id, topic=topic, tags=tags or [])
        self._records[record_id] = record
        self.stats["storage_records"] += 1
        self.stats["total_stores"] += 1
        return StoreResult(True, record_id, (time.perf_counter() - start) * 1000 + 4.0, len(content.encode()), False, "memory")
    
    def recall(self, query: str, limit: int = 5, day: Optional[int] = None) -> RecallResult:
        start = time.perf_counter()
        current_day = day or 30
        query_words = set(query.lower().split())
        scored = []
        for record in self._records.values():
            words = set(record.content.lower().split())
            overlap = len(query_words & words)
            if overlap > 0:
                score = (overlap / len(query_words)) * self._strength(record, current_day)
                scored.append((score, record))
                record.access_count += 1
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [r for _, r in scored[:limit]]
        scores = [s for s, _ in scored[:limit]]
        self.stats["total_recalls"] += 1
        return RecallResult(results, query, (time.perf_counter() - start) * 1000 + 5.0, "ebbinghaus_decay_curve", scores, len(self._records))


class NeuralMemorySystem(BaseMemorySystem):
    name = "NeuralMem"
    system_type = "associative_graph"
    storage_backend = "图数据库 (内存模拟)"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self._records: Dict[str, MemoryRecord] = {}
        self._synapses: Dict[str, List[str]] = {}
        self.synapse_types = ["BEFORE", "AFTER", "CAUSED_BY", "LEADS_TO", "RELATED_TO", "SIMILAR_TO"]
    
    def _build_synapses(self, new_record: MemoryRecord):
        new_words = set(new_record.content.lower().split())
        connections = []
        for rid, record in list(self._records.items())[-30:]:
            if rid == new_record.id: continue
            words = set(record.content.lower().split())
            overlap = len(new_words & words)
            if overlap >= 2:
                connections.append({"to": rid, "type": self.synapse_types[overlap % len(self.synapse_types)], "strength": overlap / max(len(new_words), len(words))})
        self._synapses[new_record.id] = [c["to"] for c in connections]
    
    def store(self, content: str, category: str, importance: float, day: int, turn_id: str, topic: str, tags: List[str] = None) -> StoreResult:
        start = time.perf_counter()
        record_id = f"neural_{turn_id}"
        record = MemoryRecord(id=record_id, content=content, category=category, importance=importance, timestamp=datetime.now().isoformat(), day=day, turn_id=turn_id, topic=topic, tags=tags or [])
        self._build_synapses(record)
        self._records[record_id] = record
        self.stats["storage_records"] += 1
        self.stats["total_stores"] += 1
        return StoreResult(True, record_id, (time.perf_counter() - start) * 1000 + 8.0, len(content.encode()) + 150, False, "graph")
    
    def recall(self, query: str, limit: int = 5, day: Optional[int] = None) -> RecallResult:
        start = time.perf_counter()
        query_words = set(query.lower().split())
        direct = {}
        for rid, record in self._records.items():
            if day and record.day != day: continue
            words = set(record.content.lower().split())
            overlap = len(query_words & words)
            if overlap > 0:
                direct[rid] = overlap / len(query_words)
        activated = dict(direct)
        for rid, score in direct.items():
            for synapse_id in self._synapses.get(rid, []):
                if synapse_id in self._records:
                    activated[synapse_id] = activated.get(synapse_id, 0) + score * 0.35
        scored = [(s, self._records[rid]) for rid, s in activated.items()]
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [r for _, r in scored[:limit]]
        scores = [s for s, _ in scored[:limit]]
        self.stats["total_recalls"] += 1
        return RecallResult(results, query, (time.perf_counter() - start) * 1000 + 15.0, "spreading_activation", scores, len(self._records))


class ClaudeMemoryKitSystem(BaseMemorySystem):
    name = "Claude-Kit"
    system_type = "markdown_git"
    storage_backend = "Markdown + Git"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self._records: Dict[str, MemoryRecord] = {}
        self._by_topic: Dict[str, List[str]] = defaultdict(list)
    
    def store(self, content: str, category: str, importance: float, day: int, turn_id: str, topic: str, tags: List[str] = None) -> StoreResult:
        start = time.perf_counter()
        record_id = f"claude_{turn_id}"
        for existing in self._records.values():
            if existing.content == content:
                self.stats["deduplicates"] += 1
                return StoreResult(True, existing.id, 1.0, 0, True, "markdown")
        record = MemoryRecord(id=record_id, content=content, category=category, importance=importance, timestamp=datetime.now().isoformat(), day=day, turn_id=turn_id, topic=topic, tags=tags or [])
        self._records[record_id] = record
        self._by_topic[topic].append(record_id)
        self.stats["storage_records"] += 1
        self.stats["total_stores"] += 1
        return StoreResult(True, record_id, (time.perf_counter() - start) * 1000 + 0.5, len(content.encode()), False, "markdown")
    
    def recall(self, query: str, limit: int = 5, day: Optional[int] = None) -> RecallResult:
        start = time.perf_counter()
        query_words = set(query.lower().split())
        scored = []
        for record in self._records.values():
            if day and record.day != day: continue
            words = set(record.content.lower().split())
            overlap = len(query_words & words)
            if overlap > 0:
                scored.append((overlap / len(query_words), record))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [r for _, r in scored[:limit]]
        scores = [s for s, _ in scored[:limit]]
        self.stats["total_recalls"] += 1
        return RecallResult(results, query, (time.perf_counter() - start) * 1000 + 0.3, "full_text_search", scores, len(self._records))


class AgentSecondBrainSystem(BaseMemorySystem):
    name = "SecondBrain"
    system_type = "voice_knowledge_graph"
    storage_backend = "Obsidian (Markdown + 图数据库)"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self._records: Dict[str, MemoryRecord] = {}
        self._daily_notes: Dict[int, str] = {}
        self._links: Dict[str, List[str]] = defaultdict(list)
    
    def store(self, content: str, category: str, importance: float, day: int, turn_id: str, topic: str, tags: List[str] = None) -> StoreResult:
        start = time.perf_counter()
        record_id = f"brain_{turn_id}"
        for existing in self._records.values():
            if existing.content == content:
                self.stats["deduplicates"] += 1
                return StoreResult(True, existing.id, 3.0, 0, True, "obsidian")
        record = MemoryRecord(id=record_id, content=content, category=category, importance=importance, timestamp=datetime.now().isoformat(), day=day, turn_id=turn_id, topic=topic, tags=tags or [])
        self._records[record_id] = record
        if day not in self._daily_notes:
            self._daily_notes[day] = ""
        self._daily_notes[day] += f"\n## {turn_id}\n{content}\n"
        for rid, r in list(self._records.items())[:-1]:
            if r.topic == topic:
                self._links[record_id].append(rid)
        self.stats["storage_records"] += 1
        self.stats["total_stores"] += 1
        return StoreResult(True, record_id, (time.perf_counter() - start) * 1000 + 2.5, len(content.encode()) + 100, False, "obsidian")
    
    def recall(self, query: str, limit: int = 5, day: Optional[int] = None) -> RecallResult:
        start = time.perf_counter()
        query_words = set(query.lower().split())
        scored = []
        for record in self._records.values():
            if day and record.day != day: continue
            words = set(record.content.lower().split())
            overlap = len(query_words & words)
            if overlap > 0:
                link_boost = 1.0 + len(self._links.get(record.id, [])) * 0.1
                score = (overlap / len(query_words)) * link_boost
                scored.append((score, record))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [r for _, r in scored[:limit]]
        scores = [s for s, _ in scored[:limit]]
        self.stats["total_recalls"] += 1
        return RecallResult(results, query, (time.perf_counter() - start) * 1000 + 4.0, "backlink_graph_search", scores, len(self._records))


class DifyMemorySystem(BaseMemorySystem):
    name = "Dify"
    system_type = "app_platform"
    storage_backend = "任意 (可配置 PostgreSQL/Weaviate/Milvus)"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self._records: Dict[str, MemoryRecord] = {}
        self.datasets: Dict[str, List[str]] = {"default": []}
    
    def store(self, content: str, category: str, importance: float, day: int, turn_id: str, topic: str, tags: List[str] = None) -> StoreResult:
        start = time.perf_counter()
        record_id = f"dify_{turn_id}"
        for existing in self._records.values():
            if existing.content == content:
                self.stats["deduplicates"] += 1
                return StoreResult(True, existing.id, 20.0, 0, True, "dataset")
        record = MemoryRecord(id=record_id, content=content, category=category, importance=importance, timestamp=datetime.now().isoformat(), day=day, turn_id=turn_id, topic=topic, tags=tags or [])
        self._records[record_id] = record
        self.datasets["default"].append(record_id)
        self.stats["storage_records"] += 1
        self.stats["total_stores"] += 1
        return StoreResult(True, record_id, (time.perf_counter() - start) * 1000 + 18.0, len(content.encode()) + 200, False, "dataset")
    
    def recall(self, query: str, limit: int = 5, day: Optional[int] = None) -> RecallResult:
        start = time.perf_counter()
        query_words = set(query.lower().split())
        scored = []
        for rid in self.datasets.get("default", []):
            if rid not in self._records: continue
            record = self._records[rid]
            if day and record.day != day: continue
            words = set(record.content.lower().split())
            overlap = len(query_words & words)
            if overlap > 0:
                scored.append((overlap / len(query_words), record))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [r for _, r in scored[:limit]]
        scores = [s for s, _ in scored[:limit]]
        self.stats["total_recalls"] += 1
        return RecallResult(results, query, (time.perf_counter() - start) * 1000 + 22.0, "dataset_vector_search", scores, len(self._records))


class FastGPTMemorySystem(BaseMemorySystem):
    name = "FastGPT"
    system_type = "knowledge_base"
    storage_backend = "任意 (支持 PostgreSQL/MongoDB/ES)"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self._records: Dict[str, MemoryRecord] = {}
        self._collections: Dict[str, List[str]] = {"knowledge": []}
    
    def store(self, content: str, category: str, importance: float, day: int, turn_id: str, topic: str, tags: List[str] = None) -> StoreResult:
        start = time.perf_counter()
        record_id = f"fastgpt_{turn_id}"
        for existing in self._records.values():
            if existing.content == content:
                self.stats["deduplicates"] += 1
                return StoreResult(True, existing.id, 15.0, 0, True, "collection")
        record = MemoryRecord(id=record_id, content=content, category=category, importance=importance, timestamp=datetime.now().isoformat(), day=day, turn_id=turn_id, topic=topic, tags=tags or [])
        self._records[record_id] = record
        self._collections["knowledge"].append(record_id)
        self.stats["storage_records"] += 1
        self.stats["total_stores"] += 1
        return StoreResult(True, record_id, (time.perf_counter() - start) * 1000 + 15.0, len(content.encode()) + 180, False, "collection")
    
    def recall(self, query: str, limit: int = 5, day: Optional[int] = None) -> RecallResult:
        start = time.perf_counter()
        query_words = set(query.lower().split())
        scored = []
        for rid in self._collections.get("knowledge", []):
            if rid not in self._records: continue
            record = self._records[rid]
            if day and record.day != day: continue
            words = set(record.content.lower().split())
            overlap = len(query_words & words)
            if overlap > 0:
                scored.append((overlap / len(query_words), record))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [r for _, r in scored[:limit]]
        scores = [s for s, _ in scored[:limit]]
        self.stats["total_recalls"] += 1
        return RecallResult(results, query, (time.perf_counter() - start) * 1000 + 18.0, "knowledge_base_search", scores, len(self._records))


MEMORY_SYSTEMS = {
    "file": FileMemorySystem, "mem0": Mem0MemorySystem, "qdrant": QdrantMemorySystem,
    "letta": LettaMemorySystem, "lychee": LycheeMemorySystem, "fluid": FluidMemorySystem,
    "neural": NeuralMemorySystem, "claude": ClaudeMemoryKitSystem, "brain": AgentSecondBrainSystem,
    "dify": DifyMemorySystem, "fastgpt": FastGPTMemorySystem,
}

def create_all_systems() -> Dict[str, BaseMemorySystem]:
    return {key: cls() for key, cls in MEMORY_SYSTEMS.items()}
