# CLI 入口与定时调度：python -m pipeline run + cron/systemd 配置

| 字段 | 值 |
|------|-----|
| 类型 | AFK |
| 标签 | needs-triage |
| 阻塞 | #5 容错与重试策略 |

## Parent

`specs/agents-prd.md`

## What to build

提供 CLI 入口 `python -m pipeline run` 执行全管线，支持 `--dry-run` 预览模式。配置每日 UTC 0:00 定时触发，提供 cron 和 systemd timer 两种配置模板。

端到端行为：用户执行 `python -m pipeline run` → 全管线执行 → 输出结果摘要 / 或 `python -m pipeline run --dry-run` → 仅输出预览不写文件。

## Acceptance criteria

- [ ] `python -m pipeline run` 执行完整三阶段管线
- [ ] `python -m pipeline run --dry-run` 预览模式：执行但不写入任何文件
- [ ] 提供 cron 配置模板（crontab 格式），每日 UTC 0:00 触发
- [ ] 提供 systemd timer 配置模板（.service + .timer 文件）
- [ ] 调度配置中正确激活虚拟环境（source .venv/bin/activate）
- [ ] CLI 退出码遵守约定：0=成功，1=部分失败，2=完全失败
- [ ] 支持 `--log-level` 参数切换日志级别

## Blocked by

- #5 容错与重试策略
