# OpenClaw 迁移恢复指南

> 当你换服务器或重装系统时，用这份指南完成无感切换。

---

## 快速迁移步骤

### 1. 在新服务器安装 OpenClaw

```bash
# 安装 OpenClaw
curl -fsSL https://openclaw.ai/install.sh | bash

# 确认版本
openclaw --version
```

### 2. 获取备份

**方式 A：从 GitHub 自动拉取（推荐）**
```bash
export GITHUB_TOKEN="ghp_你的token"
cd ~/.openclaw/backup/backups

# 初始化 git（如果还没有）
git init
git remote add origin "https://x-access-token:${GITHUB_TOKEN}@github.com/Yuzhao163/openclaw-backup.git"
git fetch origin master

# 列出可用备份
git branch -a
ls

# 拉取最新备份
git pull origin master

# 列出所有备份
./restore.sh
```

**方式 B：手动下载备份文件**
```bash
# 从 GitHub Web 下载最新备份的 workspace.tar.gz 和其他文件
# 然后放到 ~/.openclaw/backup/backups/日期/ 目录
```

### 3. 执行还原

```bash
cd ~/.openclaw/backup/scripts
chmod +x restore.sh

# 列出所有备份
./restore.sh

# 还原最新备份（替换日期）
./restore.sh 2026-04-29_10-00
```

### 4. 补全敏感配置

config.json 里的敏感字段已脱敏，还原后需要手动补全：

```bash
vi ~/.openclaw/openclaw.json
```

需要手动填写的字段：
- `channels.feishu.appSecret`（飞书 App Secret）
- `channels.feishu.verificationToken`
- `channels.feishu.encryptKey`
- `models.providers.dashscope.apiKey`（如果用了阿里云模型）
- GitHub Token（用于备份推送）：
  ```bash
  # 更新备份仓库 token
  cd ~/.openclaw/backup/backups
  git remote set-url origin "https://x-access-token:新TOKEN@github.com/Yuzhao163/openclaw-backup.git"
  ```

### 5. 重启服务

```bash
# 重启 OpenClaw gateway
openclaw gateway restart

# 检查状态
openclaw status
openclaw channels status

# 检查飞书连接
openclaw channels info feishu
```

### 6. 验证 claude-mem

```bash
# 检查 worker 是否运行
curl -s http://localhost:37777/api/health 2>/dev/null | python3 -m json.tool

# 验证数据库
ls -la ~/.claude-mem/claude-mem.db
```

---

## 备份内容清单

| 内容 | 文件 | 迁移后需要检查 |
|------|------|---------------|
| 工作区（含 memory） | `workspace.tar.gz` + `memory.tar.gz` | ✅ 直接可用 |
| 飞书等 channel 配置 | `config.json.gz` | ⚠️ 需补全敏感字段 |
| claude-mem 向量记忆 | `claude-mem.db.gz` | ✅ 直接可用 |
| Chroma 向量库 | `corpora.tar.gz` | ✅ 直接可用 |
| 扩展插件 | `extensions.tar.gz` | ⚠️ 可能需重新安装依赖 |
| 自定义 skills | `skills.tar.gz` | ✅ 直接可用 |
| crontab 定时任务 | `crontab.txt` | ⚠️ 需确认路径一致性 |

---

## 迁移检查清单

- [ ] OpenClaw 版本一致（当前：2026.4.11）
- [ ] Node.js ≥18
- [ ] Bun 已安装（claude-mem worker 需要）
- [ ] 飞书 App 配置完整（AppID / AppSecret / webhook）
- [ ] GitHub Token 更新为新 token
- [ ] crontab 定时备份已恢复
- [ ] 飞书 WebSocket 连接正常
- [ ] claude-mem worker 启动正常（port 37777）
- [ ] 备份推送验证成功

---

## 常见问题

**Q: 飞书 channel 连接失败？**
```bash
# 检查配置
openclaw channels test feishu

# 重启 webhook
openclaw gateway restart
```

**Q: claude-mem worker 启动不了？**
```bash
# 手动启动 worker
cd ~/.openclaw/backup/scripts
bash -c 'node bun-runner.js worker-service.cjs start'

# 检查日志
tail -100 ~/.claude-mem/logs/worker.log
```

**Q: 备份推送失败？**
```bash
# 测试 GitHub 连接
curl -s --max-time 10 -o /dev/null -w "%{http_code}" \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/Yuzhao163/openclaw-backup

# 检查 remote URL
cd ~/.openclaw/backup/backups && git remote -v
```

**Q: 想在新服务器完全重新开始，只保留 memory？**
```bash
# 还原时跳过 config.json.gz
# 只恢复 workspace.tar.gz 和 memory.tar.gz
```

---

## 定期验证备份有效性

每月至少一次在新服务器测试还原流程，确保备份可用：

```bash
# 在测试环境还原备份
./restore.sh 2026-04-29_10-00

# 验证 claude-mem 记忆是否完整
curl -s http://localhost:37777/api/observations/recent?limit=5
```
