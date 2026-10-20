# 构建与发布

## 首次准备

将目录创建为自己的 Git 仓库并推送到 GitHub。默认文档链接指向 `Frequenk/codex-focus-notifications`；如果使用其他仓库，修改 package.json 的 repository、homepage、bugs 和安装文档链接。工作流使用 github.repository，不写死仓库令牌或仓库名称。

GitHub Actions 默认读权限；仅 release job 请求 `contents: write`。无需配置个人令牌或 Marketplace 凭据，若组织策略禁止写 Release，需要仓库管理员放开对应权限。

## 日常发布

1. 手动调整 package.json 的 SemVer 版本，运行 npm install --package-lock-only --ignore-scripts 同步锁文件，更新 CHANGELOG。
2. 按[开发与构建指南](development.md)执行完整本地检查和打包流程，再按[验收指南](verification.md)验证桌面行为。
3. 由维护者自行提交、推送代码，并创建和推送与包版本一致的 `vVERSION` 标签。
4. Actions 校验、构建并发布 GitHub Release。包含连字符的预发布版本标记为 prerelease，agent 默认不安装它。
5. 检查附件与 SHA256SUMS，通过 agent 指南在隔离环境安装一次。

工作流不会自动修改版本、提交、推送或创建标签。已存在 Release 时拒绝覆盖，修复后使用新版本。GitHub 自动附带源码归档，项目额外发布 VSIX 和携带安装依赖的 agent 工具包。

## 本地与远程证据

本地打包成功只证明本机命令通过；仓库尚未推送时不能声称 Actions 已执行或 Release 已上线。无桌面 CI 使用隔离配置与模拟通知程序，不能替代真实 macOS 通知授权、持续样式和鼠标点击验收。
