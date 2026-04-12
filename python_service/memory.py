"""
记忆系统 — 三层记忆架构
短记忆：Redis原始消息（实时）
中记忆：会话超长后压缩为摘要
长记忆：文件系统持久化（用户画像+关键事实）
"""

import os
import json
import time
import asyncio
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict, field
from concurrent.futures import ThreadPoolExecutor

try:
    import redis as redis_lib
    _REDIS_URL = os.getenv("REDIS_URL", "localhost:6379")
    if _REDIS_URL.startswith("redis://"):
        _REDIS_URL = _REDIS_URL[9:]
    _r = redis_lib.Redis(
        host=_REDIS_URL.split(":")[0],
        port=int(_REDIS_URL.split(":")[-1]),
        db=0,
        decode_responses=True,
    )
    _r.ping()
    rdb = _r
    del _r, _REDIS_URL
except Exception:
    print("[Memory] WARNING: Redis unavailable — short-term memory disabled")
    rdb = None
    rdb = None

executor = ThreadPoolExecutor(max_workers=3)

# ============================================================================
# Memory Config
# ============================================================================

SHORT_MAX_MESSAGES = 10
SHORT_MAX_TOKENS = 3000
MEDIUM_MAX_MESSAGES = 50
SUMMARIZE_AFTER = 15
MAX_SUMMARY_TOKENS = 1500
LONG_MAX_FACTS = 100

# ============================================================================
# Data Structures
# ============================================================================


@dataclass
class MemoryLevel:
    """记忆层级元信息"""
    session_id: str
    user_id: str = "default"
    short_count: int = 0          # 短记忆消息数
    medium_summarized: bool = False  # 是否已完成中记忆压缩
    last_summary_time: float = 0.0   # 上次压缩时间戳
    long_fact_count: int = 0        # 长记忆事实数


@dataclass
class SessionMemory:
    """完整会话记忆结构"""
    session_id: str
    short_term: list[dict] = field(default_factory=list)   # 原始消息
    medium_summary: str = ""         # 中记忆摘要
    long_term: list[dict] = field(default_factory=list)    # 关键事实
    memory_level: Optional[MemoryLevel] = None


@dataclass
class UserFact:
    """用户事实（长记忆）"""
    category: str       # emotion/fact/preference/goal
    content: str
    confidence: float    # 0.0-1.0
    timestamp: float
    source_session: str


# ============================================================================
# Redis Key Helpers
# ============================================================================


def _key(session_id: str, suffix: str) -> str:
    return f"mem:{session_id}:{suffix}"


SHORT_KEY = lambda sid: _key(sid, "short")
MEDIUM_KEY = lambda sid: _key(sid, "medium")
LONG_KEY = lambda sid: _key(sid, "long")
META_KEY = lambda sid: _key(sid, "meta")
USER_LONG_KEY = lambda uid: f"mem:user:{uid}:long"


# ============================================================================
# Token Estimation
# ============================================================================


def estimate_tokens(text: str) -> int:
    return len(text) // 4


# ============================================================================
# Memory Manager
# ============================================================================


class MemoryManager:
    """
    三层记忆管理器
    """

    def __init__(self, session_id: str, user_id: str = "default"):
        self.session_id = session_id
        self.user_id = user_id

    # --------------------------------------------------------------------------
    # Short-term: raw messages in Redis
    # --------------------------------------------------------------------------

    def add_message(self, role: str, content: str, emotion: str = "") -> None:
        """添加一条消息到短记忆"""
        msg = {
            "role": role,
            "content": content,
            "emotion": emotion,
            "timestamp": time.time(),
        }
        rdb.lpush(SHORT_KEY(self.session_id), json.dumps(msg, ensure_ascii=False))
        rdb.ltrim(SHORT_KEY(self.session_id), 0, MEDIUM_MAX_MESSAGES - 1)
        rdb.expire(SHORT_KEY(self.session_id), LONG_TERM_MEMORY_TTL)
        self._increment_meta("short_count")

    def get_short_term(self, limit: int = None) -> list[dict]:
        """获取短记忆"""
        limit = limit or SHORT_MAX_MESSAGES
        raw = rdb.lrange(SHORT_KEY(self.session_id), 0, limit - 1)
        msgs = [json.loads(m) for m in raw]
        msgs.reverse()  #  oldest first for LLM context
        return msgs

    def get_short_term_tokens(self) -> int:
        msgs = self.get_short_term(limit=MEDIUM_MAX_MESSAGES)
        return sum(estimate_tokens(m["content"]) for m in msgs)

    # --------------------------------------------------------------------------
    # Medium-term: summarization
    # --------------------------------------------------------------------------

    def should_summarize(self) -> bool:
        """判断是否需要压缩"""
        meta = self._get_meta()
        short_count = meta.get("short_count", 0)
        # 短记忆超过阈值，且还没有压缩过
        return short_count > SUMMARIZE_AFTER and not meta.get("medium_summarized", False)

    def store_medium_summary(self, summary: str) -> None:
        """存储中记忆摘要"""
        rdb.set(MEDIUM_KEY(self.session_id), json.dumps({
            "summary": summary,
            "timestamp": time.time(),
        }, ensure_ascii=False), ex=LONG_TERM_MEMORY_TTL)
        self._update_meta(medium_summarized=True, last_summary_time=time.time())

    def get_medium_summary(self) -> str:
        """获取中记忆摘要"""
        raw = rdb.get(MEDIUM_KEY(self.session_id))
        if raw:
            return json.loads(raw).get("summary", "")
        return ""

    # --------------------------------------------------------------------------
    # Long-term: file-based persistent storage
    # --------------------------------------------------------------------------

    def _long_term_path(self) -> Path:
        p = MEMORY_DIR / f"{self.user_id}.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def add_long_term_fact(self, category: str, content: str, confidence: float = 0.8) -> None:
        """追加长记忆事实"""
        fact = UserFact(
            category=category,
            content=content,
            confidence=confidence,
            timestamp=time.time(),
            source_session=self.session_id,
        )
        # 读取现有
        existing = self.get_long_term_facts()
        # 去重（同category+同content）
        existing = [f for f in existing if not (f.category == category and f.content == content)]
        existing.append(fact)
        # 限制数量
        if len(existing) > LONG_MAX_FACTS:
            existing = sorted(existing, key=lambda f: (f.confidence, f.timestamp), reverse=True)[:LONG_MAX_FACTS]
        # 写回
        with open(self._long_term_path(), "w", encoding="utf-8") as f:
            for fact in existing:
                f.write(json.dumps(asdict(fact), ensure_ascii=False) + "\n")
        self._update_meta(long_fact_count=len(existing))

    def get_long_term_facts(self, category: str = None) -> list[UserFact]:
        """获取长记忆事实，可按category过滤"""
        path = self._long_term_path()
        if not path.exists():
            return []
        facts = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        facts.append(UserFact(**json.loads(line)))
                    except Exception:
                        pass
        if category:
            facts = [f for f in facts if f.category == category]
        return facts

    def extract_and_store_facts(self, summary: str) -> int:
        """
        从摘要中提取关键事实存入长记忆。
        直接在线程池中同步调用 LLM，不走 asyncio event loop。
        """
        extraction_prompt = (
            "从以下对话摘要中提取值得长期记住的用户信息，"
            "包括：用户基本情况、情绪模式、重要事件、明确表达的偏好和目标。"
            "以JSON数组格式返回，每个元素包含category/content/confidence字段。"
            "category可选值：emotion_pattern / personal_fact / preference / goal。"
            "只返回JSON，不要其他文字。\n\n摘要：\n" + summary
        )
        try:
            from main import openai_client, LLM_MODEL
            def _call():
                resp = openai_client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=[{"role": "user", "content": extraction_prompt}],
                    temperature=0.3,
                    max_tokens=800,
                )
                return resp.choices[0].message.content
            # Run synchronously in executor (summarize_and_evict already runs in executor)
            import concurrent.futures
            future = executor.submit(_call)
            raw_text = future.result(timeout=15)
            import re
            json_match = re.search(r"\[[\s\S]*\]", raw_text or "")
            if json_match:
                items = json.loads(json_match.group())
                count = 0
                for item in items:
                    self.add_long_term_fact(
                        category=item.get("category", "personal_fact"),
                        content=item.get("content", ""),
                        confidence=item.get("confidence", 0.7),
                    )
                    count += 1
                return count
        except Exception as exc:
            print(f"[Memory] fact extraction failed: {exc}")
        return 0

    # --------------------------------------------------------------------------
    # Full context assembly
    # --------------------------------------------------------------------------

    def get_context_for_llm(self) -> str:
        """
        组装给LLM的完整上下文字符串
        顺序：长记忆事实 → 中记忆摘要 → 短记忆原始
        """
        parts = []

        # Long-term facts
        long_facts = self.get_long_term_facts()
        if long_facts:
            facts_text = "【用户长期信息】\n"
            for f in sorted(long_facts, key=lambda x: x.timestamp, reverse=True)[:10]:
                facts_text += f"- [{f.category}] {f.content}\n"
            parts.append(facts_text)

        # Medium-term summary
        medium = self.get_medium_summary()
        if medium:
            parts.append(f"【近期对话摘要】\n{medium}\n")

        # Short-term raw
        short_msgs = self.get_short_term()
        if short_msgs:
            parts.append("【当前对话】\n")
            for m in short_msgs:
                role = "用户" if m["role"] == "user" else "助手"
                parts.append(f"{role}：{m['content']}\n")

        return "\n".join(parts) or "（这是对话的开始）"

    # --------------------------------------------------------------------------
    # Meta helpers
    # --------------------------------------------------------------------------

    def _get_meta(self) -> dict:
        raw = rdb.get(META_KEY(self.session_id))
        if raw:
            return json.loads(raw)
        return {"short_count": 0, "medium_summarized": False, "long_fact_count": 0}

    def _update_meta(self, **kwargs) -> None:
        meta = self._get_meta()
        meta.update(kwargs)
        rdb.set(META_KEY(self.session_id), json.dumps(meta, ensure_ascii=False), ex=LONG_TERM_MEMORY_TTL)

    def _increment_meta(self, key: str) -> None:
        meta = self._get_meta()
        meta[key] = meta.get(key, 0) + 1
        rdb.set(META_KEY(self.session_id), json.dumps(meta, ensure_ascii=False), ex=LONG_TERM_MEMORY_TTL)

    # --------------------------------------------------------------------------
    # Session lifecycle
    # --------------------------------------------------------------------------

    def summarize_and_evict(self, full_history: list[dict], llm_call_fn) -> str:
        """
        对会话进行中期压缩：
        1. 用LLM生成摘要
        2. 存储摘要到中记忆
        3. 清空短记忆（已包含在摘要中）
        4. 从摘要中提取事实存入长记忆
        """
        # 构造要总结的历史（最近N条）
        history_text = ""
        for m in full_history[-SUMMARIZE_AFTER:]:
            role = "用户" if m.get("role") == "user" else "助手"
            history_text += f"{role}：{m.get('content', '')}\n"

        summary_prompt = (
            "请将以下对话压缩为一段简洁的摘要，保留关键信息、情绪变化和重要结论。"
            "摘要应便于后续快速回顾。\n\n" + history_text
        )

        summary = llm_call_fn(summary_prompt)
        self.store_medium_summary(summary)
        self.extract_and_store_facts(summary)
        # 清空短记忆中的已总结部分（保留最近2条作为锚点）
        short_msgs = self.get_short_term(limit=MEDIUM_MAX_MESSAGES)
        if len(short_msgs) > 2:
            keep = short_msgs[-2:]
            pipe = rdb.pipeline()
            pipe.delete(SHORT_KEY(self.session_id))
            for msg in reversed(keep):
                pipe.lpush(SHORT_KEY(self.session_id), json.dumps(msg, ensure_ascii=False))
            pipe.execute()
        return summary
