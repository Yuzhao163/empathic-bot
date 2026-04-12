# 部署指南

## 第一步：Fork 仓库

1. 打开 https://github.com/Yuzhao163/empathic-bot
2. 点 **Fork** → 创建你的个人副本

---

## 第二步：Railway 部署后端

### 2.1 关联 GitHub

1. 打开 [Railway](https://railway.app) → Login with GitHub
2. **New Project → Deploy from GitHub repo** → 选择 `empathic-bot`

> 注意：Railway 会优先使用 `Dockerfile`，我们的 Gateway 和 Python Service 都有 Dockerfile，会自动构建。

### 2.2 添加 Redis

Railway 面板 → **New Plugin → Redis** → 自动注入 `REDIS_URL`

### 2.3 设置环境变量

Project Settings → Variables：

| 变量 | 值 |
|------|-----|
| `MINIMAX_API_KEY` | 你的 MiniMax API Key |
| `MINIMAX_BASE_URL` | `https://api.minimaxi.com/v1` |
| `LLM_MODEL` | `MiniMax-M2.7` |
| `ALLOWED_ORIGINS` | 你的 Vercel 域名（如 `https://empathic-bot.vercel.app`）|

### 2.4 记录后端地址

Railway 部署完成后给出 URL，例如 `https://empathic-bot.up.railway.app`
这个地址后面填入 Vercel 环境变量。

---

## 第三步：Vercel 部署前端

### 3.1 创建项目

1. 打开 [vercel.com](https://vercel.com) → **Add New → Project**
2. Import 你的 `empathic-bot` 仓库
3. **Root Directory**: `frontend`
4. **Framework Preset**: `Vite`
5. **Build Command**: `npm run build`（已预配置）
6. **Output Directory**: `dist`（已预配置）

### 3.2 设置环境变量

| 变量 | 值 |
|------|-----|
| `VITE_GATEWAY_URL` | Railway 给的后端地址（如 `https://empathic-bot.up.railway.app`）|

### 3.3 Deploy

点 **Deploy**，约 2 分钟完成。

---

## 验证

- 前端：`https://your-project.vercel.app`
- 后端健康：`https://xxx.railway.app/health`
- 流式聊天：`POST https://xxx.railway.app/api/chat/stream`

---

## 架构说明

```
Vercel（前端） → Railway（Gateway + Python + Redis）
```

前端 JS 直接调用 Railway 后端 API，无需额外代理。
