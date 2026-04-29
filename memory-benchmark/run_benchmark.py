#!/usr/bin/env python3
"""
Memory Benchmark - 主运行程序
模拟30天1000+轮对话，评测各记忆系统
"""

import json
import sys
import time
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

# 添加当前目录到 path
sys.path.insert(0, str(Path(__file__).parent))

from conversation_generator import ConversationGenerator
from memory_interface import create_all_systems, BaseMemorySystem, MemoryRecord


class MemoryBenchmark:
    def __init__(self):
        self.conversation_gen = ConversationGenerator()
        self.systems: Dict[str, BaseMemorySystem] = {}
        self.store_logs: Dict[str, List] = {key: [] for key in ["file", "mem0", "qdrant", "letta", "fluid", "neural"]}
        self.recall_logs: Dict[str, List] = {key: [] for key in ["file", "mem0", "qdrant", "letta", "fluid", "neural"]}
        self.day_summaries: List[Dict] = []
        self.key_fact_recall_results: Dict[str, Dict] = {}
        
    def initialize(self):
        """初始化所有记忆系统"""
        print("=" * 60)
        print("初始化记忆系统...")
        print("=" * 60)
        
        self.systems = create_all_systems()
        
        for name, system in self.systems.items():
            print(f"  [{system.name}] 类型: {system.system_type}")
        
        print()
    
    def _categorize_memory(self, turn: Dict) -> tuple:
        """根据对话内容分类记忆"""
        msg = turn["user_message"]
        topic = turn["topic"]
        
        if any(kw in msg for kw in ["喜欢", "偏好", "我的风格", "记一下"]):
            category = "preference"
            content = f"[偏好] {topic}: {msg}"
        elif any(kw in msg for kw in ["决定", "选型", "确认", "用"]):
            category = "decision"
            content = f"[决策] {topic}: {msg}"
        elif any(kw in msg for kw in ["bug", "报错", "问题", "修复"]):
            category = "error"
            content = f"[问题] {topic}: {msg}"
        elif any(kw in msg for kw in ["之前", "上次", "记得", "结论"]):
            category = "recall_trigger"
            content = f"[历史查询] {topic}: {msg}"
        else:
            category = "fact"
            content = f"[事实] {topic}: {msg}"
        
        # 提取重要性
        importance = turn.get("fact_importance", 0.5)
        if "偏好" in category:
            importance = max(importance, 0.7)
        elif "决策" in category:
            importance = max(importance, 0.85)
        
        return category, content, importance
    
    def _should_recall(self, turn: Dict, day: int) -> bool:
        """判断是否应该触发召回"""
        # 每天前几轮通常需要召回之前的内容
        turn_in_day = int(turn["turn_id"].split("_t")[1])
        if turn_in_day <= 3 and day > 1:
            return True
        # reference_past 类话题
        if turn["category"] == "reference_past":
            return True
        # 随机触发（模拟人类自然回忆）
        if random.random() < 0.15:
            return True
        return False
    
    def run(self):
        """运行完整评测"""
        print("生成模拟对话...")
        conversation_data = self.conversation_gen.generate_full_conversation()
        conversations = conversation_data["conversations"]
        key_facts = conversation_data["key_facts"]
        
        print(f"生成完成: {conversation_data['total_days']}天, {conversation_data['total_turns']}轮对话")
        print(f"关键事实数量: {len(key_facts)}")
        print()
        print("=" * 60)
        print("开始评测...")
        print("=" * 60)
        
        current_day = 0
        
        for i, turn in enumerate(conversations):
            day = turn["day"]
            
            # 新的一天开始
            if day != current_day:
                current_day = day
                day_start = time.perf_counter()
                print(f"\n--- Day {day} --- (第 {i+1}/{len(conversations)} 轮)")
                
                # 每个系统记录一天开始前的状态
                for name, system in self.systems.items():
                    stats = system.get_stats()
                    self.day_summaries.append({
                        "day": day,
                        "system": name,
                        "records_before_day": stats.get("current_records", stats.get("storage_records", 0)),
                        "total_stores": stats.get("total_stores", 0),
                        "total_recalls": stats.get("total_recalls", 0),
                    })
            
            # 存储记忆
            category, content, importance = self._categorize_memory(turn)
            tags = [turn["topic"], category]
            
            for name, system in self.systems.items():
                store_result = system.store(
                    content=content,
                    category=category,
                    importance=importance,
                    day=day,
                    turn_id=turn["turn_id"],
                    topic=turn["topic"],
                    tags=tags,
                )
                
                self.store_logs[name].append({
                    "turn_id": turn["turn_id"],
                    "day": day,
                    "category": category,
                    "importance": importance,
                    "topic": turn["topic"],
                    "content_preview": content[:50] + "...",
                    "latency_ms": store_result.latency_ms,
                    "success": store_result.success,
                    "deduplicated": store_result.deduplicated,
                })
            
            # 召回测试
            if self._should_recall(turn, day):
                recall_query = turn["user_message"]
                
                for name, system in self.systems.items():
                    recall_result = system.recall(
                        query=recall_query,
                        limit=3,
                        day=day - 1 if day > 1 else None,
                    )
                    
                    self.recall_logs[name].append({
                        "turn_id": turn["turn_id"],
                        "day": day,
                        "query": recall_query[:60],
                        "results_count": len(recall_result.records),
                        "latency_ms": recall_result.latency_ms,
                        "method": recall_result.recall_method,
                    })
            
            # 进度提示
            if (i + 1) % 100 == 0:
                print(f"  进度: {i+1}/{len(conversations)} 轮 ({100*(i+1)//len(conversations)}%)")
        
        # 测试关键事实召回
        print("\n" + "=" * 60)
        print("测试关键事实30天后召回能力...")
        print("=" * 60)
        
        for fact in key_facts:
            first_day = fact["first_mentioned"]
            if first_day is None:
                first_day = 5  # 默认第5天
            
            # 模拟30天后查询
            query = f"关于{fact['entity']}"
            
            for name, system in self.systems.items():
                result = system.recall(query=query, limit=3, day=None)
                
                found = any(
                    fact["fact"] in r.content or fact["entity"] in r.content
                    for r in result.records
                )
                
                if name not in self.key_fact_recall_results:
                    self.key_fact_recall_results[name] = {}
                
                self.key_fact_recall_results[name][fact["entity"]] = {
                    "first_mentioned_day": first_day,
                    "found_on_day30": found,
                    "results_count": len(result.records),
                    "top_relevance": result.relevance_scores[0] if result.relevance_scores else 0,
                    "latency_ms": result.latency_ms,
                }
        
        print("召回能力测试完成")
    
    def generate_report(self) -> Dict:
        """生成评测报告"""
        print("\n" + "=" * 60)
        print("生成评测报告...")
        print("=" * 60)
        
        report = {
            "benchmark_info": {
                "date": datetime.now().isoformat(),
                "total_days": 30,
                "total_turns": sum(len(logs) for logs in self.store_logs.values()) // len(self.systems),
                "systems_tested": list(self.systems.keys()),
            },
            "storage_analysis": {},
            "recall_analysis": {},
            "key_fact_recall": {},
            "latency_comparison": {},
            "recommendations": [],
        }
        
        # 存储分析
        print("分析存储模式...")
        for name, system in self.systems.items():
            stats = system.get_stats()
            store_logs = self.store_logs[name]
            
            categories = {}
            for log in store_logs:
                cat = log["category"]
                categories[cat] = categories.get(cat, 0) + 1
            
            deduplicated = sum(1 for log in store_logs if log["deduplicated"])
            
            report["storage_analysis"][name] = {
                "system_name": stats["system"],
                "system_type": stats["type"],
                "storage_format": stats.get("storage_format", "unknown"),
                "total_records": stats.get("storage_records", stats.get("current_records", 0)),
                "total_stores": stats.get("total_stores", 0),
                "deduplications": deduplicated,
                "category_distribution": categories,
                "storage_pattern": self._describe_storage_pattern(stats),
            }
        
        # 召回分析
        print("分析召回能力...")
        for name, system in self.systems.items():
            recall_logs = self.recall_logs[name]
            
            avg_latency = sum(r["latency_ms"] for r in recall_logs) / len(recall_logs) if recall_logs else 0
            avg_results = sum(r["results_count"] for r in recall_logs) / len(recall_logs) if recall_logs else 0
            
            methods = {}
            for log in recall_logs:
                method = log["method"]
                methods[method] = methods.get(method, 0) + 1
            
            report["recall_analysis"][name] = {
                "total_recalls": len(recall_logs),
                "avg_latency_ms": round(avg_latency, 2),
                "avg_results_per_recall": round(avg_results, 2),
                "methods_used": methods,
            }
        
        # 关键事实召回
        print("分析关键事实召回...")
        for name in self.systems.keys():
            if name in self.key_fact_recall_results:
                results = self.key_fact_recall_results[name]
                found_count = sum(1 for r in results.values() if r["found_on_day30"])
                avg_latency = sum(r["latency_ms"] for r in results.values()) / len(results)
                avg_relevance = sum(r["top_relevance"] for r in results.values()) / len(results)
                
                report["key_fact_recall"][name] = {
                    "key_facts_tested": len(results),
                    "found_on_day30": found_count,
                    "recall_rate": round(found_count / len(results) * 100, 1) if results else 0,
                    "avg_latency_ms": round(avg_latency, 2),
                    "avg_relevance_score": round(avg_relevance, 3),
                    "per_fact_details": results,
                }
        
        # 延迟对比
        for name in self.systems.keys():
            stores = self.store_logs[name]
            recalls = self.recall_logs[name]
            
            avg_store = sum(s["latency_ms"] for s in stores) / len(stores) if stores else 0
            avg_recall = sum(r["latency_ms"] for r in recalls) / len(recalls) if recalls else 0
            
            report["latency_comparison"][name] = {
                "avg_store_latency_ms": round(avg_store, 2),
                "avg_recall_latency_ms": round(avg_recall, 2),
                "total_operations": len(stores) + len(recalls),
            }
        
        # 生成建议
        report["recommendations"] = self._generate_recommendations(report)
        
        return report
    
    def _describe_storage_pattern(self, stats: Dict) -> str:
        """描述存储模式"""
        storage_type = stats.get("type", "unknown")
        storage_format = stats.get("storage_format", "")
        
        patterns = {
            "file-based": "文件树结构，按 category/day/topic 分目录存储 Markdown/JSON",
            "vector + structured": "向量数据库 + 结构化元数据，语义索引",
            "vector_database": "纯向量存储，相似度检索",
            "layered_memory": "核心记忆(限流) + 归档记忆 + 召回索引三层分离",
            "ebbinghaus_decay": "带衰减系数的内存存储，动态计算记忆强度",
            "associative_graph": "图数据库结构，节点+带类型突触连接",
        }
        
        return patterns.get(storage_type, storage_format)
    
    def _generate_recommendations(self, report: Dict) -> List[str]:
        """生成推荐建议"""
        recommendations = []
        
        # 找最优召回率
        recall_rates = {}
        for name, data in report["key_fact_recall"].items():
            recall_rates[name] = data["recall_rate"]
        
        best_recall = max(recall_rates, key=recall_rates.get)
        recommendations.append(f"召回率最高: {best_recall} ({recall_rates[best_recall]}%)")
        
        # 找最低延迟
        avg_latencies = {}
        for name, data in report["latency_comparison"].items():
            avg_latencies[name] = data["avg_recall_latency_ms"]
        
        lowest_latency = min(avg_latencies, key=avg_latencies.get)
        recommendations.append(f"延迟最低: {lowest_latency} ({avg_latencies[lowest_latency]}ms)")
        
        # 场景建议
        recommendations.extend([
            "需要快速原型 → Memory-File（零配置，即开即用）",
            "需要语义理解 → mem0 / Memory-Qdrant（向量检索）",
            "需要层级管理 → Letta-Sim（核心记忆+归档分离）",
            "需要模拟人脑遗忘 → FluidMem-Sim（艾宾浩斯曲线）",
            "需要联想推理 → NeuralMem-Sim（图谱突触传播）",
        ])
        
        return recommendations
    
    def save_results(self, report: Dict, conversation_data: Dict):
        """保存结果到文件"""
        output_dir = Path("/home/admin/.openclaw/workspace/memory-benchmark/results")
        output_dir.mkdir(exist_ok=True)
        
        # 保存主报告
        report_path = output_dir / "benchmark_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        # 保存对话数据
        conv_path = output_dir / "conversations.json"
        with open(conv_path, "w", encoding="utf-8") as f:
            # 只保存关键信息以节省空间
            conv_summary = {
                "total_days": conversation_data["total_days"],
                "total_turns": conversation_data["total_turns"],
                "key_facts": conversation_data["key_facts"],
                "conversations": conversation_data["conversations"][:50] + conversation_data["conversations"][-10:],  # 采样
            }
            json.dump(conv_summary, f, ensure_ascii=False, indent=2)
        
        # 保存详细日志
        logs_path = output_dir / "detailed_logs.json"
        logs_data = {
            "store_logs": {k: v[:100] for k, v in self.store_logs.items()},  # 每种只保留100条
            "recall_logs": {k: v[:100] for k, v in self.recall_logs.items()},
            "day_summaries": self.day_summaries,
        }
        with open(logs_path, "w", encoding="utf-8") as f:
            json.dump(logs_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n结果已保存至: {output_dir}/")
        print(f"  - benchmark_report.json (主报告)")
        print(f"  - conversations.json (对话数据采样)")
        print(f"  - detailed_logs.json (详细日志)")
        
        return output_dir


def print_report(report: Dict):
    """格式化打印报告"""
    print("\n")
    print("=" * 70)
    print(" " * 20 + "记忆系统评测报告")
    print("=" * 70)
    
    bi = report["benchmark_info"]
    print(f"\n📊 评测概览")
    print(f"   模拟时长: {bi['total_days']} 天")
    print(f"   总对话轮次: {bi['total_turns']} 轮")
    print(f"   评测系统: {', '.join(bi['systems_tested'])}")
    
    print(f"\n📦 存储模式对比")
    print("-" * 70)
    print(f"{'系统':<15} {'类型':<20} {'记录数':<10} {'去重次数':<10} {'存储模式'}")
    print("-" * 70)
    for name, data in report["storage_analysis"].items():
        print(f"{data['system_name']:<15} {data['system_type']:<20} {data['total_records']:<10} {data['deduplications']:<10} {data['storage_pattern'][:30]}")
    
    print(f"\n🔍 召回能力对比 (30天后)")
    print("-" * 70)
    print(f"{'系统':<15} {'召回率':<12} {'平均延迟':<15} {'相关度得分':<12} {'总召回次数'}")
    print("-" * 70)
    for name, data in report["key_fact_recall"].items():
        print(f"{name:<15} {data['recall_rate']}%{' '*6} {data['avg_latency_ms']}ms{' '*7} {data['avg_relevance_score']:<12.3f} {data['key_facts_tested']}项")
    
    print(f"\n⚡ 延迟对比 (毫秒)")
    print("-" * 70)
    print(f"{'系统':<15} {'存储延迟':<18} {'召回延迟':<18} {'总操作数'}")
    print("-" * 70)
    for name, data in report["latency_comparison"].items():
        print(f"{name:<15} {data['avg_store_latency_ms']}ms{' '*8} {data['avg_recall_latency_ms']}ms{' '*8} {data['total_operations']}")
    
    print(f"\n💡 核心发现与建议")
    print("-" * 70)
    for i, rec in enumerate(report["recommendations"], 1):
        print(f"   {i}. {rec}")
    
    print("\n" + "=" * 70)


def main():
    print("=" * 70)
    print(" " * 15 + "记忆系统 Benchmark 评测工具 v1.0")
    print("=" * 70)
    print()
    
    benchmark = MemoryBenchmark()
    benchmark.initialize()
    benchmark.run()
    
    conversation_data = benchmark.conversation_gen.generate_full_conversation()
    report = benchmark.generate_report()
    
    output_dir = benchmark.save_results(report, conversation_data)
    print_report(report)
    
    # 打印文件路径方便查看
    print(f"\n📁 完整报告文件: {output_dir}/benchmark_report.json")


if __name__ == "__main__":
    main()
