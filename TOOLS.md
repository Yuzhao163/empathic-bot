# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

---

## GitHub

- **empathic-bot 仓库**: https://github.com/Yuzhao163/empathic-bot.git
- **backup 仓库**: https://github.com/Yuzhao163/openclaw-backup（私有，用于 OpenClaw 全量备份）
- **Token**: ghp_REDACTED（用于 backup 仓库推送 + 日常操作）

## 备份恢复

- 备份脚本：`~/.openclaw/backup/scripts/backup.sh`
- 恢复脚本：`~/.openclaw/backup/scripts/restore.sh`
- 迁移指南：`~/.openclaw/workspace/MIGRATION.md`
- 备份推送 remote：`origin` 在 `~/.openclaw/backup/backups/.git/`

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.
