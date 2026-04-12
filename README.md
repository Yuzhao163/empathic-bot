# EmpathicBot — 情感对话机器人

多语言技术栈实现的 AI 情感助手，参考十大开源项目架构。

## 🚀 快速部署

### 前端（Vercel）

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new)

1. Fork 本仓库
2. Vercel Import → 选择 `frontend/`
3. 设置 `VITE_GATEWAY_URL` 为 Railway Gateway 地址

### 后端（Railway）

[![Deploy on Railway](https://railway.app/button)](https://railway.app/new)

1. Fork 本仓库
2. Railway → New Project → Deploy from GitHub
3. 添加 Redis 插件
4. 设置 `OPENAI_API_KEY`

详细步骤：[DEPLOY.md](DEPLOY.md)

## 技术栈

| 服务 | 语言 | 参考项目 |
|------|------|---------|
| API 网关 | Go | Ollama Scheduler |
| LLM 服务 | Python | LangChain LCEL |
| 情绪分析 | Java | Transformers |
| 前端 | TypeScript/React | Gradio Blocks |
</parameter>
