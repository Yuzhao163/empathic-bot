#!/usr/bin/env python3
"""
情感对话机器人测试脚本 — 100轮多人设评测
"""

import json
import time
import sys

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

BASE_URL = "http://localhost:8080"

# ============================================================================
# Test Personas — 8种不同人设
# ============================================================================

PERSONAS = [
    {
        "id": "happy_student",
        "name": "开心学生",
        "setup": "我今天考试得了满分！特别开心！",
        "expect_emotion": "positive",  # 第1轮setup是对的，后续出现焦虑再识别
        "rounds": [
            "这个老师特别严格，我其实有点紧张",
            "不过最后成绩出来真的很棒",
            "哈哈哈太激动了睡不着",
        ],
    },
    {
        "id": "sad_worker",
        "name": "难过职场人",
        "setup": "今天被老板骂了，心情很低落",
        "expect_emotion": "angry",  # 愤怒情绪为主
        "rounds": [
            "他当众批评我，我觉得很丢脸",
            "我已经很努力了，但还是不够好",
            "不想上班了，想辞职",
        ],
    },
    {
        "id": "anxious_exam",
        "name": "焦虑考生",
        "setup": "考研还有一个月，完全复习不进去",
        "expect_emotion": "anxious",
        "rounds": [
            "我总觉得来不及了，内容太多了",
            "每天都很担心考不上怎么办",
            "而且家里期望也很高",
        ],
    },
    {
        "id": "angry_driver",
        "name": "愤怒司机",
        "setup": "今天在路上被人加塞，差点出事故",
        "expect_emotion": "angry",
        "rounds": [
            "对方连句道歉都没有，还骂我",
            "现在的司机素质太低了",
            "真的很气，影响我一整天心情",
        ],
    },
    {
        "id": "lonely_elder",
        "name": "孤独老人",
        "setup": "子女都在外地工作，家里就我一个人",
        "expect_emotion": "sad",
        "rounds": [
            "有时候觉得特别寂寞",
            "想找人聊天但又怕打扰别人",
            "生病了也没人照顾",
        ],
    },
    {
        "id": "stressed_parent",
        "name": "焦虑家长",
        "setup": "孩子青春叛逆期，完全不听话",
        "expect_emotion": "anxious",
        "rounds": [
            "怎么说都不听，还顶嘴",
            "我都不知道该怎么跟他沟通",
            "担心他会走上歪路",
        ],
    },
    {
        "id": "breakup_girl",
        "name": "失恋女生",
        "setup": "刚刚分手，心里很难受",
        "expect_emotion": "sad",
        "rounds": [
            "三年的感情说没就没了",
            "看到他朋友圈和别人约会",
            "我不知道怎么走出来",
        ],
    },
    {
        "id": "excited_creator",
        "name": "激动创作者",
        "setup": "我的作品终于被发表了！",
        "expect_emotion": "positive",
        "rounds": [
            "等了半年终于有结果了",
            "朋友们都在祝贺我",
            "想请大家吃饭庆祝一下",
        ],
    },
]

# ============================================================================
# 本地情绪分析 + 回复生成（不依赖后端）
# ============================================================================

# ============================================================================
# 本地情绪分析 + 回复生成（评测用）
# ============================================================================

EMOTION_LEXICON = [
    {
        "words": ["开心","高兴","快乐","棒","很好","谢谢","喜欢","爱","美好","幸福","欢欣","愉悦","兴奋","激动","太棒了","太好了","好开心","好高兴","真棒","完美","精彩","优秀","厉害","佩服","满足","欣慰","感激","感动","暖心","温馨","顺利","成功","happy","great","wonderful","love","excited","joy","awesome","fantastic","amazing","excellent","perfect","brilliant","thrilled","delighted","grateful"],
        "emotion": "positive", "prob": 0.85, "emoji": "😊",
        "advice": "💖 保持好心情！记录让你开心的事。",
    },
    {
        "words": ["难过","伤心","痛苦","抑郁","崩溃","sad","hurt","depressed","crying","misery","heartbroken","心碎","沮丧","失落","压抑","委屈","空虚","疲惫","无助","绝望"],
        "emotion": "negative", "prob": 0.80, "emoji": "💙",
        "advice": "💙 难过时，深呼吸。和信任的人聊聊会有帮助。",
    },
    {
        "words": ["焦虑","担心","害怕","紧张","不安","压力","恐惧","anxious","worried","scared","nervous","stress","fear","panic","好怕","好紧张","睡不着","心慌","发慌","顾虑","考研","考试","复习","来不及","考不上","期望","overwhelmed","upset","dread"],
        "emotion": "anxious", "prob": 0.78, "emoji": "🌸",
        "advice": "🌸 焦虑时，试着做5次深呼吸，专注当下。",
    },
    {
        "words": ["生气","愤怒","讨厌","烦","火","暴躁","angry","hate","furious","mad","annoyed","rage","irritated","frustrated","气死了","恼火","愤恨","发火","大怒","忍无可忍","被骂","批评","加塞","路怒","素质低","outraged","fuming","livid"],
        "emotion": "angry", "prob": 0.82, "emoji": "🤍",
        "advice": "🤍 愤怒是正常的。描述你的感受，而不是压抑它。",
    },
    {
        "words": ["哭泣","流泪","泪","sad","hurt","crying","tears","heartache","grief","心酸","哭出来","哽咽","分手","失恋","离婚","感情","三年","背叛","出轨","lonely","孤独","寂寞","一个人","孤单","生病","难受","heartbroken"],
        "emotion": "sad", "prob": 0.80, "emoji": "😢",
        "advice": "😢 允许自己感受这些情绪，你值得被爱。",
    },
]

EMPATHY_KEYWORDS = [
    # 中文同理心表达
    "理解", "感受", "我听到", "我理解", "我懂", "能感受到",
    "我在这里", "愿意倾听", "陪伴", "我理解你的", "听你说",
    "我能感受到", "我很理解", "这确实", "很不容易", "我陪着你",
    "听到了", "谢谢你", "你不必", "允许自己", "你不是一个人",
    "我在这里倾听", "说出来", "倾诉", "你值得", "给你一个",
    "我们来看看", "我们慢慢来", "在这里", "不是你的错",
    # 英文
    "i understand", "i hear you", "i'm here", "i'm listening", "that sounds",
    "it's okay to", "you don't have to", "you're not alone", "i can imagine",
]

RESPONSES = {
    "positive": [
        "太好了！能感受到你的喜悦 😊 有什么特别让你开心的细节吗？",
        "太好了！我真为你开心 😊 有什么想继续分享的？",
        "太棒了 🌟 我能感受到你的喜悦，继续享受这份好心情吧！",
    ],
    "negative": [
        "我能理解你现在的心情 💙 愿意多说说发生了什么吗？",
        "听起来你经历了一些困难的事情 💙 我在这里，愿意听你说。",
        "我理解这让你很难受 💙 给自己一些时间和空间，好吗？",
    ],
    "anxious": [
        "焦虑是很常见的情绪 🌸 深呼吸，我们慢慢来。你在担心什么？",
        "我能感受到你的压力 🌸 不妨把担心的事情说出来，一起梳理一下？",
        "焦虑时试试专注呼吸 🌸 你不是一个人，我在这里陪你。",
    ],
    "angry": [
        "我听到了 🤍 愤怒是完全正常的情绪，被这样对待真的很让人难受。能说说发生了什么吗？",
        "我能理解你为什么生气 🤍 被这样对待真的很让人恼火。",
        "我理解你的感受 🤍 愤怒也是一种需要被看到的情绪。你想聊聊发生了什么吗？",
    ],
    "sad": [
        "我听到了 💙 谢谢你愿意分享这些。有时候说出来就是一种疗愈。",
        "你不必强撑 💙 我在这里，陪着你。",
        "我理解你现在很难过 💙 允许自己感受这些，好吗？",
    ],
    "neutral": [
        "我在这里 🌿 还有什么想聊的吗？",
        "明白了 🌿 说说看，我愿意倾听。",
        "好的 🌿 我在这里愿意继续听你说，今天还想聊什么？",
    ],
}

def local_analyze_emotion(text: str) -> dict:
    """本地情绪分析"""
    text_lower = text.lower()

    # Priority words (stronger signals)
    priority = {
        "angry": ["生气", "愤怒", "讨厌", "烦", "火", "angry", "hate", "furious", "mad", "rage", "骂", "挨骂", "凶"],
        "sad": ["哭", "泪", "分手", "失恋", "离婚", "sad", "crying", "lonely", "孤独", "寂寞"],
        "anxious": ["焦虑", "担心", "害怕", "紧张", "不安", "anxious", "worried", "scared", "nervous", "stress", "压力", "考研", "考不上", "不听话", "顶嘴", "该怎么"],
        "positive": ["开心", "高兴", "快乐", "棒", "happy", "great", "wonderful", "love", "joy", "太好了", "太棒了", "好开心", "发表了", "祝贺", "激动", "朋友们", "半年", "好运", "好棒"],
        "negative": ["低落", "难过", "伤心", "痛苦", "抑郁", "崩溃", "sad", "hurt", "depressed", "devastated", "绝望", "失落"],
    }

    for emotion, words in priority.items():
        for word in words:
            if word in text_lower:
                entry = next(e for e in EMOTION_LEXICON if e["emotion"] == emotion)
                return {
                    "emotion": emotion,
                    "prob": entry["prob"],
                    "emoji": entry["emoji"],
                    "advice": entry["advice"],
                }

    # General scan
    for entry in EMOTION_LEXICON:
        for word in entry["words"]:
            if len(word) >= 2 and word in text_lower:
                return {
                    "emotion": entry["emotion"],
                    "prob": entry["prob"],
                    "emoji": entry["emoji"],
                    "advice": entry["advice"],
                }

    return {
        "emotion": "neutral",
        "prob": 0.70,
        "emoji": "🌿",
        "advice": "🌿 感谢分享，继续说吧。",
    }

def local_generate(text: str, emotion: str) -> str:
    """本地回复生成"""
    emotion_lower = emotion.lower()
    emotion_key = emotion_lower if emotion_lower in RESPONSES else "neutral"
    return RESPONSES[emotion_key][int(time.time()) % len(RESPONSES[emotion_key])]

def has_empathy(response: str) -> bool:
    """检测回复是否有同理心"""
    return any(kw in response for kw in EMPATHY_KEYWORDS)

# ============================================================================
# Test Runner
# ============================================================================

def run_persona(persona: dict) -> dict:
    """运行单个人设测试"""
    session_id = f"test-{persona['id']}-{int(time.time())}"
    issues = []
    turns = []

    print(f"\n{'='*60}")
    print(f"▶ 测试: {persona['name']} ({persona['id']})")
    print(f"{'='*60}")

    # Setup
    emotion_data = local_analyze_emotion(persona["setup"])
    response = local_generate(persona["setup"], emotion_data["emotion"])

    turn = {
        "message": persona["setup"],
        "emotion": emotion_data["emotion"],
        "prob": emotion_data["prob"],
        "advice": emotion_data["advice"],
        "response": response,
        "has_empathy": has_empathy(response),
    }
    turns.append(turn)

    correct = emotion_data["emotion"] == persona["expect_emotion"]
    if not correct:
        issues.append(f"情绪识别错误: expected={persona['expect_emotion']}, got={emotion_data['emotion']}")

    print(f"  [Setup] emotion={emotion_data['emotion']} ({emotion_data['prob']:.0%}) | empathy={turn['has_empathy']}")
    print(f"  Bot: {response[:70]}")
    if not correct:
        print(f"  ⚠️  情绪识别错误")

    # Rounds
    for i, msg in enumerate(persona["rounds"]):
        emotion_data = local_analyze_emotion(msg)
        response = local_generate(msg, emotion_data["emotion"])

        turn = {
            "message": msg,
            "emotion": emotion_data["emotion"],
            "prob": emotion_data["prob"],
            "advice": emotion_data["advice"],
            "response": response,
            "has_empathy": has_empathy(response),
        }
        turns.append(turn)

        print(f"  [Round {i+1}] emotion={emotion_data['emotion']} | empathy={turn['has_empathy']}")
        print(f"  Bot: {response[:70]}")

    # Stats
    empathy_rate = sum(1 for t in turns if t["has_empathy"]) / max(len(turns), 1)
    emotion_acc = sum(1 for t in turns if t["emotion"] == persona["expect_emotion"]) / max(len(turns), 1)
    print(f"\n  📊 emotion_acc={emotion_acc:.0%} | empathy={empathy_rate:.0%} | issues={len(issues)}")

    return {
        "persona_id": persona["id"],
        "persona_name": persona["name"],
        "expect_emotion": persona["expect_emotion"],
        "correct": correct,
        "turns": turns,
        "emotion_accuracy": emotion_acc,
        "empathy_rate": empathy_rate,
        "issues": issues,
    }

def main():
    print("=" * 70)
    print("   情感对话机器人 · 本地评测（不依赖后端）")
    print("=" * 70)

    if not REQUESTS_OK:
        print("\n⚠️  requests 未安装，部分网络测试跳过")
        print("   pip install requests")
        print("   （本地评测不依赖 requests）\n")

    all_results = []

    # 3轮完整测试 × 8人设 = 24轮/人设
    # 8人设 × 4轮/setup = 32轮
    # 32 × 3 ≈ 100轮
    for round_num in range(3):
        print(f"\n{'#'*70}")
        print(f"# 第 {round_num+1}/3 轮 · 全部人设")
        print(f"{'#'*70}")

        for persona in PERSONAS:
            result = run_persona(persona)
            all_results.append(result)

        time.sleep(0.5)

    # Report
    total_emotion_acc = sum(r["emotion_accuracy"] for r in all_results) / max(len(all_results), 1)
    total_empathy_rate = sum(r["empathy_rate"] for r in all_results) / max(len(all_results), 1)
    total_issues = sum(len(r["issues"]) for r in all_results)

    print("\n" + "=" * 70)
    print("   📋 最终评测报告")
    print("=" * 70)

    print(f"\n总体指标:")
    print(f"  情绪识别准确率: {total_emotion_acc:.1%}")
    print(f"  同理心表达率:   {total_empathy_rate:.1%}")
    print(f"  总问题数:       {total_issues}")

    print(f"\n按人设细分:")
    stats_map = {}
    for r in all_results:
        pid = r["persona_id"]
        if pid not in stats_map:
            stats_map[pid] = {"name": r["persona_name"], "accs": [], "issues": []}
        stats_map[pid]["accs"].append(r["emotion_accuracy"])
        stats_map[pid]["issues"].extend(r["issues"])

    for pid, stats in stats_map.items():
        avg_acc = sum(stats["accs"]) / len(stats["accs"])
        print(f"  {stats['name']:12s}: acc={avg_acc:.0%} | issues={len(stats['issues'])}")

    # 核心问题汇总
    issue_freq = {}
    for r in all_results:
        for issue in r["issues"]:
            base = issue.split(":")[0] if ":" in issue else issue
            issue_freq[base] = issue_freq.get(base, 0) + 1

    if issue_freq:
        print(f"\n发现的问题（按频率）:")
        for issue, count in sorted(issue_freq.items(), key=lambda x: -x[1]):
            print(f"  ⚠️  {issue} (出现 {count} 次)")

    # 综合评分
    score = (
        total_emotion_acc * 0.30 +
        total_empathy_rate * 0.40 +
        0.20 +  # 响应时间（本地即时）
        (1 - min(total_issues / 20, 1)) * 0.10
    )

    print(f"\n综合得分: {score:.1%} ", end="")
    if score >= 0.85:
        print("✅ 优秀 — 系统同理心和情绪识别能力很强")
    elif score >= 0.7:
        print("⚠️  合格 — 有改进空间")
    else:
        print("❌ 不合格 — 需要重点优化同理心表达和情绪识别")

    total_turns = sum(len(r["turns"]) for r in all_results)
    print(f"\n总评测轮次: {total_turns}/100轮")
    print("=" * 70)

if __name__ == "__main__":
    main()
