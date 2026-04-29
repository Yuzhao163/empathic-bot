#!/usr/bin/env python3
"""
生成完整的详细过程报告
"""

import json
from pathlib import Path

results_dir = Path("/home/admin/.openclaw/workspace/memory-benchmark/results/detailed")

with open(results_dir / "full_traces.json") as f:
    data = json.load(f)

sys_reports = data["systems"]
conv_sample = data["conversation_sample"]
key_facts = data["key_facts"]

print("=" * 90)
print(" " * 30 + "记忆系统详细过程报告")
print("=" * 90)
print()
print(f"总对话轮次: {data['total_turns']} 轮")
print(f"总天数: {data['total_days']} 天")
print(f"评测系统: {', '.join(sys_reports.keys())}")
print()

# ====================== 第一部分：每个系统详细执行轨迹 ======================

for sys_name, report in sys_reports.items():
    print()
    print("=" * 90)
    print(f"【{report['name']}】详细执行轨迹")
    print(f"类型: {report['type']} | 存储次数: {report['stores']} | 召回次数: {report['recalls']} | 去重: {report['dedup']} | 最终记录数: {report['total']}")
    print("=" * 90)

    store_log = report["store_log"]
    recall_log = report["recall_log"]
    snapshots = report["snapshots"]

    # ---- 存储轨迹：展示前30条和后10条 ----
    print()
    print(f"  【存储轨迹】共 {len(store_log)} 条记录")
    print(f"  {'轮次':<12} {'事件':<8} {'分类':<15} {'重要性':<8} {'延迟':<8} {'当页/总数/备注'}")
    print("  " + "-" * 90)

    for entry in store_log[:15]:
        e = entry
        print(f"  {e['d']}/{e['t']:<10} {e['e']:<8} {e.get('cat',''):<15} {e.get('imp',''):<8.2f} {e.get('lat',''):<8.2f} {str(e.get('total',''))[:20]}")

    if len(store_log) > 30:
        print(f"  ... (省略 {len(store_log)-30} 条) ...")

    for entry in store_log[-5:]:
        e = entry
        print(f"  {e['d']}/{e['t']:<10} {e['e']:<8} {e.get('cat',''):<15} {e.get('imp',''):<8.2f} {e.get('lat',''):<8.2f} {str(e.get('total',''))[:20]}")

    # ---- 存储操作类型统计 ----
    events = {}
    for e in store_log:
        evt = e["e"]
        events[evt] = events.get(evt, 0) + 1
    print()
    print(f"  存储事件分布: {events}")
    cats = {}
    for e in store_log:
        c = e.get("cat", "unknown")
        cats[c] = cats.get(c, 0) + 1
    print(f"  记忆类别分布: {cats}")
    print(f"  平均存储延迟: {sum(e.get('lat',0) for e in store_log)/len(store_log):.2f}ms" if store_log else "")

    # ---- 召回轨迹：展示前20条 ----
    print()
    print(f"  【召回轨迹】共 {len(recall_log)} 条记录")
    print(f"  {'查询':<50} {'命中':<6} {'延迟':<8} {'Top结果'}")
    print("  " + "-" * 90)

    for entry in recall_log[:20]:
        q = entry["query"][:48]
        hits = entry["hits"]
        lat = entry.get("lat", 0)
        top = ""
        if entry.get("results"):
            top = entry["results"][0]["preview"][:25] if "preview" in entry["results"][0] else str(entry["results"][0])[:25]
        print(f"  {q:<50} {hits:<6} {lat:<8.2f} {top}")

    if len(recall_log) > 25:
        print(f"  ... (省略 {len(recall_log)-25} 条) ...")

    for entry in recall_log[-5:]:
        q = entry["query"][:48]
        hits = entry["hits"]
        lat = entry.get("lat", 0)
        print(f"  {q:<50} {hits:<6} {lat:<8.2f} ...")

    # ---- 每日快照 ----
    print()
    print(f"  【状态快照】共 {len(snapshots)} 个关键节点")
    for snap in snapshots[:15]:
        print(f"    Day{snap['day']}: {snap['event']} | records={snap['n']}")

    print()

# ====================== 第二部分：同一对话在所有系统中的对比 ======================

print()
print("=" * 90)
print(" " * 30 + "关键对话跨系统对比")
print("=" * 90)

# 找几个典型的存储和召回场景
test_turns = ["d1_t1", "d1_t5", "d5_t10", "d15_t20", "d30_t35"]

for sys_name, report in sys_reports.items():
    store_by_turn = {e["t"]: e for e in report["store_log"]}

    print()
    print(f"【{report['name']}】")

    for tid in test_turns:
        if tid in store_by_turn:
            e = store_by_turn[tid]
            preview = e.get("preview", "")[:45]
            extra = ""
            if "layer" in e: extra = f" [Layer={e['layer']}]"
            if "str" in e: extra = f" [Strength={e['str']:.4f}]"
            if "new_syn" in e: extra = f" [Synapses={e['new_syn']}]"
            if "ep_len" in e: extra = f" [EpLen={e['ep_len']}]"
            print(f"  STORE {tid}: {e['cat']:<15} imp={e.get('imp','?'):.2f}{extra}")
            print(f"    → {preview}")
        else:
            print(f"  STORE {tid}: (未记录/已去重)")

    print()

# ====================== 第三部分：关键事实30天召回对比 ======================

print()
print("=" * 90)
print(" " * 25 + "关键事实召回能力详细对比 (30天后)")
print("=" * 90)
print()
print("测试查询：每个系统的recall方法对关键实体的查询结果")
print()

# 对每个系统进行关键事实召回测试
for sys_name, report in sys_reports.items():
    recall_log = report["recall_log"]

    print(f"【{report['name']}】")

    # 找最后几天的recall（模拟30天后查询）
    recent_recalls = [r for r in recall_log if any(k in r["query"] for k in ["电商", "咖啡", "代码", "日本"])]

    if recent_recalls:
        for r in recent_recalls[:3]:
            print(f"  Query: \"{r['query'][:50]}\"")
            print(f"  命中: {r['hits']} 条 | 延迟: {r.get('lat', 0):.2f}ms | 方法: {r.get('method', r.get('endpoint', 'N/A'))}")
            for res in r.get("results", [])[:2]:
                if "score" in res:
                    print(f"    [{res.get('score', 0):.3f}] {res.get('preview', '')[:45]}")
                elif "cos" in res:
                    print(f"    [cos={res.get('cos', 0):.3f}] {res.get('preview', '')[:45]}")
            print()
    else:
        print(f"  无相关召回记录")
        print()

# ====================== 第四部分：延迟与存储详细数据 ======================

print()
print("=" * 90)
print(" " * 30 + "性能详细数据")
print("=" * 90)
print()

print(f"{'系统':<12} {'类型':<18} {'存储次':<8} {'召回次':<8} {'去重次':<8} {'最终记录':<10} {'avg_lat(ms)':<12}")
print("-" * 90)

for sys_name, report in sys_reports.items():
    stores = report["store_log"]
    recalls = report["recall_log"]
    avg_lat = sum(e.get("lat", 0) for e in recalls) / len(recalls) if recalls else 0
    print(f"{report['name']:<12} {report['type']:<18} {report['stores']:<8} {report['recalls']:<8} {report['dedup']:<8} {report['total']:<10} {avg_lat:<12.2f}")

print()

# ====================== 第五部分：系统间行为差异对比 ======================

print()
print("=" * 90)
print(" " * 30 + "系统行为差异对比 (同一对话 d1_t1)")
print("=" * 90)
print()

turn_id = "d1_t1"

print(f"{'系统':<12} {'STORE结果':<50} {'recall结果数':<10}")
print("-" * 90)

for sys_name, report in sys_reports.items():
    store_log = report["store_log"]
    recall_log = report["recall_log"]

    entry = next((e for e in store_log if e["t"] == turn_id), None)
    if entry:
        preview = entry.get("preview", "")[:45]
        result = f"{entry['e']}: {preview}"
    else:
        result = "DEDUP/未记录"

    recalls_for_turn = [r for r in recall_log if turn_id in r.get("query", "")]
    recall_count = recalls_for_turn[0]["hits"] if recalls_for_turn else 0

    print(f"{report['name']:<12} {result:<50} {recall_count}")

print()

# ====================== 第六部分：去重机制详解 ======================

print()
print("=" * 90)
print(" " * 30 + "去重机制行为分析")
print("=" * 90)
print()

for sys_name, report in sys_reports.items():
    store_log = report["store_log"]
    dedup_events = [e for e in store_log if e["e"] == "DEDUP"]
    store_events = [e for e in store_log if e["e"] == "STORE"]

    print(f"【{report['name']}】")
    print(f"  STORE事件: {len(store_events)} 次")
    print(f"  DEDUP事件: {len(dedup_events)} 次")
    print(f"  去重率: {len(dedup_events)/(len(store_events)+len(dedup_events))*100:.1f}%" if store_events else "")

    if dedup_events:
        print(f"  DEDUP样本（前3条）:")
        for e in dedup_events[:3]:
            print(f"    Day{e['d']} Turn{e['t']}: ms={e.get('ms', 'N/A')}")

    print()

print()
print("=" * 90)
print("报告生成完毕")
print("=" * 90)
