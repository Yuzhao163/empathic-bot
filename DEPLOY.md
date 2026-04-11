# 部署指南

## 方案：Railway (后端) + Vercel (前端)

**Railway**：有免费额度（500小时/月），关联 GitHub 自动部署，支持 Redis 插件
**Vercel**：前端完全免费，静态部署

---

## 第一步：Fork 代码到 GitHub

1. 把 `empathic-bot/` 目录 push 到你 GitHub（新建仓库）
2. 仓库设为 public（或 private 也可以）

---

## 第二步：Railway 部署后端

### 2.1 创建项目

1. 打开 [railway.app](https://railway.app)
2. Login with GitHub
3. **New Project → Deploy from GitHub repo** → 选你的仓库
4. 选择 `gateway/` 目录作为根目录

### 2.2 添加 Redis

- Railway 插件面板 → **Add Plugin → Redis** → 自动注入 `REDIS_URL`

### 2.3 设置环境变量

- `OPENAI_API_KEY` = 你的 key
- `LLM_MODEL` = `gpt-4o`
- `REDIS_URL` = 自动从插件注入（不需要手动填）

### 2.4 根目录配置

Railway 默认用 Go 编译，`gateway/` 下已有 `go.mod`，Railway 会自动识别。

**端口**：`8080`（Go 默认）

### 2.5 等待部署完成

Railway 会给一个 URL，例如：`https://empathic-bot.up.railway.app`

---

## 第三步：Vercel 部署前端

### 3.1 修改 API 地址

在 `.env.production` 里指向 Railway 地址：
```
VITE_GATEWAY_URL=https://你的railway-app.railway.app
```

### 3.2 Vercel 创建项目

1. [vercel.com](https://vercel.com) → New Project → Import GitHub 仓库
2. Framework: Next.js 或 Vite
3. Root Directory: `frontend`
4. Build Command: `npm run build`
5. Environment Variables: `VITE_GATEWAY_URL=https://xxx.railway.app`

---

## 第四步：验证

- 前端：`vercel.app` 域名
- 健康检查：`railway.app/health`
- 聊天：`railway.app/api/chat`

---

## 费用说明

| 服务 | 用量 | 费用 |
|------|------|------|
| Railway Go | <500h/月 | 免费 |
| Railway Redis | 小数据 | 免费 |
| Vercel | <100h/day | 免费 |

OpenAI API key 自备（按量计费）
