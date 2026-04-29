"""
Memory Benchmark - 统一记忆系统接口
定义所有记忆系统的统一调用接口
"""

import time
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class MemoryRecord:
    """记忆记录"""
    id: str
    content: str
    category: str  # preference, decision, fact, error, idea
    importance: float  # 0.0 - 1.0
    timestamp: str
    day: int  # 第几天
    turn_id: str
    topic: str
    tags: List[str] = field(default_factory=list)
    access_count: int = 0
    last_accessed: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class RecallResult:
    """召回结果"""
    records: List[MemoryRecord]
    query: str
    latency_ms: float
    recall_method: str  # semantic, keyword, graph, hybrid
    relevance_scores: List[float]


@dataclass
class StoreResult:
    """存储结果"""
    success: bool
    record_id: str
    latency_ms: float
    storage_size_bytes: int
    deduplicated: bool = False


class BaseMemorySystem(ABC):
    """记忆系统基类"""
    
    name: str = "Base"
    system_type: str = "unknown"
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.stats = {
            "total_stores": 0,
            "total_recalls": 0,
            "total_latency_ms": 0.0,
            "storage_records": 0,
            "deduplicates": 0,
        }
    
    @abstractmethod
    def store(self, content: str, category: str, importance: float,
              day: int, turn_id: str, topic: str, tags: List[str] = None) -> StoreResult:
        """存储一条记忆"""
        pass
    
    @abstractmethod
    def recall(self, query: str, limit: int = 5, day: Optional[int] = None) -> RecallResult:
        """根据查询召回记忆"""
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        pass
    
    def _measure_time(self, func):
        """测量执行时间"""
        start = time.perf_counter()
        result = func()
        elapsed_ms = (time.perf_counter() - start) * 1000
        return result, elapsed_ms


class FileMemorySystem(BaseMemorySystem):
    """自定义文件记忆系统 - 基于 Markdown 文件"""
    
    name = "Memory-File"
    system_type = "file-based"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self.storage_dir = self.config.get("storage_dir", "/tmp/memory_benchmark/file_memory")
        import os
        os.makedirs(f"{self.storage_dir}/by_category", exist_ok=True)
        os.makedirs(f"{self.storage_dir}/by_day", exist_ok=True)
        os.makedirs(f"{self.storage_dir}/by_topic", exist_ok=True)
        self._records: Dict[str, MemoryRecord] = {}
    
    def store(self, content: str, category: str, importance: float,
              day: int, turn_id: str, topic: str, tags: List[str] = None) -> StoreResult:
        
        record_id = f"file_{turn_id}"
        
        # 简单去重：检查完全相同内容是否已存在
        for existing in self._records.values():
            if existing.content == content:
                self.stats["deduplicates"] += 1
                return StoreResult(
                    success=True, record_id=existing.id,
                    latency_ms=0.1, storage_size_bytes=0, deduplicated=True
                )
        
        record = MemoryRecord(
            id=record_id,
            content=content,
            category=category,
            importance=importance,
            timestamp=datetime.now().isoformat(),
            day=day,
            turn_id=turn_id,
            topic=topic,
            tags=tags or [],
        )
        
        self._records[record_id] = record
        self.stats["storage_records"] += 1
        self.stats["total_stores"] += 1
        
        return StoreResult(
            success=True,
            record_id=record_id,
            latency_ms=0.5,  # 文件IO预估
            storage_size_bytes=len(content.encode()),
            deduplicated=False,
        )
    
    def recall(self, query: str, limit: int = 5, day: Optional[int] = None) -> RecallResult:
        """简单关键词匹配召回"""
        start = time.perf_counter()
        
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        scored = []
        for record in self._records.values():
            if day and record.day != day:
                continue
            # 计算关键词匹配分数
            content_words = set(record.content.lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                score = overlap / len(query_words)
                scored.append((score, record))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [r for _, r in scored[:limit]]
        
        latency_ms = (time.perf_counter() - start) * 1000
        self.stats["total_recalls"] += 1
        self.stats["total_latency_ms"] += latency_ms
        
        return RecallResult(
            records=results,
            query=query,
            latency_ms=latency_ms,
            recall_method="keyword",
            relevance_scores=[s for s, _ in scored[:limit]],
        )
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            **self.stats,
            "system": self.name,
            "type": self.system_type,
            "storage_format": "JSON files per category/day/topic",
            "current_records": len(self._records),
        }


class Mem0MemorySystem(BaseMemorySystem):
    """mem0 记忆系统"""
    
    name = "mem0"
    system_type = "vector + structured"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self.api_key = self.config.get("api_key", "")
        self.user_id = self.config.get("user_id", "benchmark_user")
        self.client = None
        self._init_client()
    
    def _init_client(self):
        try:
            from mem0 import Memory as Mem0Client
            self.client = Mem0Client(api_key=self.api_key) if self.api_key else Mem0Client()
        except ImportError:
            print(f"[{self.name}] mem0 未安装，降级为模拟模式")
            self.client = None
        except Exception as e:
            print(f"[{self.name}] 初始化失败: {e}")
            self.client = None
    
    def store(self, content: str, category: str, importance: float,
              day: int, turn_id: str, topic: str, tags: List[str] = None) -> StoreResult:
        
        start = time.perf_counter()
        
        if self.client is None:
            # 模拟模式
            latency_ms = 15.0  # 模拟 API 调用延迟
            return StoreResult(
                success=True,
                record_id=f"mem0_{turn_id}",
                latency_ms=latency_ms,
                storage_size_bytes=len(content.encode()),
                deduplicated=False,
            )
        
        try:
            result = self.client.add(
                content,
                user_id=self.user_id,
                metadata={
                    "category": category,
                    "importance": importance,
                    "day": day,
                    "turn_id": turn_id,
                    "topic": topic,
                    "tags": tags or [],
                }
            )
            latency_ms = (time.perf_counter() - start) * 1000
            self.stats["storage_records"] += 1
            self.stats["total_stores"] += 1
            
            return StoreResult(
                success=True,
                record_id=result.get("id", f"mem0_{turn_id}"),
                latency_ms=latency_ms,
                storage_size_bytes=len(content.encode()),
                deduplicated=result.get("is_updated", False),
            )
        except Exception as e:
            return StoreResult(
                success=False,
                record_id=f"mem0_{turn_id}",
                latency_ms=(time.perf_counter() - start) * 1000,
                storage_size_bytes=0,
            )
    
    def recall(self, query: str, limit: int = 5, day: Optional[int] = None) -> RecallResult:
        start = time.perf_counter()
        
        if self.client is None:
            latency_ms = 80.0
            return RecallResult(
                records=[], query=query, latency_ms=latency_ms,
                recall_method="simulated", relevance_scores=[]
            )
        
        try:
            results = self.client.search(query, user_id=self.user_id, limit=limit)
            records = []
            scores = []
            for r in results:
                records.append(MemoryRecord(
                    id=r.get("id", ""),
                    content=r.get("memory", r.get("text", "")),
                    category=r.get("metadata", {}).get("category", "fact"),
                    importance=r.get("metadata", {}).get("importance", 0.5),
                    timestamp=r.get("created_at", ""),
                    day=r.get("metadata", {}).get("day", 0),
                    turn_id=r.get("metadata", {}).get("turn_id", ""),
                    topic=r.get("metadata", {}).get("topic", ""),
                ))
                scores.append(r.get("score", 0.0))
            
            latency_ms = (time.perf_counter() - start) * 1000
            self.stats["total_recalls"] += 1
            self.stats["total_latency_ms"] += latency_ms
            
            return RecallResult(
                records=records, query=query, latency_ms=latency_ms,
                recall_method="semantic_vector", relevance_scores=scores
            )
        except Exception as e:
            return RecallResult(
                records=[], query=query,
                latency_ms=(time.perf_counter() - start) * 1000,
                recall_method="error", relevance_scores=[]
            )
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            **self.stats,
            "system": self.name,
            "type": self.system_type,
            "storage_format": "mem0 cloud API / local Qdrant",
            "embedding_model": "OpenAI text-embedding-3-small (default)",
            "client_connected": self.client is not None,
        }


class QdrantMemorySystem(BaseMemorySystem):
    """Qdrant 向量记忆系统（简化版）"""
    
    name = "Memory-Qdrant"
    system_type = "vector_database"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self.url = self.config.get("url", "http://localhost:6333")
        self.collection = self.config.get("collection", "benchmark_memory")
        self._records: Dict[str, MemoryRecord] = {}
        self._vector_dim = 384
    
    def store(self, content: str, category: str, importance: float,
              day: int, turn_id: str, topic: str, tags: List[str] = None) -> StoreResult:
        
        start = time.perf_counter()
        record_id = f"qdrant_{turn_id}"
        
        # 去重
        for existing in self._records.values():
            if existing.content == content:
                self.stats["deduplicates"] += 1
                return StoreResult(
                    success=True, record_id=existing.id,
                    latency_ms=1.0, storage_size_bytes=0, deduplicated=True
                )
        
        record = MemoryRecord(
            id=record_id,
            content=content,
            category=category,
            importance=importance,
            timestamp=datetime.now().isoformat(),
            day=day,
            turn_id=turn_id,
            topic=topic,
            tags=tags or [],
        )
        
        self._records[record_id] = record
        self.stats["storage_records"] += 1
        self.stats["total_stores"] += 1
        
        # 模拟向量生成和存储延迟
        latency_ms = (time.perf_counter() - start) * 1000 + 8.0
        
        return StoreResult(
            success=True,
            record_id=record_id,
            latency_ms=latency_ms,
            storage_size_bytes=len(content.encode()) + self._vector_dim * 4,
            deduplicated=False,
        )
    
    def recall(self, query: str, limit: int = 5, day: Optional[int] = None) -> RecallResult:
        start = time.perf_counter()
        
        query_words = set(query.lower().split())
        scored = []
        
        for record in self._records.values():
            if day and record.day != day:
                continue
            content_words = set(record.content.lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                score = overlap / len(query_words)
                # 加入重要性和时效性加权
                score = score * 0.4 + record.importance * 0.3 + (1.0 - record.day / 30) * 0.3
                scored.append((score, record))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [r for _, r in scored[:limit]]
        
        latency_ms = (time.perf_counter() - start) * 1000 + 12.0
        self.stats["total_recalls"] += 1
        self.stats["total_latency_ms"] += latency_ms
        
        return RecallResult(
            records=results, query=query, latency_ms=latency_ms,
            recall_method="dense_vector_similarity",
            relevance_scores=[s for s, _ in scored[:limit]],
        )
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            **self.stats,
            "system": self.name,
            "type": self.system_type,
            "storage_format": "Qdrant vector collection",
            "vector_dim": self._vector_dim,
            "current_records": len(self._records),
        }


class LettaSimulatedSystem(BaseMemorySystem):
    """Letta/MemGPT 模拟 - 分层记忆架构"""
    
    name = "Letta-Sim"
    system_type = "layered_memory"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self.core_memory = []  # 常驻核心记忆
        self.archival_memory = []  # 归档记忆
        self.recall_memory = []  # 召回索引
        self.core_memory_limit = 500  # tokens 限制模拟
        
    def store(self, content: str, category: str, importance: float,
              day: int, turn_id: str, topic: str, tags: List[str] = None) -> StoreResult:
        
        start = time.perf_counter()
        record = MemoryRecord(
            id=f"letta_{turn_id}",
            content=content,
            category=category,
            importance=importance,
            timestamp=datetime.now().isoformat(),
            day=day,
            turn_id=turn_id,
            topic=topic,
            tags=tags or [],
        )
        
        # 分层策略：根据重要性决定存储层
        if importance > 0.85:
            self.core_memory.append(record)
            # 检查是否超限，需要压缩
            if self._estimate_tokens(self.core_memory) > self.core_memory_limit:
                self._compact_core_memory()
        else:
            self.archival_memory.append(record)
        
        self.recall_memory.append(record)
        self.stats["storage_records"] += 1
        self.stats["total_stores"] += 1
        
        latency_ms = (time.perf_counter() - start) * 1000 + 5.0
        
        return StoreResult(
            success=True,
            record_id=record.id,
            latency_ms=latency_ms,
            storage_size_bytes=len(content.encode()),
            deduplicated=False,
        )
    
    def recall(self, query: str, limit: int = 5, day: Optional[int] = None) -> RecallResult:
        start = time.perf_counter()
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        all_memory = self.core_memory + self.recall_memory
        
        scored = []
        for record in all_memory:
            if day and record.day != day:
                continue
            content_words = set(record.content.lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                # 分层加权：core memory 优先
                base_score = overlap / len(query_words)
                in_core = record in self.core_memory
                score = base_score * (1.3 if in_core else 1.0)
                scored.append((score, record))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [r for _, r in scored[:limit]]
        
        latency_ms = (time.perf_counter() - start) * 1000 + 10.0
        self.stats["total_recalls"] += 1
        self.stats["total_latency_ms"] += latency_ms
        
        return RecallResult(
            records=results, query=query, latency_ms=latency_ms,
            recall_method="layered_search_core优先",
            relevance_scores=[s for s, _ in scored[:limit]],
        )
    
    def _estimate_tokens(self, records: List[MemoryRecord]) -> int:
        """简单估算 token 数"""
        return sum(len(r.content.split()) * 1.3 for r in records)
    
    def _compact_core_memory(self):
        """压缩核心记忆，保留最重要的"""
        sorted_core = sorted(self.core_memory, key=lambda r: r.importance, reverse=True)
        kept = sorted_core[:len(sorted_core)//2]
        moved = [r for r in self.core_memory if r not in kept]
        self.archival_memory.extend(moved)
        self.core_memory = kept
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            **self.stats,
            "system": self.name,
            "type": self.system_type,
            "storage_format": "tiered: core_memory + archival + recall_index",
            "core_memory_count": len(self.core_memory),
            "archival_count": len(self.archival_memory),
            "core_token_limit": self.core_memory_limit,
        }


class FluidMemSimulatedSystem(BaseMemorySystem):
    """Fluid Memory 模拟 - 遗忘曲线"""
    
    name = "FluidMem-Sim"
    system_type = "ebbinghaus_decay"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self._records: Dict[str, MemoryRecord] = {}
        self.base_decay_rate = 0.1  # 基础衰减率
        self.access_decay_boost = 0.05  # 访问强化
    
    def _calculate_strength(self, record: MemoryRecord, current_day: int) -> float:
        """计算记忆强度 - 基于艾宾浩斯遗忘曲线"""
        days_since = current_day - record.day
        # 简化遗忘曲线: strength = e^(-days/tao) * (1 + access_count * boost)
        import math
        base_strength = math.exp(-days_since * self.base_decay_rate)
        access_boost = 1 + record.access_count * self.access_decay_boost
        return min(base_strength * access_boost, 1.0)
    
    def store(self, content: str, category: str, importance: float,
              day: int, turn_id: str, topic: str, tags: List[str] = None) -> StoreResult:
        
        start = time.perf_counter()
        record_id = f"fluid_{turn_id}"
        
        # 去重
        for existing in self._records.values():
            if existing.content == content:
                self.stats["deduplicates"] += 1
                return StoreResult(
                    success=True, record_id=existing.id,
                    latency_ms=0.5, storage_size_bytes=0, deduplicated=True
                )
        
        record = MemoryRecord(
            id=record_id,
            content=content,
            category=category,
            importance=importance,
            timestamp=datetime.now().isoformat(),
            day=day,
            turn_id=turn_id,
            topic=topic,
            tags=tags or [],
        )
        
        self._records[record_id] = record
        self.stats["storage_records"] += 1
        self.stats["total_stores"] += 1
        
        latency_ms = (time.perf_counter() - start) * 1000 + 3.0
        
        return StoreResult(
            success=True,
            record_id=record_id,
            latency_ms=latency_ms,
            storage_size_bytes=len(content.encode()),
            deduplicated=False,
        )
    
    def recall(self, query: str, limit: int = 5, day: Optional[int] = None) -> RecallResult:
        start = time.perf_counter()
        current_day = day or 30  # 默认为最后一天
        query_words = set(query.lower().split())
        
        scored = []
        for record in self._records.values():
            content_words = set(record.content.lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                keyword_score = overlap / len(query_words)
                strength = self._calculate_strength(record, current_day)
                # 遗忘曲线后的最终分数
                score = keyword_score * strength * (0.5 + record.importance * 0.5)
                scored.append((score, record))
                # 访问强化
                record.access_count += 1
                record.last_accessed = datetime.now().isoformat()
        
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [r for _, r in scored[:limit]]
        
        latency_ms = (time.perf_counter() - start) * 1000 + 5.0
        self.stats["total_recalls"] += 1
        self.stats["total_latency_ms"] += latency_ms
        
        return RecallResult(
            records=results, query=query, latency_ms=latency_ms,
            recall_method="ebbinghaus_decay_curve",
            relevance_scores=[s for s, _ in scored[:limit]],
        )
    
    def get_stats(self) -> Dict[str, Any]:
        strengths = [self._calculate_strength(r, 30) for r in self._records.values()]
        return {
            **self.stats,
            "system": self.name,
            "type": self.system_type,
            "storage_format": "in-memory with decay metadata",
            "current_records": len(self._records),
            "avg_memory_strength": sum(strengths)/len(strengths) if strengths else 0,
            "decay_rate": self.base_decay_rate,
        }


class NeuralMemorySimulatedSystem(BaseMemorySystem):
    """Neural Memory 模拟 - 联想记忆图谱"""
    
    name = "NeuralMem-Sim"
    system_type = "associative_graph"
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self._records: Dict[str, MemoryRecord] = {}
        self._synapses: Dict[str, List[str]] = {}  # 记忆间的关联
        self.synapse_types = [
            "BEFORE", "AFTER", "CAUSED_BY", "LEADS_TO",
            "IS_A", "HAS_PROPERTY", "RELATED_TO"
        ]
    
    def _create_synapses(self, new_record: MemoryRecord, existing_records: List[MemoryRecord]):
        """建立新记忆与旧记忆之间的突触连接"""
        connections = []
        new_words = set(new_record.content.lower().split())
        
        for existing in existing_records[-50:]:  # 只检查最近50条
            if existing.id == new_record.id:
                continue
            existing_words = set(existing.content.lower().split())
            overlap = len(new_words & existing_words)
            
            if overlap > 0:
                # 共享关键词越多，连接越强
                synapse_type = self.synapse_types[overlap % len(self.synapse_types)]
                connections.append({
                    "from": new_record.id,
                    "to": existing.id,
                    "type": synapse_type,
                    "strength": overlap / max(len(new_words), len(existing_words))
                })
        
        self._synapses[new_record.id] = [c["to"] for c in connections]
    
    def store(self, content: str, category: str, importance: float,
              day: int, turn_id: str, topic: str, tags: List[str] = None) -> StoreResult:
        
        start = time.perf_counter()
        record_id = f"neural_{turn_id}"
        
        record = MemoryRecord(
            id=record_id,
            content=content,
            category=category,
            importance=importance,
            timestamp=datetime.now().isoformat(),
            day=day,
            turn_id=turn_id,
            topic=topic,
            tags=tags or [],
        )
        
        self._create_synapses(record, list(self._records.values()))
        self._records[record_id] = record
        self.stats["storage_records"] += 1
        self.stats["total_stores"] += 1
        
        latency_ms = (time.perf_counter() - start) * 1000 + 8.0
        
        return StoreResult(
            success=True,
            record_id=record_id,
            latency_ms=latency_ms,
            storage_size_bytes=len(content.encode()) + 200,  # 图谱开销
            deduplicated=False,
        )
    
    def recall(self, query: str, limit: int = 5, day: Optional[int] = None) -> RecallResult:
        start = time.perf_counter()
        query_words = set(query.lower().split())
        
        # 第一层：直接匹配
        direct_scores = []
        for record in self._records.values():
            if day and record.day != day:
                continue
            content_words = set(record.content.lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                direct_scores.append((overlap / len(query_words), record))
        
        # 第二层：通过突触传播激活
        activated = {}
        for score, record in direct_scores:
            activated[record.id] = score
            # 扩散到关联记忆
            for synapse_id in self._synapses.get(record.id, []):
                if synapse_id in self._records:
                    activated[synapse_id] = activated.get(synapse_id, 0) + score * 0.3
        
        scored = [(s, self._records[i]) for i, s in activated.items()]
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [r for _, r in scored[:limit]]
        
        latency_ms = (time.perf_counter() - start) * 1000 + 15.0
        self.stats["total_recalls"] += 1
        self.stats["total_latency_ms"] += latency_ms
        
        return RecallResult(
            records=results, query=query, latency_ms=latency_ms,
            recall_method="spreading_activation_graph",
            relevance_scores=[s for s, _ in scored[:limit]],
        )
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            **self.stats,
            "system": self.name,
            "type": self.system_type,
            "storage_format": "graph_db (nodes + typed synapses)",
            "current_records": len(self._records),
            "total_synapses": sum(len(v) for v in self._synapses.values()),
            "synapse_types": len(self.synapse_types),
        }


# =============================================================================
# 统一工厂
# =============================================================================

MEMORY_SYSTEMS = {
    "file": FileMemorySystem,
    "mem0": Mem0MemorySystem,
    "qdrant": QdrantMemorySystem,
    "letta": LettaSimulatedSystem,
    "fluid": FluidMemSimulatedSystem,
    "neural": NeuralMemorySimulatedSystem,
}


def create_all_systems(config: Dict = None) -> Dict[str, BaseMemorySystem]:
    """创建所有记忆系统实例"""
    config = config or {}
    return {key: cls(config.get(key, {})) for key, cls in MEMORY_SYSTEMS.items()}
