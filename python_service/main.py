"""
EmpathicBot LLM Service
"""

import os
import json
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from openai import OpenAI

from dataclasses import asdict
from memory import MemoryManager

# ============================================================================
# Config
# ============================================================================

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
if not MINIMAX_API_KEY:
    raise ValueError("MINIMAX_API_KEY environment variable is required")

MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "MiniMax-M2.7")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.8"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1000"))
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", "6000"))
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

openai_client = OpenAI(
    api_key=MINIMAX_API_KEY,
    base_url=MINIMAX_BASE_URL,
    max_connections=100,
)
executor = ThreadPoolExecutor(max_workers=20)

# ============================================================================
# Shared emotion lexicon
# ============================================================================

SHARED_DIR = Path(__file__).parent.parent / "shared"
EMOTION_FILE = SHARED_DIR / "emotions.json"


def load_emotions():
    if EMOTION_FILE.exists():
        with open(EMOTION_FILE) as f:
            return json.load(f)
    return None


_emotion_data = load_emotions()
EMOTION_LEXICON = _emotion_data.get("emotions", {}) if _emotion_data else {}
PRIORITY_KW = _emotion_data.get("priority_keywords", {}) if _emotion_data else {}

if not EMOTION_LEXICON:
    EMOTION_LEXICON = {
        "positive": {"prob": 0.85, "emoji": "😊", "advice": "💖 保持好心情！", "keywords": ["开心", "高兴", "happy", "great"]},
        "negative": {"prob": 0.80, "emoji": "💙", "advice": "💙 深呼吸，和信任的人聊聊。", "keywords": ["难过", "伤心", "sad", "depressed"]},
        "anxious":  {"prob": 0.78, "emoji": "🌸", "advice": "🌸 做5次深呼吸。", "keywords": ["焦虑", "担心", "anxious", "worried"]},
        "angry":    {"prob": 0.82, "emoji": "🤍", "advice": "🤍 描述感受，而非压抑。", "keywords": ["生气", "愤怒", "angry", "hate"]},
        "sad":      {"prob": 0.80, "emoji": "😢", "advice": "😢 允许自己感受情绪。", "keywords": ["哭泣", "分手", "sad", "crying"]},
        "neutral":  {"prob": 0.70, "emoji": "🌿", "advice": "🌿 继续说吧。", "keywords": []},
    }
    PRIORITY_KW = {
        "angry":    ["生气", "愤怒", "讨厌", "烦", "angry", "hate", "furious", "mad", "rage", "骂"],
        "sad":      ["哭", "泪", "分手", "失恋", "sad", "crying", "lonely", "孤独"],
        "anxious":  ["焦虑", "担心", "害怕", "紧张", "anxious", "worried", "scared", "压力", "考研"],
        "positive": ["开心", "高兴", "快乐", "棒", "happy", "great", "wonderful", "love", "joy", "太好了"],
        "negative": ["难过", "伤心", "痛苦", "抑郁", "崩溃", "sad", "hurt", "depressed", "绝望"],
    }

EMPATHY_RESPONSES = {
    "positive": ["太好了！😊 有什么特别让你开心的细节吗？", "太棒了！🌟 真为你高兴！是什么事情？", "哇，听起来很开心！💖"],
    "negative": ["我听到了 💙 谢谢你愿意告诉我。有时候倾诉本身就是疗愈。", "我能理解你现在的心情 💙 愿意再多说一些吗？", "我理解这让你很难受 💙 你不必强撑。"],
    "anxious":  ["焦虑是很常见的情绪 🌸 深呼吸，我们慢慢来。", "我能感受到你的压力 🌸 把担心的事说出来，我们一起梳理？", "焦虑时，试着把注意力带回当下 🌸"],
    "angry":    ["我听到了 🤍 愤怒是完全正常的情绪。能说说发生了什么吗？", "我能理解你为什么生气 🤍 被这样对待真的很让人恼火。", "愤怒也是一种需要被看到的情绪 🤍"],
    "sad":      ["我听到了 💙 我能感受到你现在的难过。", "听起来你经历了一些难过的事 💙 允许自己感受这些，好吗？", "我很高兴你愿意说出来 💙 我在这里。"],
    "neutral":  ["好的 🌿 还有什么是想分享的吗？", "明白了 🌿 愿意多说一些吗？", "继续说吧，我愿意倾听 🌿"],
}

SYSTEM_PROMPT = """你是一个温暖、有同理心的情感支持助手。
当前用户情绪状态：{emotion}
情绪置信度：{emotion_prob:.0%}

回复原则：
1. 先认可用户的情绪，不否定不忽视
2. 温暖、口语化语言
3. 根据情绪调整语气
4. 适当提开放式问题
5. 必要时提供简短心理健康建议

对话历史：
{history}

用户：{message}
助手："""

# ============================================================================
# Emotion Detection
# ============================================================================


def detect_emotion(text: str) -> tuple[str, float]:
    text_lower = text.lower()
    for emotion, words in PRIORITY_KW.items():
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
# Token & Context
# ============================================================================


def estimate_tokens(text: str) -> int:
    """Rough estimate: ~4 chars per token for Chinese+English mixed text."""
    return len(text) // 4


def truncate_history(context: list, max_tokens: int) -> list:
    """Drop oldest messages until total fits within token budget."""
    total = sum(estimate_tokens(msg.get("content", "")) for msg in context)
    if total <= max_tokens:
        return context
    result = []
    for msg in reversed(context):
        tokens = estimate_tokens(msg.get("content", ""))
        if total - tokens <= max_tokens:
            result.insert(0, msg)
            total -= tokens
        else:
            break
    return result or context[-4:]


def build_prompt(message: str, emotion: str, emotion_prob: float, context: list) -> str:
    truncated = truncate_history(context, MAX_CONTEXT_TOKENS)
    history_str = ""
    for msg in truncated:
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


def get_empathy_response(emotion: str) -> str:
    responses = EMPATHY_RESPONSES.get(emotion, EMPATHY_RESPONSES["neutral"])
    return responses[int(time.time() * 1000) % len(responses)]


# ============================================================================
# App
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
# LLM Calls
# ============================================================================


async def call_llm(prompt: str, message: str) -> str:
    def _call():
        resp = openai_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": message},
            ],
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
        )
        return resp.choices[0].message.content

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _call)


async def call_llm_stream(prompt: str, message: str):
    """
    Run blocking SSE stream in thread pool, yield SSE-formatted tokens.
    """
    def _stream_sync():
        try:
            stream = openai_client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": message},
                ],
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as e:
            print(f"[Stream Error] {e}")
            yield f"data: {json.dumps({'token': ''})}\n\n"

    loop = asyncio.get_event_loop()
    gen = _stream_sync()
    while True:
        try:
            chunk = await asyncio.wait_for(
                loop.run_in_executor(executor, next, iter(gen)),
                timeout=60.0,
            )
            yield chunk
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'done': True, 'error': 'timeout'})}\n\n"
            break
        except StopIteration:
            break
        except Exception as e:
            print(f"[Stream loop] {e}")
            yield f"data: {json.dumps({'done': True, 'error': str(e)})}\n\n"
            break


# ============================================================================
# Models
# ============================================================================


class ChatRequest(BaseModel):
    session_id: str = ""
    message: str
    context: list = []
    emotion: str = "neutral"
    emotion_prob: float = 0.5
    # memory control
    memory_level: str = "auto"  # "short" | "medium" | "long" | "auto"


class ChatResponse(BaseModel):
    text: str
    emotion: str
    emotion_prob: float
    advice: str = ""


# ============================================================================
# HTTP Endpoints
# ============================================================================


@app.post("/chat")
async def chat(req: ChatRequest):
    if len(req.message) > 2000:
        raise HTTPException(status_code=400, detail="message too long, max 2000 characters")

    emotion = req.emotion
    emotion_prob = req.emotion_prob
    if req.message:
        emotion, emotion_prob = detect_emotion(req.message)

    # Memory management
    mem = MemoryManager(session_id=req.session_id or "default")

    # Add user message to memory
    mem.add_message("user", req.message, emotion)

    # Check if we need to summarize
    if mem.should_summarize():
        full_history = mem.get_short_term(limit=MEDIUM_MAX_MESSAGES)
        def llm_fn(prompt_text):
            resp = openai_client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt_text}],
                temperature=0.5,
                max_tokens=MAX_SUMMARY_TOKENS,
            )
            return resp.choices[0].message.content
        mem.summarize_and_evict(full_history, llm_fn)

    # Build context from three memory layers
    context_str = mem.get_context_for_llm()

    # Build prompt with full memory context
    system_prompt = SYSTEM_PROMPT.format(
        emotion=emotion,
        emotion_prob=emotion_prob * 100,
        history=context_str,
        message=req.message,
    )

    try:
        text = await call_llm(system_prompt, req.message)
    except Exception as e:
        print(f"[LLM Error] {e}")
        text = get_empathy_response(emotion)

    # Store assistant response in memory
    mem.add_message("assistant", text, emotion)

    advice = EMOTION_LEXICON.get(emotion, EMOTION_LEXICON["neutral"])["advice"]
    return ChatResponse(
        text=text,
        emotion=emotion,
        emotion_prob=emotion_prob,
        advice=advice,
    )


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    if len(req.message) > 2000:
        raise HTTPException(status_code=400, detail="message too long, max 2000 characters")

    emotion = req.emotion
    emotion_prob = req.emotion_prob
    if req.message:
        emotion, emotion_prob = detect_emotion(req.message)

    # Memory management
    mem = MemoryManager(session_id=req.session_id or "default")
    mem.add_message("user", req.message, emotion)

    if mem.should_summarize():
        full_history = mem.get_short_term(limit=MEDIUM_MAX_MESSAGES)
        def llm_fn(prompt_text):
            resp = openai_client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt_text}],
                temperature=0.5,
                max_tokens=MAX_SUMMARY_TOKENS,
            )
            return resp.choices[0].message.content
        mem.summarize_and_evict(full_history, llm_fn)

    context_str = mem.get_context_for_llm()
    system_prompt = SYSTEM_PROMPT.format(
        emotion=emotion,
        emotion_prob=emotion_prob * 100,
        history=context_str,
        message=req.message,
    )

    advice = EMOTION_LEXICON.get(emotion, {})["advice"]

    async def stream():
        try:
            async for chunk_data in call_llm_stream(system_prompt, req.message):
                yield chunk_data
        except Exception as e:
            print(f"[Stream Error] {e}")
            fallback = get_empathy_response(emotion)
            for char in fallback:
                yield f"data: {json.dumps({'token': char})}\n\n"
        # Store assistant response in memory after stream ends
        # We accumulate the full response via SSE done signal instead
        yield f"data: {json.dumps({'done': True, 'emotion': emotion, 'advice': advice})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/health")
async def health():
    try:
        test_resp = openai_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=5,
        )
        llm_ok = bool(test_resp.choices[0].message.content)
    except Exception as e:
        print(f"[Health] LLM failed: {e}")
        llm_ok = False

    return {
        "status": "ok",
        "model": LLM_MODEL,
        "llm": llm_ok,
        "temperature": LLM_TEMPERATURE,
    }


@app.post("/emotion/analyze")
async def analyze_emotion(req: Request):
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


@app.get("/memory/{session_id}")
async def get_memory(session_id: str, level: str = "full"):
    """
    查询指定session的记忆状态
    level: short | medium | long | full
    """
    mem = MemoryManager(session_id=session_id)
    result = {"session_id": session_id}

    if level in ("short", "full"):
        result["short_term"] = mem.get_short_term()
        result["short_tokens"] = mem.get_short_term_tokens()

    if level in ("medium", "full"):
        result["medium_summary"] = mem.get_medium_summary()

    if level in ("long", "full"):
        result["long_term_facts"] = [asdict(f) for f in mem.get_long_term_facts()]

    return result


@app.post("/memory/{session_id}/summarize")
async def force_summarize(session_id: str):
    """
    强制触发中记忆压缩（通常自动触发，也可手动调用）
    """
    mem = MemoryManager(session_id=session_id)
    full_history = mem.get_short_term(limit=MEDIUM_MAX_MESSAGES)

    def llm_fn(prompt_text):
        resp = openai_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt_text}],
            temperature=0.5,
            max_tokens=MAX_SUMMARY_TOKENS,
        )
        return resp.choices[0].message.content

    summary = mem.summarize_and_evict(full_history, llm_fn)
    return {"summary": summary}


@app.delete("/memory/{session_id}")
async def delete_memory(session_id: str, level: str = "all"):
    """
    删除指定层级的记忆
    level: short | medium | long | all
    """
    mem = MemoryManager(session_id=session_id)
    if level in ("short", "all"):
        rdb.delete(f"mem:{session_id}:short")
    if level in ("medium", "all"):
        rdb.delete(f"mem:{session_id}:medium")
    if level in ("long", "all"):
        rdb.delete(f"mem:{session_id}:long")
        # 删除文件
        path = Path(MEMORY_DIR) / f"{mem.user_id}.jsonl"
        if path.exists():
            path.unlink()
    return {"ok": True, "deleted": level}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
