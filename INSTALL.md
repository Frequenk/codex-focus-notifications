# Agent 安装指南

本文面向具备本机终端权限的 agent。用户要求安装本项目，即可执行下述安装步骤，不必让用户逐条手动执行。只在确实需要管理员权限、安装 Homebrew 本身、系统授权或配置冲突时请求用户处理；不要自动关闭任务或绕过安全授权。

## 1. 检查本机

只支持本地 macOS。检查 Python ≥3.9、`codex --version`、VS Code CLI `code`、`brew` 和 `terminal-notifier`。VS Code CLI 未在 PATH 时，可使用应用内 `Contents/Resources/app/bin/code` 的绝对路径，通过 `--code-bin` 传入。

允许通过已有 Homebrew 安装缺失的 Python 和 terminal-notifier；不自动升级已有 Codex，不安装另一个 Codex，不重新编译 CLI。缺少 Homebrew 时停止并报告，不运行未经查看的远程 shell 引导脚本。VS Code 与 Codex 未安装时报告前置条件。

完整自动切换已验证 Codex 0.163.0；其他版本保留明确降级，不以安装旧版本掩盖兼容问题。

## 2. 获取同版本发布包

从 `Frequenk/codex-focus-notifications` 的最新稳定 GitHub Release 获取实际标签，随后所有下载固定到这个标签。忽略预发布版本，除非用户明确选择。

下载三个文件到临时目录：

- `codex-focus-notifications-VERSION.vsix`
- `codex-focus-notifications-VERSION-agent.tar.gz`
- `SHA256SUMS`

可用 GitHub CLI `gh release view`、`gh release download`，也可使用 GitHub Releases API 和 HTTPS 下载。无需登录即可下载公开附件。下载后运行 `shasum -a 256 -c SHA256SUMS`，失败即停止。校验和用于检测下载损坏与附件不一致，不等同于代码签名。

解压前检查归档路径：不允许绝对路径、`..` 越界或符号链接。解压到临时目录。工具包自带锁定的 TOML 编辑依赖，不需要用户安装 Python 包。检查安装源码后再执行，固定到已校验版本，不使用 `curl | sh`。

若仓库还没有 Release，使用 README 的开发构建步骤产生相同三份文件；不要声称已从 GitHub 发布。

## 3. 预览并安装

进入解压后的工具包目录，运行以下命令；替换 VSIX 路径为同版本下载文件的绝对路径：

```sh
python3 scripts/manage.py doctor --json
python3 scripts/manage.py install --vsix /absolute/path/package.vsix --dry-run --json
python3 scripts/manage.py install --vsix /absolute/path/package.vsix --install-dependencies --apply --json
python3 scripts/manage.py doctor --json
```

安装工具不依赖交互式确认。预览没有冲突且在用户授权的安装范围内时继续应用，不要求用户再次批准每个配置项。

支持 `--codex-home`、`--codex-bin`、`--code-bin`、`--notifier-bin` 与 `--icon /path/icon.png`。自定义 CODEX_HOME 会记录为默认安装位置；显式 VS Code `codexFocus.codexHome` 设置和环境变量仍优先。

安装会：

1. 备份相关文件和已有同名扩展到用户私有目录。
2. 创建独立通知 App，使用原创图标和本机签名，不复制到公开仓库。
3. 安装 VSIX 和通用通知脚本，保存原有完成回调并继续转发。
4. 增量设置终端标题与 F12，保留其他配置和快捷键。
5. 仅注册 `PreToolUse: request_user_input`；识别并移除本项目旧版四个清理 hooks。
6. 发现旧 publisher 的同名本地扩展时，先备份再迁移，避免双重处理。

不伪造或预写 Codex hook 信任记录。下次启动时如 Codex 要求信任新增 hook，向用户说明准确内容和作用，按正常信任流程处理。macOS 如提示通知授权，同样交由用户决定。

## 4. 激活与验收

告知用户在方便时执行 `Developer: Reload Window` 并重新启动对应 TUI。不要中断正在运行的会话。命令面板 `Codex Notifications: Show Status` 可查看识别状态。

窗口重载后，在后台触发一条新完成通知；确认标题、耗时、无声、返回清理和点击定位，再触发问题通知检查数量。退出当前/后台 TUI 后确认通知清理。旧通知不能自动补上新版本点击动作。

需要持续显示时，在系统设置 → 通知 → Codex Focus Notifications 中选择“提醒”并关闭声音。安装工具本身不发声音，也不改写系统通知数据库。

安装成功但尚未重载或尚未授权时，明确报告“已安装，待激活/授权”，不要声称端到端已验证。

## 5. 升级与卸载

升级使用新版本的同一安装流程，备份继续保留，重复安装不重复注册 hooks。

```sh
python3 scripts/manage.py uninstall --dry-run --json
python3 scripts/manage.py uninstall --apply --json
```

需要恢复之前的本地扩展时，增加 `--restore-legacy`。卸载只恢复本项目管理的字段、移除自身 hook，并保留其他配置；发现用户修改受管字段或运行文件时停止并返回冲突。不要强行覆盖。

备份、诊断记录都在本机。卸载保留备份与通知 App，避免破坏回滚及系统通知历史；用户确认不再需要时可自行删除，不做自动清空主目录的操作。
