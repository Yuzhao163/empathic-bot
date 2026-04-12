# EmpathicBot — 情感对话机器人

多语言技术栈实现的 AI 情感助手，基于 MiniMax LLM 提供温暖、有同理心的对话体验。

## 技术栈

| 服务 | 语言 | 职责 | 参考项目 |
|------|------|------|---------|
| API 网关 | Go | 请求路由、WebSocket、限流、Redis 存储 | Ollama Scheduler |
| LLM 服务 | Python | 情绪检测、LLM 调用、流式响应 | LangChain LCEL |
| 前端 | TypeScript/React | 对话界面、情绪可视化 | Gradio Blocks |

## 架构

```
用户输入 → Go Gateway → Python LLM Service → 流式推送 → 前端
                ↓
          Redis 会话存储
```

## 快速部署

### 前端（Vercel）

1. Fork 本仓库
2. Vercel Import → 选择 `frontend/`
3. 设置环境变量：`VITE_GATEWAY_URL` = 你的 Railway Gateway 地址
4. Deploy

### 后端（Railway）

1. Fork 本仓库
2. Railway → New Project → Deploy from GitHub
3. 添加 **Redis** 插件（自动注入 `REDIS_URL`）
4. 设置环境变量：
   - `MINIMAX_API_KEY`（必填）
   - `LLM_MODEL` = `MiniMax-M2.7`
   - `ALLOWED_ORIGINS` = 你的 Vercel 域名

详细步骤：[DEPLOY.md](DEPLOY.md)

## 本地开发

```bash
# 1. 启动 Redis
make run-redis

# 2. 启动 Gateway
make run-gateway

# 3. 启动 Python LLM Service
make run-python

# 4. 启动前端
cd frontend && npm install && npm run dev
```

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `MINIMAX_API_KEY` | ✅ | — | MiniMax API Key |
| `LLM_MODEL` | | `MiniMax-M2.7` | LLM 模型 |
| `LLM_TEMPERATURE` | | `0.8` | 回复随机性 |
| `LLM_MAX_TOKENS` | | `1000` | 回复最大长度 |
| `MAX_CONTEXT_TOKENS` | | `6000` | 上下文截断阈值 |
| `ALLOWED_ORIGINS` | | `http://localhost:3000` | CORS 白名单（逗号分隔）|
| `REDIS_URL` | | `localhost:6379` | Redis 地址 |

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/chat` | POST | 发送消息（非流式）|
| `/api/chat/stream` | GET | SSE 流式对话 |
| `/api/history/:session_id` | GET | 获取历史记录 |
| `/api/sessions` | GET | 列出所有会话 |
| `/ws/chat` | WS | WebSocket 对话 |
| `/health` | GET | 健康检查 |
| `/metrics` | GET | Prometheus 指标 |

## 功能特性

- 😊 **情绪识别**：自动检测 6 种情绪（开心/难过/焦虑/愤怒/悲伤/平静）
- 💬 **流式回复**：SSE 实时流式输出，打字机效果
- 🌙 **深色模式**：支持浅色/深色/跟随系统
- 📊 **情绪趋势**：可视化情绪变化曲线
- 🔒 **安全**：CORS 白名单、IP 限流、消息长度限制
