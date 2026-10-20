# Codex Focus Notifications

[English](README.en.md) · [Agent 安装指南](INSTALL.md) · [工作原理](docs/architecture.md) · [故障排查](docs/troubleshooting.md)

让 macOS 上的 Codex CLI 与 VS Code 通知形成一条完整的使用流程：后台完成或需要回答时提醒，回到对应会话后自动清除；点击通知定位原窗口、终端与会话。

这是 frequenk 维护的社区项目，与 OpenAI 和 Microsoft 无隶属关系。**不需要修改或重新构建 Codex CLI。**

## 让你的 agent 安装

把下面这段话交给有本机终端操作能力的 agent：

> 请读取 https://github.com/Frequenk/codex-focus-notifications/blob/main/INSTALL.md ，按照其中的 agent 安装流程为我安装完整的 Codex 通知集成。允许通过已有 Homebrew 补齐常规依赖。保留我的其他配置和 hooks，完成安装、诊断并说明需要我处理的系统授权。

agent 将下载同版本 GitHub Release 中的扩展和安装工具，验证校验和，备份并配置完成回调、待输入 hook、VS Code 扩展和独立通知 App。用户无需逐条执行命令。仓库尚无 Release 时请使用安装指南中的本地构建流程。

## 通知如何工作

- **完成**：显示 `Worked for 42s • 16:38`，使用对应回合记录的耗时；取不到时显示 `Finished • HH:mm`。
- **待输入**：显示 `1 question`、`2 questions` 等问题数量。
- **内容**：标题为 `项目 · 会话名称`，不展示会话 ID，默认无声。
- **返回会话**：聚焦 VS Code 窗口并选中对应终端后，清除已有通知，抑制新通知。焦点位于同窗口编辑器时，选中终端仍算前台。
- **退出**：正常退出 TUI 或关闭当前/后台终端，清理此 TUI 已识别会话的通知；同会话还有其他存活终端时保留。
- **点击**：先定位原 VS Code 窗口和终端；支持时打开会话总览并切回目标，不提交消息、不丢弃草稿。

完成通知使用 Codex `notify` 回调；问题通知只注册 `PreToolUse: request_user_input`。**清理完全由扩展负责**，不再注册 `PostToolUse`、`UserPromptSubmit`、`SessionStart`、`SessionEnd` 清理 hooks。安装工具只迁移本项目旧 hooks，保留其他 hooks 和原有完成回调。

## 支持范围

- 本地 macOS、VS Code 稳定版，需保持终端 shell integration 启用。扩展声明 VS Code ≥1.100；已实际验证 1.141.2。
- 已实际验证 Codex CLI **0.163.0**。其他版本不强制升降级；自动跨会话切换会停止，仅保留能够识别的通知与定位能力。
- 自动切换要求本地 Unix 服务、唯一且能完整显示的会话名，以及标准英文会话总览。目标为 active（含部分待输入状态）、重名或界面核对失败时提示手动选择。
- 扩展必须观察过会话标题，才知道它属于哪个终端；重载后需在方便时重启 TUI。远程窗口不提供焦点静默与点击集成。
- 窗口重载不视为退出。强杀、崩溃或整个应用退出时可能收不到终端事件，残留通知可手动关闭；状态过期后不再抑制通知。
- macOS 首次通知授权、横幅/提醒样式由系统控制。选择“提醒”可让通知保留到处理或清理，没有固定秒数；系统仍可能分组或收起通知。

## 隐私与依赖

不上传会话或遥测。仅在本机读取会话索引、只读数据库和对应回合记录尾部，以获取名称、ID 和耗时。点击期间短暂处理终端界面，不写出聊天文本。诊断日志包含会话 ID 和结果，提交 issue 前请脱敏。

依赖 Python ≥3.9、Codex CLI、VS Code CLI、Homebrew `terminal-notifier` 3.x。安装工具为通知工具创建独立 App 和原创图标；不会替换 Homebrew 原 App。可用 `--icon` 指定本机 PNG 图标，但官方品牌图标不随本项目分发。

## 开发与构建

需要 Node.js ≥22、Python ≥3.9：

```sh
npm ci --ignore-scripts
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements-build.txt
npm run check
.venv/bin/python checks/install-smoke.py
node checks/exit-smoke.cjs
npm run package
.venv/bin/python scripts/bundle.py
.venv/bin/python checks/package-smoke.py
```

输出位于忽略的 `dist/`。CI 执行相同的构建与隔离检查。桌面端通知及真实点击仍需按[验收指南](docs/verification.md)检查，不调用真实模型。

## 发布与恢复

推送与 `package.json` 版本一致的 `v*` 标签，GitHub Actions 自动构建并发布 VSIX、agent 安装工具包和 SHA-256。仅发布到 GitHub Releases，无需 Marketplace 凭据。详见[发布指南](docs/releasing.md)。

安装管理支持预览、重复安装、诊断和卸载；恢复旧扩展使用 `uninstall --restore-legacy --apply`。遇到后续用户改动会停止覆盖，备份保留在本机，详见 [INSTALL.md](INSTALL.md)。

MIT © 2026 frequenk。第三方许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
