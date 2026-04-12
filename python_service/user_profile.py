"""
用户画像系统 — 昵称、偏好、情感定制
"""

import os
import json
import time
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional

# ============================================================================
# Paths
# ============================================================================

PROFILE_DIR = Path(os.getenv("MEMORY_DIR", "./memory")) / "profiles"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

def _profile_path(user_id: str) -> Path:
    return PROFILE_DIR / f"{user_id}.json"

# ============================================================================
# Emotion Profile — 用户情绪偏好定制
# ============================================================================


@dataclass
class EmotionProfile:
    """用户情绪偏好"""
    # 是否主动打招呼
    greet_enabled: bool = True
    greet_templates: list[str] = field(default_factory=lambda: [
        "今天怎么样？有什么想聊的吗？😊",
        "嗨，欢迎回来！最近心情如何？",
        "你好呀，今天想聊点什么？"
    ])

    # 情绪回复风格
    reply_style: str = "warm"  # warm | concise | poetic | humor

    # 情绪建议详细程度
    advice_level: str = "medium"  # brief | medium | detailed

    # 是否显示情绪趋势图
    show_trend_chart: bool = True

    # 是否开启快捷回复建议
    show_suggestions: bool = True

    # 昵称
    nickname: str = ""

    # 称呼偏好（称呼对方的方式）
    call_me: str = "你"  # 你 | 名字 | 宝宝/亲爱的 等

    # 语言风格
    language_style: str = "auto"  # auto | casual | formal | poetic

    # 深夜模式（更安静的回复）
    night_mode: bool = False
    night_start: int = 23  # 23:00
    night_end: int = 7      # 07:00

    # 自定义情绪词（用户添加的触发词）
    custom_emotion_words: dict[str, list[str]] = field(default_factory=dict)
    # 格式：{"positive": ["开心果", "美滋滋"], "angry": ["炸毛"]}

    # 自定义回复模板（覆盖默认同理心回复）
    custom_responses: dict[str, list[str]] = field(default_factory=dict)
    # 格式：{"positive": ["自定义回复1", "自定义回复2"]}


# ============================================================================
# User Profile
# ============================================================================


@dataclass
class UserProfile:
    """完整用户画像"""
    user_id: str
    nickname: str = ""
    avatar: str = ""             # 头像URL或emoji
    display_name: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    emotion_profile: EmotionProfile = field(default_factory=EmotionProfile)
    # 统计
    total_sessions: int = 0
    total_messages: int = 0
    dominant_emotion: str = "neutral"
    last_seen: float = 0.0


def _now() -> float:
    return time.time()


def get_profile(user_id: str) -> UserProfile:
    path = _profile_path(user_id)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            data["emotion_profile"] = EmotionProfile(**data.get("emotion_profile", {}))
            return UserProfile(**data)
    return UserProfile(user_id=user_id, created_at=_now(), updated_at=_now())


def save_profile(profile: UserProfile) -> None:
    profile.updated_at = _now()
    path = _profile_path(profile.user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(profile)
    data["emotion_profile"] = asdict(profile.emotion_profile)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def update_nickname(user_id: str, nickname: str) -> UserProfile:
    profile = get_profile(user_id)
    profile.nickname = nickname
    profile.display_name = nickname
    save_profile(profile)
    return profile


def update_emotion_profile(user_id: str, updates: dict) -> UserProfile:
    """部分更新情绪配置"""
    profile = get_profile(user_id)
    ep = profile.emotion_profile
    for key, value in updates.items():
        if hasattr(ep, key):
            setattr(ep, key, value)
    save_profile(profile)
    return profile


def delete_memory_for_user(user_id: str, level: str = "all") -> dict:
    """
    删除用户指定层级的记忆和画像
    level: short | medium | long | all | profile
    """
    import redis as redis_lib

    REDIS_URL = os.getenv("REDIS_URL", "localhost:6379")
    if REDIS_URL.startswith("redis://"):
        REDIS_URL = REDIS_URL[9:]
    rdb = redis_lib.Redis(
        host=REDIS_URL.split(":")[0],
        port=int(REDIS_URL.split(":")[-1]),
        db=0,
        decode_responses=True
    )

    deleted = []
    # 短期/中期记忆（Redis，按 user_id 模糊匹配 session_* keys）
    if level in ("short", "medium", "all"):
        cursor = 0
        pattern = f"mem:*"  # 简化：删除该用户所有记忆keys
        while True:
            cursor, keys = rdb.scan(cursor=cursor, match="mem:*", count=100)
            user_keys = [k for k in keys if user_id in k or f"default" in k]
            if user_keys:
                rdb.delete(*user_keys)
                deleted.extend(user_keys)
            if cursor == 0:
                break

    # 长期记忆文件
    long_file = Path(os.getenv("MEMORY_DIR", "./memory")) / "long_term" / f"{user_id}.jsonl"
    if level in ("long", "all") and long_file.exists():
        long_file.unlink()
        deleted.append(str(long_file))

    # 用户画像
    profile_file = _profile_path(user_id)
    if level in ("profile", "all") and profile_file.exists():
        profile_file.unlink()
        deleted.append(str(profile_file))

    return {"deleted": deleted, "level": level, "user_id": user_id}


# ============================================================================
# 增强版同理心回复生成器
# ============================================================================

STYLE_RESPONSES = {
    "warm": {
        "positive": [
            "太好了！{nick}，真替你开心！🌟 有什么特别的原因吗？",
            "哇，{nick}心情这么好！😊 继续分享一下吧，我爱听！",
            "感受到{nick}的快乐了！💖 最近是什么让你这么开心呀？",
            "{nick}开心，我也开心！✨ 有什么好消息吗？",
            "太棒了！{nick}！有什么想聊聊的吗？",
        ],
        "negative": [
            "我听到了 💙 {nick}最近是不是有些难过的时刻？愿意说说吗？",
            "抱抱{nick} 💙 不开心的时候，我都在。",
            "{nick}，辛苦了 💙 想说就说，我愿意听。",
            "我理解你的感受 💙 {nick}不必逞强。",
            "难过的时候，可以什么都不做，我陪着你 💙",
        ],
        "anxious": [
            "深呼吸 🌸 {nick}，我们慢慢来。先说说最担心的是什么？",
            "焦虑很正常 🌸 {nick}，我在这里，和你一起梳理。",
            "慢慢来 🌸 {nick}，先把担心的事说出来，好吗？",
            "感到压力的时候，{nick}，我愿意陪你聊聊 🌸",
            "别急 🌸 {nick}，有什么想说的我都在听。",
        ],
        "angry": [
            "生气是正常的 🤍 {nick}，被这样对待，换谁都会不开心的。",
            "我听到了 🤍 {nick}想说说发生了什么吗？",
            "愤怒是因为在乎 🤍 {nick}，想说就说，我不评判。",
            "有我在 🤍 {nick}，把委屈说出来吧。",
            "陪{nick}一起 🤍 你不是一个人。",
        ],
        "sad": [
            "我很高兴{nick}愿意说出来 💙 愿意再多说一点吗？",
            "无论{nick}感受到什么，都是被允许的 💙 我在这里。",
            "抱抱{nick} 💙 想说多少都可以。",
            "{nick}的难过，我收到了 💙 我在这里陪着你。",
            "允许自己难过 💙 {nick}不必逞强，慢慢来。",
        ],
        "neutral": [
            "我在这里，{nick} 🌿 想聊什么都可以。",
            "继续说吧 🌿 {nick}，我愿意听。",
            "今天过得怎么样，{nick}？ 🌿",
            "我听着呢 🌿 慢慢说，不着急。",
            "想说就说 🌿 无论什么，我都陪{nick}聊。",
        ],
    },
    "concise": {
        "positive": ["太好了！😊 怎么了？"],
        "negative": ["我听到了 💙 想说吗？"],
        "anxious": ["嗯 🌸 慢慢说。"],
        "angry": ["嗯 🤍 在呢。"],
        "sad": ["嗯 💙 我在听。"],
        "neutral": ["嗯 🌿 说。"],
    },
    "poetic": {
        "positive": ["春风拂面 🌸 {nick}，是什么带来了这份美好？"],
        "negative": ["秋意渐浓 💙 {nick}，我愿做那盏灯火。"],
        "anxious": ["云雾重重 🌸 {nick}，静待日出。"],
        "angry": ["雷声隐隐 🤍 {nick}，风暴终会过去。"],
        "sad": ["夜色温柔 💙 {nick}，我陪你等黎明。"],
        "neutral": ["清风徐来 🌿 {nick}，且听风吟。"],
    },
    "humor": {
        "positive": ["哈哈哈{nick}！😆 什么好事，说来听听！"],
        "negative": ["哎呀{nick} 😔 来，聊五毛钱的？"],
        "anxious": ["深呼吸 🌸 {nick}，焦虑这家伙又来了是吧？"],
        "angry": ["生气正常 🤍 {nick}，来，吐槽一下？"],
        "sad": ["抱抱{nick} 🥺 不开心就来找我，不收费。"],
        "neutral": ["嘿{nick} 🌿 最近咋样？"],
    },
}

NIGHT_RESPONSES = {
    "positive": ["夜深了还这么开心 🌙 {nick}，有什么美梦要说给我听？"],
    "neutral": ["晚安前的悄悄话 🌙 {nick}，我听着呢。"],
    "default": ["夜深了 🌙 {nick}，早点休息，我在这里守着你。"],
}


def get_human_reply(emotion: str, user_id: str = None) -> str:
    """根据用户画像和当前时间生成最合适的回复"""
    profile = get_profile(user_id or "default")
    ep = profile.emotion_profile
    now = time.localtime()
    hour = now.tm_hour
    is_night = ep.night_mode and (hour >= ep.night_start or hour < ep.night_end)

    nickname = ep.nickname or "朋友"

    # 深夜模式特殊回复
    if is_night and emotion in NIGHT_RESPONSES:
        template = NIGHT_RESPONSES.get(emotion, NIGHT_RESPONSES["default"])
    else:
        style = ep.reply_style or "warm"
        pool = STYLE_RESPONSES.get(style, STYLE_RESPONSES["warm"])
        template = pool.get(emotion, pool["neutral"])

    import random
    choice = template[int(time.time() * 1000) % len(template)]
    return choice.replace("{nick}", nickname)


def get_greeting(user_id: str = None) -> str:
    """生成问候语"""
    profile = get_profile(user_id or "default")
    ep = profile.emotion_profile
    if not ep.greet_enabled:
        return None
    greetings = ep.greet_templates or ["你好呀！😊 有什么想聊的吗？"]
    import random
    return greetings[int(time.time() * 1000) % len(greetings)]


def get_suggestion_prompts(emotion: str = "neutral", user_id: str = None) -> list[str]:
    """根据情绪返回引导性问题建议"""
    prompts = {
        "positive": ["最近有什么特别开心的事吗？", "这份快乐想一直延续下去吗？", "有什么计划吗？"],
        "negative": ["最近是什么让你难过？", "愿意多说一点吗？", "有没有试过找人聊聊？"],
        "anxious": ["最担心的事情是什么？", "这种情况多久了？", "有没有试过什么方法缓解？"],
        "angry": ["发生了什么？", "有什么想吐槽的吗？", "发泄一下也好。"],
        "sad": ["愿意说说吗？", "我陪着你 💙", "什么时候开始的？"],
        "neutral": ["今天过得怎么样？", "有什么想法吗？", "随便聊聊？"],
    }
    return prompts.get(emotion, prompts["neutral"])
