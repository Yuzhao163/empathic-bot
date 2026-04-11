# 本地开发指南

## 前提条件

- Node.js >= 18
- Python >= 3.10
- Go >= 1.21
- Redis（可使用 Docker）

## 快速启动

### 1. 启动 Redis

```bash
# 使用 Docker
docker run -d -p 6379:6379 --name redis redis:7-alpine

# 或使用 Homebrew
brew install redis && brew services start redis
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入你的 API Key
```

### 3. 启动各服务

**方式A：分别启动（推荐开发）**

```bash
# Terminal 1: Python LLM Service
cd python_service
pip install -r requirements.txt  # 如果有
uvicorn main:app --reload --port 8001

# Terminal 2: Gateway (Go)
cd gateway
go run main.go

# Terminal 3: Frontend
cd frontend
npm install
npm run dev
```

**方式B：使用 Docker Compose**

```bash
docker-compose up
```

## 服务端口

| 服务 | 端口 | URL |
|------|------|-----|
| Frontend | 3000 | http://localhost:3000 |
| Gateway | 8080 | http://localhost:8080 |
| Python LLM | 8001 | http://localhost:8001 |
| Java Emotion | 8002 | http://localhost:8002 |
| Redis | 6379 | redis://localhost:6379 |

## API 端点

- `POST /chat` - 发送消息
- `POST /chat/stream` - 流式聊天
- `GET /health` - 健康检查

## 故障排查

### Python Service 启动失败
```bash
cd python_service
pip install fastapi uvicorn langchain-openai langchain-community
```

### Redis 连接失败
```bash
docker start redis
```

### 前端无法连接 Gateway
检查 `VITE_GATEWAY_URL` 环境变量是否指向正确的 Gateway 地址。
