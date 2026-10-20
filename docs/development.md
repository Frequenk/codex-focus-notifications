# 开发与构建

本文面向修改源码或从源码构建的开发者。安装和使用项目请先阅读 [README](../README.md)；让 agent 安装现成发布包请使用 [INSTALL.md](../INSTALL.md)。

## 环境

需要 Node.js ≥22、Python ≥3.9。以下命令均在项目根目录执行。构建工具和安装依赖已有锁定版本，运行通知脚本本身只依赖 Python 标准库。

## 安装依赖

```sh
npm ci --ignore-scripts
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements-build.txt
```

## 检查与构建

```sh
npm run check
.venv/bin/python checks/install-smoke.py
node checks/exit-smoke.cjs
npm run package
.venv/bin/python scripts/bundle.py
.venv/bin/python checks/package-smoke.py
```

这些命令检查语法与公开内容，在隔离环境验证配置生命周期和退出清理，然后生成并检查发布包。不会安装到日常使用的 Codex 或 VS Code 环境，也不调用真实模型。

产物位于忽略的 `dist/` 目录：

| 文件 | 用途 |
| --- | --- |
| `codex-focus-notifications-VERSION.vsix` | VS Code 扩展包 |
| `codex-focus-notifications-VERSION-agent.tar.gz` | 包含安装脚本及依赖的 agent 工具包 |
| `SHA256SUMS` | 两份发布包的 SHA-256 校验和 |

需要从源码安装时，将同一版本的 VSIX 路径传给安装工具，后续步骤遵循 [agent 安装指南](../INSTALL.md#3-预览并安装)。仅构建不会更改当前安装。

## 桌面验收与发布

CI 执行相同的源码检查、隔离流程验收与构建。真实 macOS 通知、系统权限和鼠标点击需按[验收指南](verification.md)检查，隔离检查不能替代桌面验证。

推送 main 后，GitHub Actions 自动递增补丁版本并发布 GitHub Release；PR 只检查和构建。自动版本仅写入 CI 工作目录，不产生版本提交。版本规则、权限与维护步骤见[发布指南](releasing.md)。贡献约定见 [CONTRIBUTING.md](../CONTRIBUTING.md)。
