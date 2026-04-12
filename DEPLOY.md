# 部署指南

## 第一步：GitHub Fork 仓库

> 仓库已经是公开的，直接在 GitHub 页面上操作，无需 token

1. 打开 https://github.com/Yuzhao163/empathic-bot
2. 点 **Fork** → 创建你个人的副本
3. 你的新仓库地址会是 `https://github.com/Yuzhao163/empathic-bot`（变为你用户名）

---

## 第二步：Railway 部署后端

### 2.1 关联 GitHub 仓库

1. 打开 [Railway](https://railway.app)
2. **Login with GitHub**（不需要 PAT，用 OAuth）
3. **New Project → Deploy from GitHub repo** → 选择 `empathic-bot`
4. Railway 会自动检测 Go + Docker 类型

### 2.2 添加 Redis

Railway 面板 → **New Plugin → Redis** → 点一下自动注入 `REDIS_URL`

### 2.3 设置环境变量

Project Settings → Variables：
- `OPENAI_API_KEY` = `sk-xxx`
- `LLM_MODEL` = `gpt-4o`
- `REDIS_URL` = 自动从 Redis 插件注入

### 2.4 记录 Gateway 地址

部署完成后，Railway 给一个 URL，例如 `https://empathic-bot.up.railway.app`
复制这个地址，后面填入 Vercel 环境变量。

---

## 第三步：Vercel 部署前端

### 3.1 创建 Vercel 项目

1. 打开 [vercel.com](https://vercel.com)
2. **Add New → Project**
3. **Import Git Repository** → 选择你的 `empathic-bot` 仓库
4. Framework: **Vite**
5. Root Directory: `frontend`
6. Build Command: `npm run build`
7. Output Directory: `dist`

### 3.2 设置环境变量

Environment Variables：
- `VITE_GATEWAY_URL` = `https://xxx.railway.app`（Railway 给的地址，不带引号）

### 3.3 Deploy

点 **Deploy**，等待 2 分钟。

---

## 验证

- 前端：`vercel.app 域名`
- 后端健康：`railway.app/health`
- 聊天：`railway.app/api/chat`（POST JSON）
