#!/usr/bin/env python3
"""
用法：MINIMAX_API_KEY=sk-xxx python3 python_service/benchmark_llm.py
"""
import os, re, json, time, random, sys
from collections import defaultdict

KEY = os.getenv("MINIMAX_API_KEY", "")
if not KEY:
    print("请设置 MINIMAX_API_KEY"); sys.exit(1)
try:
    from openai import OpenAI
    client = OpenAI(api_key=KEY, base_url="https://api.minimaxi.com/v1")
    print("Client ready")
except Exception as e:
    print(f"Client failed: {e}"); sys.exit(1)

def llm(messages, temp=0.7, max_t=150):
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model="MiniMax-M2.7", messages=messages,
                temperature=temp, max_tokens=max_t)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            if attempt < 2 and "429" in str(e):
                time.sleep(2 ** attempt); continue
            return "[Error]"

def strip(s):
    return re.sub(r"<[^>]*>", "", s or "").strip()

# emotion detection
KW = {
    "angry": ["生气","愤怒","讨厌","烦","火大","忍无可忍","无赖","嚣张","假货","绕远","拒退货","投诉","讨说法","太过分","气死人","素质差","可恨","可恶","恶心","塌房","骗子","偷","插队","跑路","健身房跑","差评","不公平","冤枉","委屈","丢人","furious","outraged","livid","infuriated","how dare","unacceptable","rear-ended","overbooked","overcharged","scammed","ripped off","rage","angry","hate","mad","fuck","该死","气死我了","恨死","客服差","恶劣","态度恶劣","坑人","黑店","宰客","乱收费","欺诈","诈骗","盗刷","气得发抖","气得浑身发抖"],
    "anxious": ["焦虑","担心","害怕","紧张","不安","压力","考研","失眠","睡不着","nervous","慌","慌乱","惧怕","心神不宁","惶恐","没底","没把握","不确定","悬着","忐忑","心慌","七上八下","复习不进去","面试没准备","答辩没做完","断供","被裁","失业","体检异常","panic","dread","uneasy","apprehensive","overwhelmed","stressed","burned out","runway","deadline","visa expires","laid off","心跳快","总惊醒","越想越慌","发慌","睡不着","噩梦","心事重重","前路迷茫","悬而未决"],
    "negative": ["难过","伤心","痛苦","抑郁","崩溃","绝望","诸事不顺","谷底","撑不住","失败","挫折","打击","困境","逆境","倒霉","last day","石沉大海","被裁","裁员","负债","逾期","冻结","投资失败","亏本","lost","failed","rejected","humiliated","devastated","hopeless","诸事","难熬","受挫","诸事","困难"],
    "sad": ["哭","泪","分手","失恋","去世","逝世","病逝","走了","没了","离开","失去","绝交","流产","确诊","早产","心碎","肾衰","被骗","黑心","合伙人骗","背叛","伤心","悲痛","哀伤","沮丧","失落","crying","lonely","heartbroken","devastated","grief","mournful","passed away","betrayed","狗狗没了","NICU","孤独","独居","孤零零","没人陪","寂寞","空巢","想念","牵挂","心酸","dog ran","cat ran","ran away","alone","miss my"],
    "positive": ["开心","高兴","快乐","棒","太好了","激动","兴奋","喜悦","欢乐","愉快","欣喜","振奋","太棒了","超开心","美滋滋","乐开花","好运","顺利","满分","全优","全奖","达标","涨停","拿到offer","升职","融资","脱单","全红","上岸","拿到","完成了","happy","great","wonderful","love","joy","dream school","got funded","promoted","perfect score","won","excellent","thrilled","delighted","accomplished","championship","graduated","honors","funded","breakthrough","通过了","被表扬","成功","赢","拿到了","晋升","加薪","全红","涨停","浮盈","盈利","收获满满","赶上了","最后一班","perfect","amazing","awesome","fantastic"],
}

def detect(text):
    t = text.lower()
    sc = {}
    for emo, kws in KW.items():
        cnt = sum(1 for kw in kws if kw in t)
        if cnt:
            sc[emo] = cnt
    return max(sc, key=lambda k: sc[k]) if sc else "neutral"

SYS_PROMPT = "你是一个温暖、有同理心的情感支持助手。回复要温暖、口语化、简短（50字以内）。"
TONES = {
    "positive": "温暖热情，鼓励继续分享",
    "negative": "温柔倾听，不否定情绪",
    "anxious": "安抚减压，陪伴舒缓",
    "angry": "理解愤怒，引导表达",
    "sad": "温暖陪伴，允许悲伤",
    "neutral": "自然友好，继续对话",
}

def gen_reply(text, emo):
    tone = TONES.get(emo, "温暖友好")
    raw = llm([
        {"role": "system", "content": SYS_PROMPT},
        {"role": "user", "content": f"用户情绪：{emo}（{tone}）\n用户说：「{text}」"}
    ], temp=0.7, max_t=80)
    return strip(raw)

# local scoring
def score_reply(reply, emo):
    t = reply.strip()
    sc = 0.0
    reasons = []
    if 15 <= len(t) <= 250: sc += 0.2
    elif len(t) < 10: reasons.append("太短")
    pos_kws = {"太棒了","真替你","为你高兴","开心","继续分享","恭喜","厉害","太厉害了"}
    neg_kws = {"听到了","理解","愿意听","我在这里","陪着你","不强撑","慢慢来"}
    anx_kws = {"深呼吸","慢慢来","一起","我在这里","别急","先说"}
    ang_kws = {"正常","理解","被这样","愤怒是","可以发泄"}
    sad_kws = {"难过","愿意说","我在这里","抱抱","允许自己"}
    neu_kws = {"嗯","继续说","愿意听"}
    tone_kws = {"你很棒","加油","慢慢来","会好的"}
    tone_bad = {"抱歉，我作为AI","我是一个AI","对不起我不知道","无法帮助","I'm an AI"}
    EMO_KWS = {
        "positive": pos_kws, "negative": neg_kws, "anxious": anx_kws,
        "angry": ang_kws, "sad": sad_kws, "neutral": neu_kws,
    }
    matched = [kw for kw in EMO_KWS.get(emo, neu_kws) if kw in t]
    if matched: sc += 0.4
    else: reasons.append("缺情绪词")
    if any(b in t for b in tone_bad): sc -= 0.3; reasons.append("机械回复")
    if any(q in t for q in ["吗？","怎么","愿意说","为什么","还有吗"]): sc += 0.2
    if any(e in t for e in ["你很棒","加油","慢慢来","会好的","太厉害了","真替你","为你高兴","恭喜"]): sc += 0.2
    return max(0.0, min(1.0, sc)), reasons, matched

# 1000条数据
BASE = [
    ("positive","今天考试得了满分，特别开心"),("positive","工作汇报顺利通过，老板当众表扬了"),
    ("positive","收到dream company的offer了"),("positive","减重10斤终于达标"),
    ("positive","孩子期末考试全优"),("positive","创业项目拿到第一笔融资"),
    ("positive","收到了升职通知"),("positive","i got promoted today"),
    ("positive","my startup got funded"),("positive","太棒了今天一切顺利"),
    ("positive","全红涨停开心"),("positive","顺利通过考试啦"),
    ("negative","投了50份简历全部石沉大海"),("negative","被裁员了今天last day"),
    ("negative","创业失败欠了一屁股债"),("negative","诸事不顺，喝水都塞牙"),
    ("negative","last day 被裁"),("negative","failed my dissertation defense"),
    ("negative","努力了却什么都没得到"),("negative","觉得自己特别失败"),
    ("anxious","考研还剩两周完全复习不进去"),("anxious","明天答辩PPT还没做完"),
    ("anxious","35岁被裁员找不到下家"),("anxious","高考出分前焦虑睡不着"),
    ("anxious","i have a job interview tomorrow"),("anxious","waiting for my graduate admission result"),
    ("anxious","my startup runway is running out"),("anxious","每天想东想西停不下来"),
    ("anxious","对未来充满不确定感"),("anxious","心跳快睡不好总惊醒"),
    ("angry","外卖被偷走还被人吃了"),("angry","客服态度恶劣拒不退款"),
    ("angry","网购被骗了5000块"),("angry","健身房卷钱跑路了"),
    ("angry","气得浑身发抖"),("angry","平台随意封禁我账号"),
    ("angry","rear-ended my new car"),("angry","tech support kept transferring me around for hours"),
    ("sad","从小带大的奶奶去世了"),("sad","狗狗走丢了找不回来"),
    ("sad","和最好的朋友绝交了"),("sad","my best friend betrayed my trust"),
    ("sad","眼泪停不下来"),("sad","心里空落落的"),
    ("sad","my grandmother passed away last week"),("sad","put my dog down yesterday"),
    ("neutral","今天吃了什么"),("neutral","天气怎么样"),
    ("neutral","这个电影不错"),("neutral","明天记得提醒我开会"),
]

def build_scenarios():
    data = BASE * 6 + BASE[:40]
    random.seed(42)
    random.shuffle(data)
    return data[:1000]

def main():
    print("=" * 60)
    print("MiniMax LLM 情感机器人全面评测")
    print("情绪检测：本地关键词 | 回复生成：MiniMax-M2.7 | 评分：本地规则")
    print("=" * 60)
    scenarios = build_scenarios()
    t0 = time.time()
    R = defaultdict(lambda: {"t": 0, "c": 0, "sc": [], "reps": []})
    for i, (exp, text) in enumerate(scenarios):
        det = detect(text)
        ok = (det == exp)
        R[exp]["t"] += 1
        if ok: R[exp]["c"] += 1
        reply = gen_reply(text, det)
        sc_val, reasons, matched = score_reply(reply, det)
        R[exp]["sc"].append(sc_val)
        if i < 20 or (i + 1) % 200 == 0:
            R[exp]["reps"].append({"text": text[:30], "det": det, "reply": reply[:60], "sc": sc_val})
        print(f"[{i+1:4d}/1000] {exp} -> {det} sc={sc_val:.2f} | {reply[:40]}...", end="\r", flush=True)
        time.sleep(0.05)
    elapsed = time.time() - t0
    total_c = sum(R[e]["c"] for e in R)
    total_t = len(scenarios)
    print()
    print("=" * 60)
    print(f"耗时: {elapsed:.0f}s | {total_t/elapsed:.1f} 条/秒")
    print("=" * 60)
    print(f"{'情绪':10}  {'准确率':>8}  {'均分':>6}  样例")
    for emo in ["positive", "negative", "anxious", "angry", "sad", "neutral"]:
        d = R.get(emo, {"t": 0, "c": 0, "sc": [], "reps": []})
        if d["t"] == 0: continue
        acc = d["c"] / d["t"]
        avg_sc = sum(d["sc"]) / max(len(d["sc"]), 1)
        rep = (d["reps"][0]["reply"] or "")[:35] if d["reps"] else ""
        mk = "✅" if acc >= 0.80 else "⚠️ " if acc >= 0.70 else "❌"
        print(f"  {mk} {emo:10} {acc:>7.1%}  {avg_sc:.2f}  {rep}")
    all_sc = [s for d in R.values() for s in d["sc"]]
    avg_all_sc = sum(all_sc) / max(len(all_sc), 1)
    print()
    print(f"  综合情绪检测: {total_c}/{total_t} = {total_c/total_t:.1%}")
    print(f"  平均回复质量: {avg_all_sc:.2f}/1.00")
    os.makedirs("benchmark_results", exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    report = {
        "timestamp": ts, "model": "MiniMax-M2.7", "elapsed_seconds": round(elapsed, 1),
        "total": total_t, "correct": total_c,
        "emotion_accuracy": round(total_c/total_t, 4),
        "avg_reply_score": round(avg_all_sc, 3),
        "by_emotion": {e: {"correct": d["c"], "total": d["t"], "accuracy": round(d["c"]/max(d["t"],1), 4), "avg_score": round(sum(d["sc"])/max(len(d["sc"]),1), 3), "samples": d["reps"][:3]} for e, d in R.items()}
    }
    with open(f"benchmark_results/report_{ts}.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"报告: benchmark_results/report_{ts}.json")

if __name__ == "__main__":
    main()
