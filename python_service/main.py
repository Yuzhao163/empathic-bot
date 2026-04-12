"""
EmpathicBot LLM Service — 基于 LangChain LCEL 管道
完整版：含情绪词典 + 多样化回复模板
"""

import os
import json
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncIterator

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from openai import OpenAI
from langchain_core.messages import HumanMessage, SystemMessage

# ============================================================================
# Config Validation
# ============================================================================

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
if not MINIMAX_API_KEY:
    raise ValueError("MINIMAX_API_KEY environment variable is required")

MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "MiniMax-M2.7")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.8"))
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

# ============================================================================
# OpenAI Compatible Client
# ============================================================================

openai_client = OpenAI(
    api_key=MINIMAX_API_KEY,
    base_url=MINIMAX_BASE_URL,
    max_connections=100,
)

executor = ThreadPoolExecutor(max_workers=20)

# ============================================================================
# App Setup
# ============================================================================

app = FastAPI(title="EmpathicBot LLM Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# 情绪词典 — 扩充版
# ============================================================================

EMOTION_LEXICON = {
    "positive": {
        "prob": 0.85,
        "emoji": "😊",
        "advice": "💖 保持好心情！记录让你开心的事。",
        "keywords": [
            "开心", "高兴", "快乐", "棒", "很好", "谢谢", "喜欢", "爱", "美好", "幸福", "欢欣", "愉悦", "兴奋", "激动",
            "太棒了", "太好了", "好开心", "好高兴", "真棒", "完美", "精彩", "优秀", "厉害", "赞叹", "佩服",
            "满足", "欣慰", "感激", "感动", "暖心", "温馨", "顺利", "成功", "胜利", "通过了",
            "happy", "great", "wonderful", "love", "excited", "joy", "awesome", "fantastic", "amazing",
            "excellent", "perfect", "brilliant", "thrilled", "delighted", "grateful", "thankful",
        ],
    },
    "negative": {
        "prob": 0.80,
        "emoji": "💙",
        "advice": "💙 难过时，深呼吸。和信任的人聊聊会有帮助。",
        "keywords": [
            "难过", "伤心", "痛苦", "抑郁", "绝望", "崩溃", "沮丧", "失落", "心碎", "悲伤", "哀伤", "压抑",
            "委屈", "失落感", "空虚", "疲惫", "无助", "无望", "灰心", "消沉", "颓废",
            "sad", "hurt", "depressed", "devastated", "crying", "misery", "heartbroken", "miserable",
            "gloomy", "hopeless", "desperate", "unhappy", "disappointed",
        ],
    },
    "anxious": {
        "prob": 0.78,
        "emoji": "🌸",
        "advice": "🌸 焦虑时，试着做5次深呼吸，专注当下。",
        "keywords": [
            "焦虑", "担心", "害怕", "紧张", "不安", "压力", "恐惧", "惊慌", "惶恐", "忧虑", "忐忑",
            "好怕", "害怕", "担心", "好紧张", "睡不着", "心慌", "发慌", "不安", "顾虑",
            "考研", "考试", "复习", "来不及", "考不上", "期望",
            "anxious", "worried", "scared", "nervous", "stress", "fear", "panic", "tense", "overwhelmed",
            "stressed", "upset", "dread",
        ],
    },
    "angry": {
        "prob": 0.82,
        "emoji": "🤍",
        "advice": "🤍 愤怒是正常的。描述你的感受，而不是压抑它。",
        "keywords": [
            "生气", "愤怒", "讨厌", "烦", "火", "气死了", "暴躁", "恼火", "愤恨", "发火", "大怒", "忍无可忍",
            "被骂", "批评", "加塞", "路怒", "素质低", "混蛋", "SB", "无语", "真想", "恨不得",
            "angry", "hate", "furious", "mad", "annoyed", "rage", "irritated", "frustrated", "outraged",
            "fuming", "livid",
        ],
    },
    "sad": {
        "prob": 0.80,
        "emoji": "😢",
        "advice": "😢 允许自己感受这些情绪，你值得被爱。",
        "keywords": [
            "哭泣", "流泪", "泪", "心酸", "哭", "哽咽", "泪目", "哭出来",
            "分手", "失恋", "离婚", "感情", "三年", "背叛", "出轨",
            "没人", "孤独", "寂寞", "一个人", "孤单",
            "生病", "住院", "身体", "不舒服", "难受",
            "sad", "hurt", "crying", "tears", "heartache", "grief", "lonely", "sorrow",
            "heartbreak", "heartbroken",
        ],
    },
    "neutral": {
        "prob": 0.70,
        "emoji": "🌿",
        "advice": "🌿 感谢分享，还有什么想聊的吗？",
        "keywords": [],
    },
}

def detect_emotion(text: str) -> tuple[str, float]:
    """基于扩充词典的情绪检测"""
    text_lower = text.lower()

    priority = {
        "angry": ["生气", "愤怒", "讨厌", "烦", "火", "angry", "hate", "furious", "mad", "rage", "骂", "挨骂", "凶"],
        "sad": ["哭", "泪", "分手", "失恋", "离婚", "sad", "crying", "lonely", "孤独", "寂寞"],
        "anxious": ["焦虑", "担心", "害怕", "紧张", "不安", "anxious", "worried", "scared", "nervous", "stress", "压力", "考研", "考不上", "不听话", "顶嘴", "该怎么"],
        "positive": ["开心", "高兴", "快乐", "棒", "happy", "great", "wonderful", "love", "joy", "太好了", "太棒了", "好开心", "发表了", "祝贺", "激动", "朋友们", "半年", "好运", "好棒"],
        "negative": ["难过", "伤心", "痛苦", "抑郁", "崩溃", "sad", "hurt", "depressed", "devastated", "绝望", "失落"],
    }
    for emotion, words in priority.items():
        for word in words:
            if word in text_lower:
                return emotion, EMOTION_LEXICON[emotion]["prob"]

    for emotion, data in EMOTION_LEXICON.items():
        if emotion == "neutral":
            continue
        for word in data["keywords"]:
            if len(word) >= 2 and word in text_lower:
                return emotion, data["prob"]

    return "neutral", 0.70


# ============================================================================
# 多样化同理心回复模板
# ============================================================================

EMPATHY_RESPONSES = {
    "positive": [
        "太好了！😊 我能感受到你的喜悦，有什么特别让你开心的细节吗？",
        "太棒了！🌟 真为你高兴！是什么事情这么开心？",
        "哇，听起来真的很开心！💖 继续享受这份快乐吧！",
        "太让人高兴了！✨ 你分享的这件事一定很特别吧？",
        "哈哈，感受到了你的好心情！🎉 有什么想继续分享的吗？",
    ],
    "negative": [
        "我听到了 💙 谢谢你愿意告诉我这些。有时候倾诉本身就是一种疗愈。",
        "我能理解你现在的心情 💙 愿意再多说一些吗？我在这里倾听。",
        "听起来你经历了一些困难 💙 给自己一些时间和空间，好吗？",
        "我理解这让你很难受 💙 你不必强撑，我陪着你。",
        "感谢你的信任 💙 无论你想说什么，我都在这里。",
    ],
    "anxious": [
        "焦虑是很常见的情绪 🌸 深呼吸，我们慢慢来。你最担心的是什么呢？",
        "我能感受到你的压力 🌸 不妨把担心的事情说出来，我们一起梳理一下？",
        "焦虑时，试着把注意力带回当下 🌸 你现在安全。有什么想说的？",
        "我理解你的担心 🌸 有时候说出来，会感觉好一些。我在听。",
        "你不是在一个人面对 🌸 我们来看看可以怎么缓解你的焦虑？",
    ],
    "angry": [
        "我听到了 🤍 愤怒是完全正常的情绪，被这样对待真的很让人难受。能说说发生了什么吗？",
        "我能理解你为什么这么生气 🤍 被这样对待真的很让人恼火。",
        "愤怒也是一种需要被看到的情绪 🤍 你想聊聊是什么让你这么愤怒吗？",
        "听起来你真的很生气 🤍 我在这里陪你说说。",
        "换做是谁都会生气的 🤍 你愿意多说一些吗？",
    ],
    "sad": [
        "我听到了 💙 我能感受到你现在的难过，愿意再多说一些吗？",
        "听起来你经历了一些难过的事 💙 允许自己感受这些，好吗？",
        "我很高兴你愿意说出来 💙 我听到了，我会陪着你。",
        "无论你感受到什么，都是被允许的 💙 我在这里。",
        "我理解你现在很难过 💙 你不必解释，只需要知道我在这里。",
    ],
    "neutral": [
        "好的 🌿 我在这里，还有什么想分享的吗？",
        "明白了 🌿 愿意多说一些吗？",
        "好的 🌿 你今天过得怎么样？",
        "我听到了 🌿 你想聊聊什么？",
        "明白了 🌿 继续说吧，我愿意倾听。",
    ],
}


def get_empathy_response(emotion: str) -> str:
    """根据情绪返回同理心回复（轮询 + 时间戳多样性）"""
    responses = EMPATHY_RESPONSES.get(emotion, EMPATHY_RESPONSES["neutral"])
    index = int(time.time() * 1000) % len(responses)
    return responses[index]


# ============================================================================
# 系统提示词
# ============================================================================

SYSTEM_PROMPT = """你是一个温暖、有同理心的情感支持助手。
当前用户情绪状态：{emotion}
情绪置信度：{emotion_prob:.0%}

你的回复原则：
1. 先认可用户的情绪，不要否定或忽视
2. 用温暖、口语化的语言回应
3. 根据情绪状态调整语气：
   - 开心：真诚分享喜悦
   - 难过/悲伤：温柔安慰，给予陪伴感
   - 焦虑：平和镇定，帮助梳理
   - 愤怒：理解感受，引导冷静
   - 平静：轻松自然交流
4. 适当提出开放式问题
5. 必要时提供简短心理健康建议

对话历史：
{history}

用户：{message}
助手："""


# ============================================================================
# Request / Response Models
# ============================================================================

class ChatRequest(BaseModel):
    message: str
    context: list = []
    emotion: str = "neutral"
    emotion_prob: float = 0.5


class ChatResponse(BaseModel):
    text: str
    emotion: str
    emotion_prob: float
    advice: str = ""


# ============================================================================
# Internal helpers
# ============================================================================

def build_prompt(message: str, emotion: str, emotion_prob: float, context: list) -> str:
    history_str = ""
    for msg in context[-10:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            history_str += f"用户：{content}\n"
        else:
            history_str += f"助手：{content}\n"
    return SYSTEM_PROMPT.format(
        emotion=emotion,
        emotion_prob=emotion_prob * 100,
        history=history_str or "（这是对话的开始）",
        message=message,
    )


async def call_llm_async(prompt: str, message: str) -> str:
    """在线程池中执行同步 LLM 调用，避免阻塞事件循环"""
    def _call():
        response = openai_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": message}
            ],
            temperature=LLM_TEMPERATURE,
        )
        return response.choices[0].message.content

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _call)


async def call_llm_stream_async(prompt: str, message: str):
    """流式 LLM 调用"""
    def _call():
        stream_response = openai_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": message}
            ],
            temperature=LLM_TEMPERATURE,
            stream=True,
        )
        for chunk in stream_response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield f"data: {json.dumps({'token': chunk.choices[0].delta.content})}\n\n"

    loop = asyncio.get_event_loop()
    async for item in loop.run_in_executor(executor, lambda: list(_call())):
        yield item


# ============================================================================
# HTTP Endpoints
# ============================================================================

@app.post("/chat")
async def chat(req: ChatRequest):
    """非流式聊天接口"""
    if len(req.message) > 2000:
        raise HTTPException(status_code=400, detail="message too long, max 2000 characters")

    emotion = req.emotion
    emotion_prob = req.emotion_prob

    if req.message:
        emotion, emotion_prob = detect_emotion(req.message)

    prompt = build_prompt(req.message, emotion, emotion_prob, req.context)

    try:
        text = await call_llm_async(prompt, req.message)
    except Exception as e:
        print(f"[LLM Error] {e}")
        text = get_empathy_response(emotion)

    advice = EMOTION_LEXICON.get(emotion, EMOTION_LEXICON["neutral"])["advice"]

    return ChatResponse(
        text=text,
        emotion=emotion,
        emotion_prob=emotion_prob,
        advice=advice,
    )


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """流式聊天接口"""
    if len(req.message) > 2000:
        raise HTTPException(status_code=400, detail="message too long, max 2000 characters")

    emotion = req.emotion
    emotion_prob = req.emotion_prob

    if req.message:
        emotion, emotion_prob = detect_emotion(req.message)

    prompt = build_prompt(req.message, emotion, emotion_prob, req.context)

    async def stream():
        try:
            full_response = ""
            async for chunk_data in call_llm_stream_async(prompt, req.message):
                full_response += chunk_data
                yield chunk_data
        except Exception as e:
            print(f"[Stream Error] {e}")
            fallback = get_empathy_response(emotion)
            for char in fallback:
                yield f"data: {json.dumps({'token': char})}\n\n"
        yield f"data: {json.dumps({'done': True, 'emotion': emotion})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/health")
async def health():
    """健康检查：验证 LLM API 连通性"""
    try:
        test_response = openai_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=5,
        )
        llm_ok = test_response.choices[0].message.content != ""
    except Exception as e:
        print(f"[Health] LLM check failed: {e}")
        llm_ok = False

    return {
        "status": "ok",
        "model": LLM_MODEL,
        "llm": llm_ok,
        "temperature": LLM_TEMPERATURE,
    }


@app.post("/emotion/analyze")
async def analyze_emotion(req: Request):
    """情绪分析接口"""
    body = await req.json()
    text = body.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    if len(text) > 2000:
        raise HTTPException(status_code=400, detail="text too long")

    emotion, prob = detect_emotion(text)
    data = EMOTION_LEXICON.get(emotion, EMOTION_LEXICON["neutral"])
    return {
        "emotion": emotion,
        "prob": prob,
        "emoji": data["emoji"],
        "advice": data["advice"],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
