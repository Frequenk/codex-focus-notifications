# 故障排查

1. 运行 `python3 scripts/manage.py doctor --json`，确认运行文件和可执行路径；自定义目录加 `--codex-home`。
2. 在 VS Code 命令面板运行 `Codex Notifications: Show Status`，检查当前会话识别、焦点和点击结果。
3. 确认已经重载扩展，并在方便时重启原 TUI。扩展无法追溯启动前已经错过的输出流；不要强行终止任务。
4. 确认 `terminal.integrated.shellIntegration.enabled` 为 true，标题配置未被覆盖，未手动重命名终端而屏蔽标题。
5. 只有待输入通知缺失时，检查 Codex 是否已信任本项目 `PreToolUse: request_user_input` hook。不要自行伪造 trusted_hash。
6. 系统设置 → 通知 → Codex Focus Notifications：允许通知，检查专注模式和提醒样式。选择“提醒”可持续显示，声音可关闭。首次授权可能要用户操作。
7. 点击只定位终端时，检查目标是否 active、是否重名、详情面板是否过窄，或 Codex 是否不是 0.163.0。日志会记录停止原因；不要通过盲目重试回车绕过。
8. 正常退出无清理时，检查 shell integration 的命令结束事件与终端映射；崩溃、强杀和整个应用退出不保证收到事件。
9. 卸载报告冲突时，检查本机备份与受管字段的当前值，手工合并后再运行，不强制覆盖新配置。

日志可能含会话 ID、项目名和本机路径。公开 issue 前请脱敏；不要上传完整 config.toml、hooks.json、会话记录或 runtime.json。
