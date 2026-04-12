"""
配置模板 — 复制为 config.py 并填入你的密钥

cp python_service/config.example.py python_service/config.py
然后编辑 config.py 填入真实密钥
"""
from pathlib import Path

# --- MiniMax LLM ---
MINIMAX_API_KEY = ""          # MiniMax API Key (必填)
MINIMAX_BASE_URL = "https://api.minimaxi.com/v1"
LLM_MODEL = "MiniMax-M2.7"
LLM_TEMPERATURE = 0.8

# --- Tavily Web Search (可选) ---
TAVILY_API_KEY = ""          # Tavily API Key (选填，不填则 web-search 工具不可用)
# 获取方式: https://app.tavily.com

# --- Redis ---
REDIS_URL = "localhost:6379"

# --- 前端跨域 ---
ALLOWED_ORIGINS = ["http://localhost:3000", "http://localhost:8080"]

# --- 服务器地址 ---
HOST = "0.0.0.0"
PORT = 8000

# --- 可选: 百度天气 API ---
BAIDU_WEATHER_API_KEY = ""   # 选填，不填则使用免费的百度天气
