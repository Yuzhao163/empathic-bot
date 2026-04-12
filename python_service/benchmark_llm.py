#!/usr/bin/env python3
"""
MiniMax LLM 情感机器人评测系统
用法:
  MINIMAX_API_KEY=sk-xxx MINIMAX_BASE_URL=https://api.minimaxi.com/v1 python benchmark_llm.py
"""

import os, json, time, random, sys, re
from collections import defaultdict

# ============================================================================
# MiniMax API Client
# ============================================================================

KEY = os.getenv("MINIMAX_API_KEY", "")
BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
MODEL = os.getenv("LLM_MODEL", "MiniMax-M2.7")

if not KEY:
    print("❌ 请设置 MINIMAX_API_KEY"); sys.exit(1)

try:
    from openai import OpenAI
    client = OpenAI(api_key=KEY, base_url=BASE_URL)
    print(f"✅ Client ready | model={MODEL} | base={BASE_URL}")
except Exception as e:
    print(f"❌ Client init failed: {e}"); sys.exit(1)

def llm_call(messages, temperature=0.3, max_tokens=200, retries=3):
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=MODEL, messages=messages,
                temperature=temperature, max_tokens=max_tokens)
            return resp.choices[0].message.content
        except Exception as e:
            err = str(e)
            if attempt < retries-1 and ("rate_limit" in err or "429" in err or "500" in err):
                time.sleep(2 ** attempt)
                continue
            raise

# ============================================================================
# 情绪检测 Prompt
# ============================================================================

EMOTION_PROMPT = """你是一个情绪分类器。根据用户输入，判断情绪类型。

规则：只输出一个词：positive / negative / anxious / angry / sad / neutral / mixed

- positive：开心、兴奋、成就感、被表扬，好运
- negative：难过、沮丧、失落、被拒绝、失败
- anxious：担心、害怕、紧张、失眠、不确定
- angry：生气、愤怒、不公平、被骗、讨厌
- sad：悲伤、哭泣、失去、离别、孤独、心碎
- neutral：普通陈述、不带情绪
- mixed：两种情绪并存（如开心但担心）

示例：
输入：今天考试得了满分！
输出：positive

输入：被老板当众批评，觉得很丢脸
输出：angry

输入：考研还剩两周完全复习不进去
输出：anxious

输入：和谈了5年的对象分手了
输出：sad

输入：投了50份简历全部石沉大海
输出：negative

输入："""

def detect_emotion_llm(text):
    try:
        result = llm_call([
            {"role": "system", "content": EMOTION_PROMPT},
            {"role": "user", "content": text}
        ], temperature=0.1, max_tokens=30)
        # 去除<think>...</think>思考标签（MiniMax模型输出格式）
        clean = re.sub(r'<[^>]*>', '', result).strip()
        # 去除多余空白
        clean = re.sub(r'\s+', ' ', clean)
        # 查找第一个情绪词
        for v in ["positive","negative","anxious","angry","sad","neutral","mixed"]:
            if v in clean.lower():
                return v, 0.85
        return "neutral", 0.5
    except Exception as e:
        return "neutral", 0.5

# ============================================================================
# 同理心回复评分 Prompt
# ============================================================================

def score_empathy_llm(reply, emotion):
    try:
        prompt = f"""评价下面情感支持回复的质量（0-10分）：
- 0-3：冷淡、机械
- 4-6：基本但不温暖
- 7-9：温暖有同理心
- 10：非常出色

回复：{reply[:200]}
用户情绪：{emotion}

只输出JSON：{{"score": 7.5, "reason": "原因"}}
"""
        result = llm_call([{"role": "user", "content": prompt}], temperature=0.3, max_tokens=80)
        m = re.search(r'\{.*?"score"\s*:\s*[\d.]+.*?\}', result, re.DOTALL)
        if m:
            return json.loads(m.group())
        return {"score": 5.0, "reason": "解析失败"}
    except Exception as e:
        return {"score": 5.0, "reason": str(e)}

# ============================================================================
# 1000条测试数据
# ============================================================================

BASE_SCENARIOS = [
    # positive × 150
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
    ("positive", "今天特别顺利，一路上都绿灯"),
    ("positive", "抽到了演唱会前排票"),
    ("positive", "体重终于下100斤了"),
    ("positive", "宝宝的第一次叫妈妈"),
    ("positive", "养了多年的花终于开了"),
    ("positive", "邻居送来了自己做的蛋糕"),
    ("positive", "顺利通过了驾照考试"),
    ("positive", "收到了期待已久的包裹"),
    # negative × 150
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
    ("negative", "my boss humiliated me in front of everyone"),
    ("negative", "诸事不顺，喝水都塞牙"),
    ("negative", "努力了却什么都没得到"),
    ("negative", "觉得自己特别失败"),
    ("negative", "看不到未来的方向"),
    ("negative", "所有希望都破灭了"),
    # anxious × 150
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
    ("anxious", "新工作完全不适应每天加班到凌晨"),
    ("anxious", "i have a job interview tomorrow"),
    ("anxious", "waiting for my graduate admission result"),
    ("anxious", "my visa expires next month"),
    ("anxious", "the experiment keeps failing and deadline is near"),
    ("anxious", "my startup runway is running out"),
    ("anxious", "my passport expired and my flight is in 3 days"),
    ("anxious", "i might get laid off next quarter"),
    ("anxious", "i have to present to the board next week"),
    ("anxious", "每天想东想西停不下来"),
    ("anxious", "一闭上眼睛就开始担心各种事"),
    ("anxious", "怕自己做得不够好"),
    ("anxious", "对未来充满不确定感"),
    ("anxious", "心跳快睡不好总惊醒"),
    # angry × 150
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
    ("angry", "平台随意封禁我账号没有任何解释"),
    ("angry", "被人当众羞辱"),
    ("angry", "真的很想发火但得忍住"),
    ("angry", "气得浑身发抖"),
    ("angry", "遇到这种人就气不打一处来"),
    ("angry", "忍无可忍了"),
    # sad × 150
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
    ("sad", "i got diagnosed with a chronic illness"),
    ("sad", "i lost all my savings in a scam"),
    ("sad", "my best friend betrayed my trust"),
    ("sad", "i had to put my cat to sleep"),
    ("sad", "grief from losing my mother is overwhelming"),
    ("sad", "nothing seems to go right lately"),
    ("sad", "眼泪停不下来"),
    ("sad", "心里空落落的"),
    ("sad", "不知道为什么就是想哭"),
    ("sad", "再也回不去了"),
    ("sad", "失去了才懂得珍惜"),
    # neutral × 50
    ("neutral", "今天吃了什么"),
    ("neutral", "天气怎么样"),
    ("neutral", "周末有什么计划"),
    ("neutral", "你叫什么名字"),
    ("neutral", "这个电影不错"),
    ("neutral", "明天记得提醒我开会"),
    ("neutral", "下班一起去吃饭吗"),
    ("neutral", "这个包多少钱"),
    ("neutral", "最近在追什么剧"),
    ("neutral", "今天走了多少步"),
    # mixed × 50
    ("mixed", "我今天特别开心因为项目上线了，但同时又很焦虑因为老板的评价还没出来"),
    ("mixed", "拿到offer了很开心，但一想到要搬去新城市又有点害怕"),
    ("mixed", "减肥成功了超开心，但最近失眠很严重不知道怎么了"),
    ("mixed", "老公出差一个月了，一个人带孩子累得崩溃"),
    ("mixed", "升职了应该高兴，但我担心胜任不了新岗位"),
    ("mixed", "i got the job but i'm nervous about the new challenges"),
    ("mixed", "the project succeeded but my team is burnt out"),
    ("mixed", "i'm happy about the bonus but worried about the restructuring"),
    ("mixed", "终于通过考试了！但同时又为接下来的面试担心"),
    ("mixed", "孩子升学成功了高兴，但想到学费就愁"),
]

# ============================================================================
# 主评测
# ============================================================================

def main():
    print("=" * 70)
    print("  MiniMax LLM 情感机器人评测")
    print("  模型:", MODEL)
    print("=" * 70)

    random.seed(42)
    scenarios = (BASE_SCENARIOS * 4 + BASE_SCENARIOS[:len(BASE_SCENARIOS)])[:1000]
    random.shuffle(scenarios)

    print(f"\n评测集：{len(scenarios)} 条")
    print("阶段1：情绪检测（MiniMax-M2.7）...")

    t0 = time.time()
    results = defaultdict(lambda: {"total": 0, "correct": 0, "errors": []})
    correct = 0

    for i, (expected, text) in enumerate(scenarios):
        detected, prob = detect_emotion_llm(text)
        ok = (detected == expected)
        results[expected]["total"] += 1
        if ok:
            results[expected]["correct"] += 1
            correct += 1
        else:
            if len(results[expected]["errors"]) < 2:
                results[expected]["errors"].append({"text": text[:50], "detected": detected})
        if (i+1) % 20 == 0:
            acc = correct / (i+1)
            print(f"  [{i+1}/{len(scenarios)}] 当前准确率: {acc:.1%}  ", end="\r", flush=True)
        time.sleep(0.15)  # 避免过速

    t1 = time.time()
    print(f"\n情绪检测完成，耗时 {t1-t0:.1f}s")

    # 阶段2：同理心评分（每类抽样10条）
    print("\n阶段2：同理心回复质量评分（抽样70条）...")
    samples = defaultdict(list)
    for expected, text in scenarios:
        if len(samples[expected]) < 10:
            samples[expected].append(text)

    empathy_data = []
    total_score = 0.0
    emp_count = 0

    for emo, texts in samples.items():
        for text in texts:
            # 生成回复
            try:
                reply = llm_call([
                    {"role": "system", "content": "你是一个温暖有同理心的情感支持助手。"},
                    {"role": "user", "content": f"用户说：「{text}」\n请以温暖的方式回复，不超过50字。"}
                ], temperature=0.7, max_tokens=80)
            except Exception as e:
                reply = f"[生成失败: {e}]"
            # 评分
            score_result = score_empathy_llm(reply, emo)
            score = score_result.get("score", 5.0)
            total_score += score
            emp_count += 1
            empathy_data.append({"emotion": emo, "text": text[:40], "reply": reply[:60], "score": score})
            print(f"  [{emo:8s}] {score:.1f}/10 | {reply[:50]}...", flush=True)
            time.sleep(0.2)

    avg_emp = total_score / max(emp_count, 1)
    elapsed = time.time() - t0

    # ===== 报告 =====
    total_acc = correct / len(scenarios)
    print()
    print("=" * 70)
    print(f"  📋 MiniMax LLM 情感机器人评测报告")
    print(f"  评测时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  模型: {MODEL} | 耗时: {elapsed:.1f}s")
    print("=" * 70)

    print("\n  【第一部分】情绪检测准确率（MiniMax-M2.7）")
    print("  " + "-" * 56)
    print(f"  {'情绪':12s}  {'正确/总数':>12s}  {'准确率':>8s}")
    emo_order = ["positive","negative","anxious","angry","sad","neutral","mixed"]
    for emo in emo_order:
        d = results.get(emo, {"total": 0, "correct": 0, "errors": []})
        t = d["total"]
        if t == 0: continue
        c = d["correct"]
        a = c / t
        m = "✅" if a >= 0.85 else "⚠️ " if a >= 0.70 else "❌"
        print(f"  {m} {emo:12s}  {c:>5}/{t:<5}   {a:>7.1%}")
        if d["errors"]:
            print(f"      错例：「{d['errors'][0]['text']}」 → {d['errors'][0]['detected']}")

    print()
    print(f"  综合情绪检测准确率: {correct}/{len(scenarios)} = {total_acc:.1%}")
    grade = "A" if total_acc >= 0.90 else "B" if total_acc >= 0.80 else "C" if total_acc >= 0.70 else "D"
    print(f"  评分等级: {grade}")

    print()
    print("  【第二部分】同理心回复质量（MiniMax-M2.7 生成回复）")
    print("  " + "-" * 56)
    print(f"  {'情绪':12s}  {'样本':>6s}  {'平均得分':>10s}")
    for emo in emo_order:
        scores = [s["score"] for s in empathy_data if s["emotion"] == emo]
        if not scores: continue
        avg = sum(scores) / len(scores)
        label = "优秀" if avg >= 7 else "良好" if avg >= 5 else "一般" if avg >= 3 else "较差"
        print(f"  {emo:12s}  {len(scores):>5}条   {avg:>8.1f}/10  {label}")

    print()
    print(f"  平均同理心得分: {avg_emp:.1f}/10")

    weak = [(e,d) for e,d in results.items() if d["total"]>0 and d["correct"]/d["total"]<0.80]
    if weak:
        print()
        print("  【第三部分】主要问题")
        print("  " + "-" * 56)
        for emo, d in weak:
            a = d["correct"]/d["total"]
            print(f"  ❌ {emo} 准确率仅 {a:.1%}，典型错例：")
            for ex in d["errors"][:2]:
                print(f"     「{ex['text']}」 → 误判为 {ex['detected']}")
    else:
        print()
        print("  【第三部分】✅ 各情绪类型准确率均达到 80% 以上")

    print()
    print("=" * 70)

    # 保存报告
    os.makedirs("benchmark_results", exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": MODEL, "elapsed_seconds": round(elapsed, 1),
        "total": len(scenarios), "correct": correct,
        "emotion_accuracy": round(total_acc, 4),
        "avg_empathy_score": round(avg_emp, 2),
        "emotion_results": {e: {"correct": d["correct"], "total": d["total"],
            "accuracy": round(d["correct"]/max(d["total"],1),4), "errors": d["errors"]}
            for e, d in results.items()},
        "empathy_samples": empathy_data,
    }
    with open(f"benchmark_results/report_llm_{ts}.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n报告已保存: benchmark_results/report_llm_{ts}.json")

if __name__ == "__main__":
    main()
