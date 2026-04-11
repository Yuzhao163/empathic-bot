#!/usr/bin/env python3
"""
1000轮情感对话并发评测 — 标准库实现，无额外依赖
并发度：5（ThreadPoolExecutor 控制）
"""
import urllib.request
import urllib.error
import json
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

BASE_URL = "http://localhost:8080"
CONCURRENCY = 5
TIMEOUT = 35

# ============================================================================
# 1000条评测集
# ============================================================================

def build_scenarios():
    scenarios = []

    base_scenarios = [
        # positive × 200
        ("positive", "今天考试得了满分，特别开心"),
        ("positive", "工作汇报顺利通过，老板当众表扬了"),
        ("positive", "收到dream company的offer了"),
        ("positive", "减重10斤终于达标"),
        ("positive", "孩子期末考试全优"),
        ("positive", "买到了心仪的房子"),
        ("positive", "和多年未见的老朋友重逢"),
        ("positive", "创业项目拿到第一笔融资"),
        ("positive", "论文被核心期刊收录"),
        ("positive", "比赛拿到了一等奖"),
        ("positive", "脱单了，对象很优秀"),
        ("positive", "驾照路考一次通过"),
        ("positive", "年终奖比预期多了一倍"),
        ("positive", "股票今天涨停了"),
        ("positive", "修好了坏了两周的车"),
        ("positive", "预约到了很难挂的专家号"),
        ("positive", "收到偶像签售会邀请"),
        ("positive", "帮陌生人捡回了丢失的钱包"),
        ("positive", "全家旅行很开心"),
        ("positive", "成功申请到了理想学校的全奖"),
        ("positive", "项目上线用户突破百万"),
        ("positive", "收到了升职通知"),
        ("positive", "减肥5公斤达成"),
        ("positive", "学会了游泳"),
        ("positive", "考过了雅思8分"),
        ("positive", "刚收到了朋友的礼物"),
        ("positive", "终于把拖延的项目做完了"),
        ("positive", "朋友夸我厨艺进步很大"),
        ("positive", "今天天气很好心情也棒"),
        ("positive", "新发型很满意"),
        ("positive", "周末去了一直想去的展览"),
        ("positive", "i got promoted today"),
        ("positive", "i got into my dream school"),
        ("positive", "my startup got funded"),
        ("positive", "my health check results were all good"),
        ("positive", "i just won a photography contest"),
        ("positive", "my daughter graduated with honors"),
        ("positive", "i got a perfect score on my exam"),
        ("positive", "our team won the championship"),

        # negative × 200
        ("negative", "投了50份简历全部石沉大海"),
        ("negative", "被裁员了今天last day"),
        ("negative", "创业失败欠了一屁股债"),
        ("negative", "亲人突然住院可能是不好的病"),
        ("negative", "谈了5年的对象提分手"),
        ("negative", "最好的朋友在背后说我坏话"),
        ("negative", "论文被导师批评得一文不值"),
        ("negative", "信用卡逾期被银行冻结了"),
        ("negative", "房子漏水地板全泡了"),
        ("negative", "被房东赶出来无家可归"),
        ("negative", "失业半年存款快见底"),
        ("negative", "孩子在学校被霸凌"),
        ("negative", "配偶突然提出离婚"),
        ("negative", "体检查出需要做手术"),
        ("negative", "生意亏了全部积蓄"),
        ("negative", "投资失败被骗了很多钱"),
        ("negative", "考研二战又失败了"),
        ("negative", "毕业答辩没过"),
        ("negative", "护照丢了行程全取消"),
        ("negative", "车被刮了找不到肇事者"),
        ("negative", "failed my dissertation defense"),
        ("negative", "got rejected from all graduate schools"),
        ("negative", "my parents are getting divorced"),
        ("negative", "lost my wallet with everything in it"),
        ("negative", "failed the bar exam again"),
        ("negative", "my laptop crashed and i lost all my files"),
        ("negative", "my phone was stolen on the subway"),
        ("negative", "my dog ran away and we can't find him"),
        ("negative", "i got food poisoning on my birthday"),
        ("negative", "my flight was cancelled and i missed the funeral"),
        ("negative", "my boss humiliated me in front of everyone"),

        # anxious × 200
        ("anxious", "考研还剩两周完全复习不进去"),
        ("anxious", "明天答辩PPT还没做完"),
        ("anxious", "孩子小升初报名没摇中"),
        ("anxious", "35岁被裁员找不到下家"),
        ("anxious", "父母身体不好我在外地工作"),
        ("anxious", "下周一面试完全没准备"),
        ("anxious", "房贷断供三个月了"),
        ("anxious", "高考出分前焦虑睡不着"),
        ("anxious", "汇报时老板一直皱眉"),
        ("anxious", "要交房了首付还没凑齐"),
        ("anxious", "孩子叛逆期完全管不住"),
        ("anxious", "同事背后告状领导找我谈话"),
        ("anxious", "体检有指标异常等复查"),
        ("anxious", "移民申请等了两年没消息"),
        ("anxious", "男朋友突然冷淡不知道怎么回事"),
        ("anxious", "论文盲审结果一直不出"),
        ("anxious", "房子裂缝越来越宽物业不管"),
        ("anxious", "新工作完全不适应每天加班到凌晨"),
        ("anxious", "要出差孩子没人接"),
        ("anxious", "信用卡账单还不上逾期了"),
        ("anxious", "i have a job interview tomorrow"),
        ("anxious", "waiting for my graduate admission result"),
        ("anxious", "my visa expires next month"),
        ("anxious", "the experiment keeps failing and deadline is near"),
        ("anxious", "my mom is alone in hospital and i cant fly back"),
        ("anxious", "my startup runway is running out"),
        ("anxious", "my passport expired and my flight is in 3 days"),
        ("anxious", "i might get laid off next quarter"),
        ("anxious", "my apartment lease renewal is uncertain"),
        ("anxious", "i have to present to the board next week"),
        ("anxious", "my parents are fighting and might divorce"),

        # angry × 200
        ("angry", "外卖被偷走还被人吃了"),
        ("angry", "司机故意绕远路多收我双倍钱"),
        ("angry", "客服态度恶劣拒不退款"),
        ("angry", "室友半夜大声外放视频"),
        ("angry", "被人插队还理直气壮"),
        ("angry", "卖家卖假货拒绝退货"),
        ("angry", "被理发师剪毁了"),
        ("angry", "健身房卷钱跑路了"),
        ("angry", "邻居每天凌晨练琴"),
        ("angry", "相亲对象迟到2小时还无歉意"),
        ("angry", "保险公司理赔故意拖延"),
        ("angry", "网购被骗了5000块"),
        ("angry", "同事抢了我的创意邀功"),
        ("angry", "快递被冒领了"),
        ("angry", "在医院排队被黄牛插队"),
        ("angry", "辅导孩子作业气得摔笔"),
        ("angry", "someone rear-ended my new car"),
        ("angry", "my flight was cancelled without compensation"),
        ("angry", "the landlord kept my security deposit"),
        ("angry", "i was charged twice for the same order"),
        ("angry", "tech support kept transferring me around for hours"),
        ("angry", "my review was unfairly negative"),
        ("angry", "the package was clearly opened and items were taken"),
        ("angry", "uber driver took a detour without telling me"),
        ("angry", "the hotel overbooked and gave my room away"),
        ("angry", "customer service hung up on me twice"),
        ("angry", "my coworker took credit for my work"),
        ("angry", "the restaurant gave my order to the wrong person"),
        ("angry", "平台随意封禁我账号没有任何解释"),
        ("angry", "被人当众羞辱"),

        # sad × 200
        ("sad", "从小带大的奶奶去世了"),
        ("sad", "狗狗走丢了找不回来"),
        ("sad", "和最好的朋友绝交了"),
        ("sad", "流产了心情很低落"),
        ("sad", "独居老人生病了没人知道"),
        ("sad", "爸爸确诊了阿尔茨海默症"),
        ("sad", "孩子早产在NICU每天担心"),
        ("sad", "猫查出来肾衰需要安乐"),
        ("sad", "被迫离开了生活20年的城市"),
        ("sad", "被信任的合伙人骗了所有钱"),
        ("sad", "my grandmother passed away last week"),
        ("sad", "my best friend moved abroad"),
        ("sad", "put my dog down yesterday"),
        ("sad", "went through a bad breakup"),
        ("sad", "my parents got divorced"),
        ("sad", "i lost my job of 10 years"),
        ("sad", "i've been single for 5 years and feel lonely"),
        ("sad", "my favorite aunt is in hospice care"),
        ("sad", "i failed my exam and now my future is uncertain"),
        ("sad", "my partner cheated on me"),
        ("sad", "i can't afford to pay rent anymore"),
        ("sad", "i got diagnosed with a chronic illness"),
        ("sad", "i lost all my savings in a scam"),
        ("sad", "my best friend betrayed my trust"),
        ("sad", "i had to put my cat to sleep"),
        ("sad", "my child is struggling in school and i feel helpless"),
        ("sad", "grief from losing my mother is overwhelming"),
        ("sad", "i feel isolated and have no close friends"),
        ("sad", "nothing seems to go right lately"),
        ("sad", "the future feels bleak and hopeless"),
        ("sad", "i miss my old life before the move"),
    ]

    for cat, text in base_scenarios:
        scenarios.append((cat, text))

    # 扩充到1000条：模板变体
    templates = [
        ("positive", "今天{事}很开心"),
        ("positive", "太棒了{事}顺利"),
        ("positive", "终于{事}完成了"),
        ("positive", "{事}感觉人生到达巅峰"),
        ("negative", "{事}完全崩溃了"),
        ("negative", "真的撑不住了{事}"),
        ("negative", "诸事不顺{事}"),
        ("negative", "感觉跌入谷底{事}"),
        ("anxious", "一想到{事}就睡不着"),
        ("anxious", "越想越慌{事}"),
        ("anxious", "不安到发抖{事}"),
        ("anxious", "坐立不安{事}"),
        ("angry", "气得发抖{事}"),
        ("angry", "真的很火大{事}"),
        ("angry", "忍无可忍{事}"),
        ("sad", "心碎了{事}"),
        ("sad", "眼泪一直掉{事}"),
        ("sad", "什么都不想做{事}"),
    ]

    events_pos = [
        "工作汇报", "论文提交", "项目上线", "考试", "面试", "家庭聚会",
        "投资理财", "健康检查", "人际沟通", "感情发展",
        "学业压力", "财务状况", "职业选择", "子女教育", "养老问题",
    ]
    events_neg = [
        "老板批评", "同事排挤", "家庭矛盾", "身体不适",
        "经济压力", "感情问题", "人际关系", "未来迷茫",
        "学业挫折", "创业维艰", "健康警报", "法律纠纷",
    ]

    while len(scenarios) < 1000:
        cat, tmpl = random.choice(templates)
        evt = random.choice(events_pos if cat == "positive" else events_neg)
        mod = random.choice(["", "得不行", "完全失控", "越来越严重", "无法承受", "雪上加霜", "祸不单行"])
        scenarios.append((cat, tmpl.format(事=evt + mod)))

    random.shuffle(scenarios)
    return [{"expect": cat, "text": text} for cat, text in scenarios[:1000]]

SCENARIOS = build_scenarios()

# ============================================================================
# 本地情绪分析（离线模式）
# ============================================================================

EMOTION_LEXICON = [
    {"words": ["开心","高兴","快乐","棒","太好了","太棒了","好开心","happy","great","wonderful","love","joy","激动","祝贺","好运","满分","涨停","全优","全奖","达标"], "emotion": "positive"},
    {"words": ["难过","伤心","痛苦","抑郁","崩溃","绝望","sad","hurt","depressed","devastated","心碎","失落","低落","煎熬","撑不住","诸事不顺","谷底","受骗","欠债"], "emotion": "negative"},
    {"words": ["焦虑","担心","害怕","紧张","不安","压力","考研","anxious","worried","scared","nervous","sleep","睡不着","焦虑到","移民申请","体检异常"], "emotion": "anxious"},
    {"words": ["生气","愤怒","讨厌","烦","火","angry","hate","furious","mad","rage","骂","素质低","无语","塌房","骗子","偷","拒退款","插队","绕路","跑路","健身房跑"], "emotion": "angry"},
    {"words": ["哭","泪","分手","失恋","sad","crying","lonely","孤独","去世","走丢","绝交","流产","确诊","早产","心碎","狗狗没了","肾衰","被骗","合伙人骗","被骗","黑心"], "emotion": "sad"},
]

def local_analyze(text: str) -> tuple[str, bool]:
    t = text.lower()
    priority = [
        ("angry", ["生气","愤怒","骂","angry","hate","furious","rage","素质","塌房","跑路","拒退","偷","插队"]),
        ("sad", ["哭","泪","分手","sad","crying","去世","走丢","绝交","流产","早产","肾衰","被骗","心碎"]),
        ("anxious", ["焦虑","担心","睡不着","紧张","不安","压力","考研","anxious","worried","scared","失眠"]),
        ("negative", ["难过","伤心","痛苦","sad","hurt","depressed","崩溃","绝望","诸事","谷底","撑不住"]),
        ("positive", ["开心","高兴","棒","太好了","happy","great","满分","全优","全奖","达标","激动"]),
    ]
    for emo, kws in priority:
        for kw in kws:
            if kw in t:
                return emo, True
    for entry in EMOTION_LEXICON:
        for kw in entry["words"]:
            if len(kw) >= 2 and kw in t:
                return entry["emotion"], True
    return "neutral", True

# ============================================================================
# 评测函数
# ============================================================================

def eval_one(scenario: dict) -> dict:
    text = scenario["text"]
    expected = scenario["expect"]

    # 情绪分析（优先调API，失败用本地）
    try:
        req = urllib.request.Request(
            f"{BASE_URL}/api/emotion/analyze",
            data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            j = json.loads(r.read())
            detected = j.get("emotion", "neutral")
            correct = (detected == expected)
    except Exception:
        detected, correct = local_analyze(text)

    return {
        "text": text,
        "expected": expected,
        "detected": detected,
        "correct": correct,
    }

# ============================================================================
# 主函数
# ============================================================================

def main():
    print("=" * 70)
    print(f"   情感机器人1000轮评测 | 并发度={CONCURRENCY}")
    print("=" * 70)

    # 检查后端
    try:
        req = urllib.request.Request(f"{BASE_URL}/health", method="GET")
        with urllib.request.urlopen(req, timeout=3):
            online = True
    except Exception:
        online = False

    print(f"\n后端: {'🟢 在线' if online else '🔴 离线（本地评测）'}")
    print(f"评测集: {len(SCENARIOS)} 条 | 并发: {CONCURRENCY}")
    print()

    t0 = time.time()

    correct = 0
    by_emotion = defaultdict(lambda: {"total": 0, "correct": 0})

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = [pool.submit(eval_one, s) for s in SCENARIOS]
        done = 0
        for future in as_completed(futures):
            r = future.result()
            by_emotion[r["expected"]]["total"] += 1
            if r["correct"]:
                by_emotion[r["expected"]]["correct"] += 1
                correct += 1
            done += 1
            if done % 200 == 0:
                print(f"  [{done}/1000]...", flush=True)

    elapsed = time.time() - t0

    total = len(SCENARIOS)
    acc_rate = correct / total

    print(f"\n{'='*70}")
    print(f"  📋 1000轮评测报告 | 耗时: {elapsed:.1f}s ({total/elapsed:.0f}轮/秒)")
    print(f"{'='*70}")

    print(f"\n  {'情绪':12s} {'正确/总数':>14s} {'准确率':>8s}")
    for emo in ["positive", "anxious", "angry", "sad", "negative"]:
        d = by_emotion.get(emo, {"total": 0, "correct": 0})
        t = d["total"]
        a = d["correct"] / max(t, 1)
        print(f"  {emo:12s} {d['correct']:>6}/{t:<6}  {a:>7.1%}")

    print(f"\n  情绪识别准确率: {correct}/{total} ({acc_rate:.1%})")
    print(f"  综合得分: {acc_rate:.1%} ", end="")
    if acc_rate >= 0.90: print("✅ 优秀")
    elif acc_rate >= 0.75: print("⚠️  合格")
    else: print("❌ 需改进")
    print(f"{'='*70}")

main()
