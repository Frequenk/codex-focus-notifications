# Codex Focus Notifications

[English](README.en.md)

**为 VS Code 终端中的 Codex CLI 添加 macOS 系统通知。**

任务完成或需要回答时提醒你，返回会话后自动清除，点击通知定位对应终端。适合把 Codex 留在后台工作，同时处理其他事情。

## 使用体验

| 场景 | 表现 |
| --- | --- |
| 后台任务完成 | 显示项目、会话名称、耗时和完成时间 |
| Codex 需要你回答 | 显示待回答的问题数量，如 `1 question` |
| 正在查看会话 | 不弹出该会话的新通知 |
| 返回对应会话 | 自动清除它已有的通知，其他会话不受影响 |
| 点击通知 | 返回原 VS Code 窗口和终端，满足条件时自动切回目标会话 |
| 正常退出 Codex 或关闭终端 | 清理该终端已识别会话的通知；同会话还有其他终端打开时保留 |

完成通知示例：

```text
my-project · 优化登录流程
Worked for 42s • 16:38
```

通知默认无声，按会话分别管理。耗时取自对应回合记录；无法取得时显示 `Finished • HH:mm`。

## 由什么组成，会改动什么

安装包含三个部分：

| 组成 | 负责什么 | 安装改动 |
| --- | --- | --- |
| **VS Code 扩展** | 识别当前会话，管理静默、清理和点击跳转 | 安装一个 VSIX 扩展包 |
| **Codex 事件脚本（Python）** | 接收完成、待回答事件，生成通知内容 | 在 `~/.codex` 下安装脚本，配置完成回调和一个待输入 hook |
| **macOS 通知工具（terminal-notifier）** | 发送系统通知，接收通知点击 | 通过 Homebrew 安装工具，并在 `~/Applications` 创建独立通知 App |

**hook** 是事件发生时自动执行脚本的入口；**Homebrew** 是 macOS 软件包管理器，这里用它安装 terminal-notifier。通知清理由 VS Code 扩展负责。

安装还会设置用于识别会话的终端标题，以及打开会话列表的 **F12** 快捷键。改动前自动备份，保留原有通知回调和其他 hooks，并支持卸载恢复。集成配合原版 Codex CLI 运行；Codex 数据目录可通过 `CODEX_HOME` 自定义。

## 安装

适用于 **macOS 本机的 VS Code 集成终端**，需要 VS Code ≥1.100、已安装的 Codex CLI、Python ≥3.9 和 terminal-notifier 3.x。安装时可通过已有 Homebrew 补齐常规依赖。

把下面这段话交给有本机操作能力的 agent，它会安装并配置上述全部组件：

> 请阅读 https://github.com/Frequenk/codex-focus-notifications/blob/main/INSTALL.md ，为我安装 Codex Focus Notifications。允许通过已有 Homebrew 补齐依赖，保留我的其他配置，完成后检查安装结果。

安装后重载 VS Code，并在方便时重新启动对应 Codex 会话；首次使用可能需要按提示信任 hook、允许 macOS 通知。[安装、升级与卸载说明 →](INSTALL.md)

## 使用须知

- **前台如何判断**：聚焦的 VS Code 窗口与选中的终端共同决定当前会话；在同窗口编辑代码时，这个终端仍算前台。需保持终端 shell integration（命令跟踪）启用。
- **点击跳转有条件**：自动切回会话目前限定 Codex **0.163.0**。目标仍在运行（包括部分待回答状态）、重名或界面识别失败时，只定位终端，需手动选择。详见[点击流程与限制](docs/architecture.md#点击流程)。
- **持续显示由系统控制**：在 macOS「系统设置 → 通知 → Codex Focus Notifications」选择“提醒”，通知可保留到处理或清理，系统仍可能将其分组或收起。
- **异常退出可能留有通知**：强杀、崩溃或整个应用退出时，扩展可能收不到终端事件，残留通知需手动关闭。远程 VS Code 窗口不在支持范围内。

会话信息仅在本机处理，无遥测或会话上传。诊断日志可能包含会话标识，提交反馈前请脱敏。

## 文档与许可

[故障排查](docs/troubleshooting.md) · [工作原理](docs/architecture.md) · [开发与构建](docs/development.md) · [发布指南](docs/releasing.md) · [贡献指南](CONTRIBUTING.md)

MIT © 2026 **frequenk** · [第三方许可](THIRD_PARTY_NOTICES.md)。本项目由社区维护，与 OpenAI 和 Microsoft 无隶属关系。
