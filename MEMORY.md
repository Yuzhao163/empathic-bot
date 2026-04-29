# MEMORY.md - Long-term Memory

## 关于我

- 运行在阿里云 ECS（iZ2ze2k1jugg7ft7culj5Z），OpenClaw 2026.4.11
- 主要渠道：飞书（WebSocket 模式）
- 默认模型：minimax-portal/MiniMax-M2.7
- 备份仓库：https://github.com/Yuzhao163/openclaw-backup（私有）

## 关于用户

- 使用飞书与我对话
- **偏好：发文档/链接时一定要带链接**，不要只说"已更新"
- 时区：Asia/Shanghai（GMT+8）

## 重要配置

- 飞书 App：cli_a920865b2e79dbd7，webhook port 3000
- 微信插件已安装（openclaw-weixin），但 channel 显示不稳定
- GitHub Token（用于备份推送）：ghp_REDACTED

## 定时任务

- 每日 10/12/14/16/18/22 点执行 `~/.openclaw/backup/scripts/backup.sh`
- 备份推送到 Yuzhao163/openclaw-backup

## 重要文件路径

- 工作区：`~/.openclaw/workspace/`
- 备份脚本：`~/.openclaw/backup/scripts/backup.sh`
- claude-mem 数据库：`~/.claude-mem/claude-mem.db`
- 向量库：`~/.claude-mem/corpora/`

## 已知问题

- 微信 channel 与 OpenClaw 2026.4.11 存在兼容性问题的历史记录
- BOOTSTRAP.md 尚未删除（意味着身份尚未正式建立）

## 技能清单

- find-skills / skillhub-preference（技能发现）
- weather（天气查询）

## 项目记录

- **empathic-bot**：用户有 GitHub 仓库，但早期克隆失败（仓库不存在或 private）
- **飞书 AI 资讯文档**：每早/晚自动更新，链接 https://feishu.cn/docx/EqCndDXkpom0kxxmiOmcYCZenfb
