# EmpathicBot — 情感对话机器人

多语言技术栈实现的 AI 情感助手，参考十大开源项目架构。

## 技术栈

| 服务 | 语言 | 职责 | 参考项目 |
|------|------|------|---------|
| Gateway | Go | API 网关 + WebSocket | Ollama Scheduler |
| LLM Service | Python | 情绪感知回复生成 | LangChain LCEL |
| Emotion Engine | Java | 情绪识别 NLP | Transformers |
| Frontend | TypeScript/React | 对话界面 | Gradio Blocks |

## 快速启动

```bash
# 启动全部服务
docker-compose up -d

# 仅启动前端（开发）
cd frontend && npm install && npm run dev
```

## 架构

```
用户输入 → Go Gateway → Python LLM Service → 流式推送 → 前端
                ↓
          Java Emotion Engine（并行）
                ↓
          Redis 会话存储
```

## API 端点

- `POST /api/chat` — 发送消息
- `GET /api/history/{session_id}` — 获取历史
- `WebSocket /ws/chat` — 流式对话
- `POST /api/emotion/analyze` — 情绪分析

## 环境变量

```env
# Python LLM
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o

# Java Emotion
EMOTION_MODEL_PATH=models/emotion_classifier

# Redis
REDIS_URL=redis://localhost:6379
```
