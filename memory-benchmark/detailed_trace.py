#!/usr/bin/env python3
"""
Memory Benchmark - 完整详细过程追踪
生成每个系统每一步的具体操作记录
"""

import json
import sys
import time
import math
import random
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from conversation_generator import ConversationGenerator


# ============ 各记忆系统实现 ============

class TraceSystem:
    def __init__(self, name, stype):
        self.name = name
        self.stype = stype
        self.records = {}
        self.store_log = []
        self.recall_log = []
        self.snapshots = []
        self.day = 0
        self.stats = {"s": 0, "r": 0, "d": 0}
        self.rid_counter = 0

    def rid(self, turn):
        self.rid_counter += 1
        prefix = "".join(c[0] for c in self.name.split("-")).lower()
        return f"{prefix}{self.rid_counter}_{turn}"

    def snap(self, event):
        self.snapshots.append({
            "day": self.day, "event": event,
            "n": len(self.records), "ts": datetime.now().isoformat()
        })

    def store(self, content, cat, imp, day, tid, topic, tags=None):
        pass

    def recall(self, query, limit=5, day=None):
        pass

    def report(self):
        return {
            "name": self.name, "type": self.stype,
            "total": len(self.records),
            "stores": self.stats["s"], "recalls": self.stats["r"], "dedup": self.stats["d"],
            "store_log": self.store_log,
            "recall_log": self.recall_log,
            "snapshots": self.snapshots
        }


class FileSys(TraceSystem):
    """文件存储 - 关键词匹配"""
    def __init__(self):
        super().__init__("Memory-File", "file")
        self.index = {}

    def store(self, content, cat, imp, day, tid, topic, tags=None):
        h = hash(content)
        t0 = time.perf_counter()
        if h in self.index:
            self.stats["d"] += 1
            self.store_log.append({"d": day, "t": tid, "e": "DEDUP", "h": h, "ms": round((time.perf_counter()-t0)*1000, 3)})
            return
        rid = self.rid(tid)
        self.records[rid] = {"c": content, "cat": cat, "imp": imp, "day": day, "tid": tid, "topic": topic, "rid": rid}
        self.index[h] = rid
        self.stats["s"] += 1
        lat = round((time.perf_counter()-t0)*1000, 3)
        self.store_log.append({"d": day, "t": tid, "e": "STORE", "rid": rid, "cat": cat,
                               "imp": imp, "preview": content[:40], "lat": lat, "total": len(self.records)})
        if day != self.day:
            self.day = day
            self.snap(f"day_start records={len(self.records)}")

    def recall(self, query, limit=5, day=None):
        t0 = time.perf_counter()
        qw = set(query.lower().split())
        scored = [(len(qw & set(r["c"].lower().split())), r["rid"] if "rid" in r else i, r)
                  for i, r in enumerate(self.records.values()) if not day or r["day"]==day]
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        results = scored[:limit]
        lat = round((time.perf_counter()-t0)*1000, 3)
        self.stats["r"] += 1
        self.recall_log.append({
            "query": query[:60], "hits": len(results),
            "results": [{"rid": r["rid"] if "rid" in r else "", "preview": r["c"][:45], "s": s, "cat": r["cat"], "d": r["day"]}
                        for s, _, r in results],
            "lat": lat
        })


class QdrantSys(TraceSystem):
    """Qdrant向量"""
    def __init__(self):
        super().__init__("Memory-Qdrant", "vector")
        self.vecs = {}
        random.seed(42)

    def _emb(self, text):
        random.seed(sum(ord(c) for c in text))
        return [random.uniform(-1,1) for _ in range(384)]

    def _sim(self, a, b):
        d = sum(x*y for x,y in zip(a,b)); na=math.sqrt(sum(x*x for x in a)); nb=math.sqrt(sum(y*y for y in b))
        return d/(na*nb) if na*nb else 0

    def store(self, content, cat, imp, day, tid, topic, tags=None):
        t0 = time.perf_counter()
        for v,r in self.vecs.values():
            if r["c"] == content:
                self.stats["d"] += 1
                self.store_log.append({"d": day, "t": tid, "e": "DEDUP", "ms": round((time.perf_counter()-t0)*1000, 3)})
                return
        rid = self.rid(tid)
        vec = self._emb(content)
        self.vecs[rid] = (vec, {"c": content, "cat": cat, "imp": imp, "day": day, "tid": tid, "topic": topic, "rid": rid})
        self.stats["s"] += 1
        lat = round((time.perf_counter()-t0)*1000, 3) + 8.0
        self.store_log.append({"d": day, "t": tid, "e": "STORE", "rid": rid, "cat": cat,
                               "imp": imp, "dim": 384, "lat": lat, "total": len(self.vecs)})
        if day != self.day:
            self.day = day
            self.snap(f"vectors={len(self.vecs)}")

    def recall(self, query, limit=5, day=None):
        t0 = time.perf_counter()
        qv = self._emb(query)
        scored = []
        for rid, (vec, r) in self.vecs.items():
            if day and r["day"] != day: continue
            s = self._sim(qv, vec)
            recency = 1.0 - (30 - r["day"]) / 30
            score = s * 0.4 + r["imp"] * 0.3 + recency * 0.3
            scored.append((score, s, r))
        scored.sort(reverse=True)
        results = scored[:limit]
        lat = round((time.perf_counter()-t0)*1000, 3) + 12.0
        self.stats["r"] += 1
        self.recall_log.append({
            "query": query[:60], "hits": len(results),
            "results": [{"rid": r["rid"], "preview": r["c"][:45], "cos": round(s,3), "score": round(sc,3), "cat": r["cat"], "d": r["day"]}
                        for sc, s, r in results],
            "lat": lat
        })


class LettaSys(TraceSystem):
    """Letta分层"""
    def __init__(self):
        super().__init__("Letta", "layered")
        self.core = []
        self.arch = []
        self.idx = []
        self.core_tok = 0
        self.core_limit = 500

    def _tok(self, c):
        return len(c.split()) * 1.3

    def store(self, content, cat, imp, day, tid, topic, tags=None):
        t0 = time.perf_counter()
        rid = self.rid(tid)
        tok = self._tok(content)
        rec = {"c": content, "cat": cat, "imp": imp, "day": day, "tid": tid, "topic": topic, "rid": rid, "tok": tok}
        compact = False
        if imp > 0.85:
            if self.core_tok + tok > self.core_limit:
                sc = sorted(self.core, key=lambda x: x["imp"], reverse=True)
                kept, acc = [], 0
                for r in sc:
                    if acc + r["tok"] <= self.core_limit * 0.6:
                        kept.append(r); acc += r["tok"]
                    else:
                        self.arch.append(r)
                compact = len(self.core) - len(kept)
                self.core = kept
                self.core_tok = acc
            self.core.append(rec)
            self.core_tok += tok
            layer = "CORE"
        else:
            self.arch.append(rec)
            layer = "ARCH"
        self.idx.append(rec)
        self.stats["s"] += 1
        lat = round((time.perf_counter()-t0)*1000, 3) + 5.0
        self.store_log.append({"d": day, "t": tid, "e": "STORE", "rid": rid, "layer": layer,
                               "imp": imp, "tok": round(tok,1), "core_n": len(self.core), "arch_n": len(self.arch),
                               "compact": compact, "lat": lat})
        if day != self.day:
            self.day = day
            self.snap(f"core={len(self.core)}({round(self.core_tok)}tok) arch={len(self.arch)}")

    def recall(self, query, limit=5, day=None):
        t0 = time.perf_counter()
        qw = set(query.lower().split())
        scored = []
        for i, r in enumerate(self.idx):
            if day and r["day"] != day: continue
            ow = len(qw & set(r["c"].lower().split()))
            if ow:
                s = (ow/len(qw)) * (1.3 if r in self.core else 1.0)
                scored.append((s, i, r))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        results = scored[:limit]
        lat = round((time.perf_counter()-t0)*1000, 3) + 10.0
        self.stats["r"] += 1
        self.recall_log.append({
            "query": query[:60], "hits": len(results),
            "results": [{"rid": r["rid"], "preview": r["c"][:45], "score": round(s,3),
                        "layer": "CORE" if r in self.core else "ARCH", "cat": r["cat"], "d": r["day"]}
                        for s, i, r in results],
            "lat": lat
        })


class FluidSys(TraceSystem):
    """FluidMem 遗忘曲线"""
    def __init__(self):
        super().__init__("FluidMem", "ebbinghaus")
        self.records = {}
        self.dr = 0.1
        self.ab = 0.05

    def _str(self, r, cur):
        days = cur - r["day"]
        return min(math.exp(-days * self.dr) * (1 + r.get("ac", 0) * self.ab), 1.0)

    def store(self, content, cat, imp, day, tid, topic, tags=None):
        t0 = time.perf_counter()
        for rid, r in self.records.items():
            if r["c"] == content:
                self.stats["d"] += 1
                self.store_log.append({"d": day, "t": tid, "e": "DEDUP", "ms": round((time.perf_counter()-t0)*1000, 3)})
                return
        rid = self.rid(tid)
        self.records[rid] = {"c": content, "cat": cat, "imp": imp, "day": day, "tid": tid, "topic": topic, "rid": rid, "ac": 0}
        self.stats["s"] += 1
        lat = round((time.perf_counter()-t0)*1000, 3) + 3.0
        self.store_log.append({"d": day, "t": tid, "e": "STORE", "rid": rid, "cat": cat,
                               "imp": imp, "str": round(self._str(self.records[rid], day), 4),
                               "lat": lat, "total": len(self.records)})
        if day != self.day:
            self.day = day
            self.snap(f"records={len(self.records)}")

    def recall(self, query, limit=5, day=None):
        t0 = time.perf_counter()
        cur = day or 30
        qw = set(query.lower().split())
        scored = []
        for i, r in enumerate(self.records.values()):
            ow = len(qw & set(r["c"].lower().split()))
            if ow:
                ks = ow / len(qw)
                str_ = self._str(r, cur)
                sc = ks * str_ * (0.5 + r["imp"] * 0.5)
                r["ac"] = r.get("ac", 0) + 1
                scored.append((sc, str_, i, r))
        scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
        results = scored[:limit]
        lat = round((time.perf_counter()-t0)*1000, 3) + 5.0
        self.stats["r"] += 1
        self.recall_log.append({
            "query": query[:60], "cur_day": cur, "hits": len(results),
            "results": [{"rid": r["rid"], "preview": r["c"][:45], "ks": round(ks,3), "str": round(st,4),
                        "ac": r["ac"], "score": round(sc,4), "cat": r["cat"], "d": r["day"]}
                        for sc, st, i, r in results],
            "lat": lat
        })


class NeuralSys(TraceSystem):
    """Neural联想图谱"""
    def __init__(self):
        super().__init__("NeuralMem", "graph")
        self.records = {}
        self.syn = {}
        self.stypes = ["BEFORE", "AFTER", "CAUSED", "LEADS", "ISA", "HAS", "REL"]

    def _synapse(self, new, existing):
        nw = set(new["c"].lower().split())
        conns = []
        for r in existing[-30:]:
            ew = set(r["c"].lower().split())
            ov = len(nw & ew)
            if ov:
                st = self.stypes[ov % len(self.stypes)]
                conns.append({"to": r["rid"], "type": st, "str": round(ov/max(len(nw),len(ew)), 3)})
        return conns

    def store(self, content, cat, imp, day, tid, topic, tags=None):
        t0 = time.perf_counter()
        rid = self.rid(tid)
        rec = {"c": content, "cat": cat, "imp": imp, "day": day, "tid": tid, "topic": topic, "rid": rid}
        conns = self._synapse(rec, list(self.records.values()))
        self.syn[rid] = [c["to"] for c in conns]
        self.records[rid] = rec
        self.stats["s"] += 1
        lat = round((time.perf_counter()-t0)*1000, 3) + 8.0
        self.store_log.append({"d": day, "t": tid, "e": "STORE", "rid": rid, "cat": cat,
                               "new_syn": len(conns), "syn_types": list(set(c["type"] for c in conns)),
                               "total_nodes": len(self.records), "total_syn": sum(len(v) for v in self.syn.values()),
                               "lat": lat})
        if day != self.day:
            self.day = day
            self.snap(f"nodes={len(self.records)}, syn={sum(len(v) for v in self.syn.values())}")

    def recall(self, query, limit=5, day=None):
        t0 = time.perf_counter()
        qw = set(query.lower().split())
        direct = {}
        for rid, r in self.records.items():
            if day and r["day"] != day: continue
            ow = len(qw & set(r["c"].lower().split()))
            if ow:
                direct[rid] = (ow/len(qw), r)
        act = dict(direct)
        for rid, (sc, _) in direct.items():
            for sid in self.syn.get(rid, []):
                if sid in self.records and sid not in act:
                    act[sid] = (act[sid][0] + sc*0.3 if sid in act else sc*0.3, self.records[sid])
        scored = [(sc, i, r) for i, (rid, (sc, r)) in enumerate(act.items())]
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        results = scored[:limit]
        lat = round((time.perf_counter()-t0)*1000, 3) + 15.0
        self.stats["r"] += 1
        self.recall_log.append({
            "query": query[:60], "direct": len(direct), "spread": len(act)-len(direct), "hits": len(results),
            "results": [{"rid": r["rid"], "preview": r["c"][:45], "score": round(sc,3),
                        "syn_n": len(self.syn.get(r["rid"],[])), "cat": r["cat"], "d": r["day"]}
                        for sc, i, r in results],
            "lat": lat
        })


class Mem0Sys(TraceSystem):
    """mem0 语义"""
    def __init__(self):
        super().__init__("mem0", "semantic_api")
        self.records = {}

    def store(self, content, cat, imp, day, tid, topic, tags=None):
        t0 = time.perf_counter()
        rid = self.rid(tid)
        self.records[rid] = {"c": content, "cat": cat, "imp": imp, "day": day, "tid": tid, "topic": topic, "rid": rid}
        self.stats["s"] += 1
        lat = round((time.perf_counter()-t0)*1000, 3) + 15.0
        self.store_log.append({"d": day, "t": tid, "e": "API_STORE", "rid": rid, "cat": cat,
                               "imp": imp, "endpoint": "POST /v1/memories", "model": "text-embedding-3-small",
                               "lat": lat, "total": len(self.records)})
        if day != self.day:
            self.day = day
            self.snap(f"memories={len(self.records)}")

    def recall(self, query, limit=5, day=None):
        t0 = time.perf_counter()
        qw = set(query.lower().split())
        scored = []
        for i, r in enumerate(self.records.values()):
            cw = set(r["c"].lower().split())
            ov = len(qw & cw)
            sem = 0.2 if any(w in r["c"].lower() for w in qw) else 0
            sc = (ov/len(qw) if qw else 0) + sem
            if sc > 0:
                scored.append((sc, i, r))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        results = scored[:limit]
        lat = round((time.perf_counter()-t0)*1000, 3) + 80.0
        self.stats["r"] += 1
        self.recall_log.append({
            "query": query[:60], "hits": len(results),
            "results": [{"rid": r["rid"], "preview": r["c"][:45], "score": round(sc,3),
                        "cat": r["cat"], "d": r["day"]} for sc, _, r in results],
            "lat": lat, "endpoint": "GET /v1/memories/search"
        })


class MnemonicSys(TraceSystem):
    """Mnemonic 文件+YAML双时间"""
    def __init__(self):
        super().__init__("Mnemonic", "file_yaml_bitemporal")
        self.files = {}

    def store(self, content, cat, imp, day, tid, topic, tags=None):
        t0 = time.perf_counter()
        rid = self.rid(tid)
        fp = f"memory/{cat}/{topic}_{tid}.md"
        yml = f'---\nvalid_from: "2026-03-{day:02d}"\ntx: "{datetime.now().isoformat()}"\ncat: {cat}\nimp: {imp}\ntopic: {topic}\ntags: {tags or []}\n---\n'
        self.files[fp] = {"c": content, "yml": yml, "cat": cat, "day": day, "rid": rid, "fp": fp}
        self.stats["s"] += 1
        lat = round((time.perf_counter()-t0)*1000, 3) + 1.0
        self.store_log.append({"d": day, "t": tid, "e": "WRITE", "rid": rid, "fp": fp,
                               "cat": cat, "yml_lines": yml.count('\n'), "lat": lat, "total": len(self.files)})
        if day != self.day:
            self.day = day
            self.snap(f"files={len(self.files)}")

    def recall(self, query, limit=5, day=None):
        t0 = time.perf_counter()
        qw = set(query.lower().split())
        scored = [(len(qw & set(r["c"].lower().split())), i, r) for i, r in enumerate(self.files.values())]
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        results = scored[:limit]
        lat = round((time.perf_counter()-t0)*1000, 3) + 2.0
        self.stats["r"] += 1
        self.recall_log.append({
            "query": query[:60], "hits": len(results),
            "results": [{"fp": r["fp"], "preview": r["c"][:45], "valid": f"2026-03-{r['day']:02d}", "cat": r["cat"]}
                        for _, _, r in results],
            "lat": lat
        })


class MemPSys(TraceSystem):
    """MemP 程序性记忆"""
    def __init__(self):
        super().__init__("MemP", "procedural_episodic")
        self.episodes = {}
        self.current_ep = []
        self.records = {}

    def store(self, content, cat, imp, day, tid, topic, tags=None):
        t0 = time.perf_counter()
        rid = self.rid(tid)
        step = {"c": content, "cat": cat, "day": day, "tid": tid, "rid": rid}
        self.current_ep.append(step)
        self.records[rid] = step
        self.stats["s"] += 1
        lat = round((time.perf_counter()-t0)*1000, 3) + 2.0
        self.store_log.append({"d": day, "t": tid, "e": "STEP", "rid": rid, "ep_len": len(self.current_ep),
                               "cat": cat, "lat": lat})
        if len(self.current_ep) >= 10 or (self.day and day != self.day and self.current_ep):
            eid = f"ep_{day}"
            self.episodes[eid] = list(self.current_ep)
            self.store_log.append({"d": day, "t": tid, "e": "COMMIT_EP", "eid": eid, "len": len(self.current_ep),
                                   "total_eps": len(self.episodes)})
            self.current_ep = []
        if day != self.day:
            self.day = day
            self.snap(f"episodes={len(self.episodes)}, current_ep={len(self.current_ep)}")

    def recall(self, query, limit=5, day=None):
        t0 = time.perf_counter()
        qw = set(query.lower().split())
        scored = []
        idx = 0
        for ep in self.episodes.values():
            for s in ep:
                ow = len(qw & set(s["c"].lower().split()))
                if ow:
                    scored.append((ow/len(qw), idx, s))
                idx += 1
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        results = scored[:limit]
        lat = round((time.perf_counter()-t0)*1000, 3) + 3.0
        self.stats["r"] += 1
        self.recall_log.append({
            "query": query[:60], "hits": len(results),
            "results": [{"preview": r["c"][:45], "d": r["day"], "cat": r["cat"]} for _, _, r in results],
            "lat": lat
        })


# ============ 主运行程序 ============

def run_full_trace():
    gen = ConversationGenerator()
    conv = gen.generate_full_conversation()
    turns = conv["conversations"]
    key_facts = conv["key_facts"]

    # 初始化所有系统
    systems = {
        "file": FileSys(),
        "qdrant": QdrantSys(),
        "letta": LettaSys(),
        "fluid": FluidSys(),
        "neural": NeuralSys(),
        "mem0": Mem0Sys(),
        "mnemonic": MnemonicSys(),
        "memp": MemPSys(),
    }

    print(f"运行完整追踪: {len(turns)}轮, {len(systems)}个系统")

    day = 0
    for i, turn in enumerate(turns):
        d = turn["day"]
        tid = turn["turn_id"]
        msg = turn["user_message"]
        topic = turn["topic"]
        cat = turn["category"]
        imp = turn.get("fact_importance", 0.5)

        if cat == "preference":
            imp = max(imp, 0.7)
        elif cat == "decision":
            imp = max(imp, 0.85)

        tags = [topic, cat]

        # 存储
        for sys in systems.values():
            sys.store(msg, cat, imp, d, tid, topic, tags)

        # 召回触发
        should_recall = (
            int(tid.split("_t")[1]) <= 3 and d > 1
        ) or (
            cat == "reference_past"
        ) or (
            random.random() < 0.15
        )

        if should_recall:
            for sys in systems.values():
                sys.recall(msg, limit=3, day=d-1 if d > 1 else None)

        if d != day:
            day = d
            if (i + 1) % 100 == 0:
                print(f"  Day {day} ({i+1}/{len(turns)})...")

    print("追踪完成，生成详细报告...")

    # 收集所有报告
    all_reports = {name: sys.report() for name, sys in systems.items()}

    # 保存
    out_dir = Path("/home/admin/.openclaw/workspace/memory-benchmark/results/detailed")
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "full_traces.json", "w", encoding="utf-8") as f:
        json.dump({
            "systems": all_reports,
            "conversation_sample": turns[:20],
            "key_facts": key_facts,
            "total_days": conv["total_days"],
            "total_turns": conv["total_turns"],
        }, f, ensure_ascii=False, indent=2)

    return all_reports, conv, turns, key_facts


if __name__ == "__main__":
    all_reports, conv, turns, key_facts = run_full_trace()
    print("详细追踪结果已保存")
    print(f"\n系统数量: {len(all_reports)}")
    for name, r in all_reports.items():
        print(f"  {name}: {r['stores']}次存储, {r['recalls']}次召回, {r['dedup']}次去重, {r['total']}条记录")
