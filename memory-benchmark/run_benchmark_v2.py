#!/usr/bin/env python3
"""
Memory Benchmark v2 - 主运行程序
模拟30天×1128轮对话，评测11个记忆系统
"""

import sys
import json
import time
import random
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from memory_systems_v2 import create_all_systems, BaseMemorySystem, MemoryRecord


class ConversationGenerator:
    def __init__(self, seed=42):
        random.seed(seed)
        self.key_facts = [
            {"entity": "电商平台", "fact": "决定用Next.js重构前端", "importance": 0.95, "first_mentioned": None},
            {"entity": "数据库", "fact": "选型PostgreSQL，已完成迁移", "importance": 0.9, "first_mentioned": None},
            {"entity": "AI助手", "fact": "接入ClawHub，做记忆系统评测", "importance": 0.85, "first_mentioned": None},
            {"entity": "咖啡偏好", "fact": "只喝美式，不加糖，每天2杯", "importance": 0.7, "first_mentioned": None},
            {"entity": "会议习惯", "fact": "周三下午固定会议，其他时间异步", "importance": 0.75, "first_mentioned": None},
            {"entity": "休假计划", "fact": "计划6月去日本赏樱花", "importance": 0.8, "first_mentioned": None},
            {"entity": "代码风格", "fact": "偏好TypeScript strict mode", "importance": 0.85, "first_mentioned": None},
            {"entity": "数据看板", "fact": "用FastGPT做内部BI", "importance": 0.75, "first_mentioned": None},
        ]
        self.topics = ["电商平台前端架构", "AI记忆系统", "数据库优化", "微服务拆分", "CI/CD", "单元测试", "API设计", "React性能", "Rust学习"]
        self.templates = [
            ("task", ["今天要做什么？", "帮我看看待办", "昨天的进度怎么样了？", "这个任务预计什么时候完成？"]),
            ("tech", ["关于{topic}有什么建议？", "在{topic}上遇到问题", "帮我review代码", "{topic}的设计可以改进吗？"]),
            ("decision", ["用哪个方案好？A还是B？", "决定用{option}了", "这个会影响{impact}"]),
            ("pref", ["我喜欢{pref}，记一下", "有个偏好更新：{pref}", "我一直觉得{opinion}"]),
            ("recall", ["之前关于{topic}的结论是什么？", "我记得有过一个决定", "上周提到要关注{topic}"]),
            ("daily", ["今天心情不错", "午饭吃啥？", "下午有会", "周末计划？"]),
            ("learn", ["最近学{topic}有收获", "学到了新用法", "{topic}文档很清晰"]),
            ("error", ["遇到bug：{problem}", "报错了，{error}", "这个库有坑，{issue}"]),
        ]
        self.problems = ["连接超时", "内存泄漏", "类型不匹配", "并发冲突", "部署失败"]
        self.prefs = ["深色主题", "快捷键", "自动化测试", "代码格式化", "简洁函数名"]
        self.options = ["TypeScript", "Go", "Rust", "PostgreSQL", "React", "Docker"]
    
    def generate(self, days=30, turns_per_day=38):
        conversations = []
        for day in range(1, days + 1):
            for turn in range(turns_per_day):
                turn_id = f"d{day}_t{turn+1}"
                cat, templates = random.choice(self.templates)
                msg = random.choice(templates)
                topic = random.choice(self.topics)
                msg = msg.format(topic=topic, pref=random.choice(self.prefs), option=random.choice(self.options), 
                               impact="可扩展性", opinion="代码要先测试", problem=random.choice(self.problems), error="connection refused", issue="版本兼容")
                
                # 30%概率提起关键事实
                mentioned = None
                if random.random() < 0.3:
                    fact = random.choice(self.key_facts)
                    mentioned = fact["fact"]
                    if fact["first_mentioned"] is None:
                        fact["first_mentioned"] = day
                
                conversations.append({
                    "turn_id": turn_id, "day": day, "user_message": msg, "topic": topic,
                    "category": cat, "mentioned_fact": mentioned,
                    "importance": random.uniform(0.5, 1.0)
                })
        return {"conversations": conversations, "key_facts": self.key_facts, "total_days": days, "total_turns": len(conversations)}


class MemoryBenchmark:
    def __init__(self):
        self.conv_gen = ConversationGenerator()
        self.systems: Dict[str, BaseMemorySystem] = {}
        self.store_logs: Dict[str, List] = {k: [] for k in ["file", "mem0", "qdrant", "letta", "lychee", "fluid", "neural", "claude", "brain", "dify", "fastgpt"]}
        self.recall_logs: Dict[str, List] = {k: [] for k in self.store_logs}
        self.key_fact_results: Dict[str, Dict] = {}
    
    def init_systems(self):
        print("=" * 60)
        print("初始化 11 个记忆系统...")
        print("=" * 60)
        self.systems = create_all_systems()
        for k, s in self.systems.items():
            print(f"  [{s.name}] {s.system_type} | {s.storage_backend}")
        print()
    
    def categorize(self, turn):
        msg = turn["user_message"]
        if "喜欢" in msg or "记一下" in msg or "偏好" in msg: return "preference"
        if "决定" in msg or "用" in msg: return "decision"
        if "bug" in msg or "报错" in msg: return "error"
        if "之前" in msg or "记得" in msg or "上次" in msg: return "recall"
        return "fact"
    
    def should_recall(self, turn):
        if turn["category"] == "recall": return True
        if random.random() < 0.15: return True
        turn_num = int(turn["turn_id"].split("_t")[1])
        if turn_num <= 3 and turn["day"] > 1: return True
        return False
    
    def run(self):
        print("生成模拟对话...")
        data = self.conv_gen.generate(days=30, turns_per_day=38)
        convs = data["conversations"]
        key_facts = data["key_facts"]
        print(f"生成完成: {data['total_days']}天 × {data['total_turns']//30}轮 = {data['total_turns']}轮")
        print()
        print("=" * 60)
        print("开始评测...")
        print("=" * 60)
        
        current_day = 0
        for i, turn in enumerate(convs):
            day = turn["day"]
            if day != current_day:
                current_day = day
                print(f"\n--- Day {day} --- (第 {i+1}/{len(convs)} 轮)")
            
            category = self.categorize(turn)
            content = f"[{category}] {turn['topic']}: {turn['user_message']}"
            importance = turn["importance"]
            tags = [turn["topic"], category]
            
            # 存储到所有系统
            for name, system in self.systems.items():
                result = system.store(content, category, importance, day, turn["turn_id"], turn["topic"], tags)
                self.store_logs[name].append({
                    "day": day, "turn_id": turn["turn_id"], "category": category,
                    "importance": importance, "success": result.success,
                    "latency_ms": result.latency_ms, "deduplicated": result.deduplicated
                })
            
            # 召回测试
            if self.should_recall(turn):
                for name, system in self.systems.items():
                    result = system.recall(turn["user_message"], limit=3, day=day-1 if day > 1 else None)
                    self.recall_logs[name].append({
                        "day": day, "turn_id": turn["turn_id"], "query": turn["user_message"][:40],
                        "results": len(result.records), "latency_ms": result.latency_ms,
                        "method": result.recall_method
                    })
            
            if (i + 1) % 100 == 0:
                print(f"  进度: {i+1}/{len(convs)} 轮 ({100*(i+1)//len(convs)}%)")
        
        # 关键事实召回测试
        print("\n" + "=" * 60)
        print("测试 30天后关键事实召回能力...")
        print("=" * 60)
        for fact in key_facts:
            query = f"关于{fact['entity']}"
            for name, system in self.systems.items():
                result = system.recall(query, limit=3)
                found = any(fact["fact"] in r.content or fact["entity"] in r.content for r in result.records)
                if name not in self.key_fact_results:
                    self.key_fact_results[name] = {}
                self.key_fact_results[name][fact["entity"]] = {
                    "found": found, "results": len(result.records),
                    "latency_ms": result.latency_ms, "score": result.relevance_scores[0] if result.relevance_scores else 0
                }
        print("召回测试完成")
    
    def generate_report(self):
        report = {
            "info": {"date": datetime.now().isoformat(), "total_days": 30, "total_turns": len(self.store_logs["file"]), "systems": len(self.systems)},
            "storage": {}, "recall": {}, "key_facts": {}, "latency": {}, "schemas": {}, "recommendations": []
        }
        
        # 存储分析
        for name, system in self.systems.items():
            logs = self.store_logs[name]
            cats = {}
            for l in logs:
                c = l["category"]
                cats[c] = cats.get(c, 0) + 1
            dedup = sum(1 for l in logs if l["deduplicated"])
            stats = system.get_stats()
            report["storage"][name] = {
                "name": stats["system"], "type": stats["type"], "backend": system.storage_backend,
                "total_records": stats["storage_records"], "deduplications": dedup,
                "category_dist": cats
            }
        
        # 召回分析
        for name, system in self.systems.items():
            logs = self.recall_logs[name]
            if not logs: continue
            avg_lat = sum(l["latency_ms"] for l in logs) / len(logs)
            avg_res = sum(l["results"] for l in logs) / len(logs)
            methods = {}
            for l in logs:
                m = l["method"]
                methods[m] = methods.get(m, 0) + 1
            report["recall"][name] = {"total_recalls": len(logs), "avg_latency_ms": round(avg_lat, 2), "avg_results": round(avg_res, 2), "methods": methods}
        
        # 关键事实召回
        for name in self.systems.keys():
            if name not in self.key_fact_results: continue
            results = self.key_fact_results[name]
            found = sum(1 for r in results.values() if r["found"])
            avg_lat = sum(r["latency_ms"] for r in results.values()) / len(results)
            avg_score = sum(r["score"] for r in results.values()) / len(results)
            report["key_facts"][name] = {"tested": len(results), "found": found, "rate": round(found/len(results)*100, 1), "avg_latency_ms": round(avg_lat, 2), "avg_relevance": round(avg_score, 3)}
        
        # 延迟对比
        for name in self.systems.keys():
            stores = self.store_logs[name]
            recalls = self.recall_logs[name]
            avg_store = sum(s["latency_ms"] for s in stores) / len(stores) if stores else 0
            avg_recall = sum(r["latency_ms"] for r in recalls) / len(recalls) if recalls else 0
            report["latency"][name] = {"store_ms": round(avg_store, 2), "recall_ms": round(avg_recall, 2), "total_ops": len(stores) + len(recalls)}
        
        # 存储方案
        for name, system in self.systems.items():
            report["schemas"][name] = {"name": system.name, "type": system.system_type, "backend": system.storage_backend}
        
        # 建议
        recall_rates = {n: d["rate"] for n, d in report["key_facts"].items()}
        latencies = {n: d["recall_ms"] for n, d in report["latency"].items()}
        best_recall = max(recall_rates, key=recall_rates.get) if recall_rates else "N/A"
        lowest_lat = min(latencies, key=latencies.get) if latencies else "N/A"
        report["recommendations"] = [
            f"召回率最高: {best_recall} ({recall_rates.get(best_recall, 'N/A')}%)",
            f"延迟最低: {lowest_lat} ({latencies.get(lowest_lat, 'N/A')}ms)",
            "场景建议: 快速原型→Memory-File | 语义理解→mem0/Qdrant | 层级管理→Letta",
            "场景建议: 遗忘曲线→FluidMem | 联想推理→NeuralMem | 零费用→Claude-Kit",
            "场景建议: 中文知识库→FastGPT | 企业应用→Dify | 知识图谱→SecondBrain"
        ]
        return report
    
    def save(self, report, data):
        out = Path("/home/admin/.openclaw/workspace/memory-benchmark/results_v2")
        out.mkdir(exist_ok=True)
        (out/"benchmark_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        sample = {"total_days": data["total_days"], "total_turns": data["total_turns"], "conversations": data["conversations"][:20]}
        (out/"conversations.json").write_text(json.dumps(sample, ensure_ascii=False, indent=2))
        print(f"\n结果已保存: {out}/")


def print_report(report):
    print("\n" + "=" * 70)
    print(" " * 15 + "记忆系统评测报告 v2.0 (11个系统)")
    print("=" * 70)
    bi = report["info"]
    print(f"\n📊 评测概览")
    print(f"   模拟时长: {bi['total_days']} 天")
    print(f"   总对话轮次: {bi['total_turns']} 轮")
    print(f"   评测系统: {bi['systems']} 个")
    
    print(f"\n📦 存储模式对比")
    print("-" * 70)
    print(f"{'系统':<14} {'类型':<18} {'记录数':<8} {'去重':<6} {'存储后端'}")
    print("-" * 70)
    for d in report["storage"].values():
        print(f"{d['name']:<14} {d['type']:<18} {d['total_records']:<8} {d['deduplications']:<6} {d['backend'][:25]}")
    
    print(f"\n🔍 召回能力对比 (30天后)")
    print("-" * 70)
    print(f"{'系统':<14} {'召回率':<10} {'平均延迟':<12} {'平均结果数':<12} {'召回次数'}")
    print("-" * 70)
    for name, d in report["key_facts"].items():
        print(f"{name:<14} {d['rate']}%{' '*4} {d['avg_latency_ms']}ms{' '*5} {d['avg_results'] if 'avg_results' in d else 'N/A':<12} {d['tested']}项")
    
    print(f"\n⚡ 延迟对比 (毫秒)")
    print("-" * 70)
    print(f"{'系统':<14} {'存储延迟':<14} {'召回延迟':<14} {'总操作数'}")
    print("-" * 70)
    for name, d in report["latency"].items():
        print(f"{name:<14} {d['store_ms']}ms{' '*6} {d['recall_ms']}ms{' '*6} {d['total_ops']}")
    
    print(f"\n💡 核心结论")
    print("-" * 70)
    for i, rec in enumerate(report["recommendations"], 1):
        print(f"   {i}. {rec}")
    print("\n" + "=" * 70)


def main():
    print("=" * 70)
    print(" " * 12 + "记忆系统 Benchmark v2.0")
    print("=" * 70)
    print()
    
    bm = MemoryBenchmark()
    bm.init_systems()
    bm.run()
    
    data = bm.conv_gen.generate(days=30, turns_per_day=38)
    report = bm.generate_report()
    bm.save(report, data)
    print_report(report)


if __name__ == "__main__":
    main()
