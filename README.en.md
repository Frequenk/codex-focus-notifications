# Codex Focus Notifications

[中文](README.md)

**macOS system notifications for Codex CLI running in VS Code terminals.**

Get notified when work finishes or Codex needs an answer. Return to a session to clear its notifications, or click one to find its terminal. Let Codex work in the background while you do something else.

## What it does

| Situation | Behavior |
| --- | --- |
| A background task finishes | Shows the project, session name, duration and completion time |
| Codex needs an answer | Shows the number of questions and time, such as `1 question • 16:38:09` |
| You are viewing a session | Suppresses new notifications for that session |
| You return to a session | Clears its existing notifications, leaving other sessions alone |
| You click a notification | Focuses the original VS Code window and terminal; switches to the target session when supported |
| You exit Codex normally or close a terminal | Clears notifications for sessions identified in that terminal, unless another terminal still has the same session open |

Example completion notification:

```text
my-project · Improve login flow
Worked for 42s • 16:38:09
```

Completion and question notifications use “project · session name” as the title. Missing parts are omitted; when neither is available, the title is `Codex`. All notification messages end with local time in 24-hour `HH:mm:ss` format.

| Situation | Example message | Where it appears |
| --- | --- | --- |
| Task finishes with duration available | `Worked for 42s • 16:38:09` | macOS system notification |
| Task finishes without duration | `Finished • 16:38:09` | macOS system notification |
| Answer needed with question count available | `1 question • 16:38:09` / `3 questions • 16:38:09` | macOS system notification |
| Answer needed without a question count | `Input required • 16:38:09` | macOS system notification |
| Original terminal unavailable after clicking | `Original terminal is unavailable • 16:38:09` (title: `Codex`) | macOS system notification |
| Automatic session switching does not complete | `已定位原终端，但未能自动切回目标会话。已停止按键操作，请手动选择该会话。 • 16:38:09` | VS Code message (currently in Chinese) |

Notifications are silent by default and managed separately for each session. Durations may also read `2m 5s` or `1h 2m 5s`. The time is the recorded turn completion time when available; otherwise, it is the time the notification is generated.

## Components and installation changes

The integration has three parts:

| Component | Responsibility | What gets installed or configured |
| --- | --- | --- |
| **VS Code extension** | Identifies the current session; handles suppression, cleanup and click navigation | One VSIX extension package |
| **Codex event script (Python)** | Receives completion and question events; prepares notification content | A script under `~/.codex`, a completion callback and one input hook |
| **macOS notification tool (terminal-notifier)** | Sends system notifications and receives clicks | The tool via Homebrew, plus a separate notification app under `~/Applications` |

A **hook** runs a script when an event occurs. **Homebrew** is a macOS package manager, used here to install terminal-notifier. The VS Code extension handles notification cleanup.

Installation also configures the terminal title for session identification and **F12** to open the session list. Changes are backed up, existing notification callbacks and unrelated hooks are preserved, and uninstall can restore managed settings. It uses the original Codex CLI. Set `CODEX_HOME` to use a custom Codex data directory.

## Install

For **local VS Code terminals on macOS**. Requires VS Code 1.100+, an existing Codex CLI installation, Python 3.9+ and terminal-notifier 3.x. Ordinary missing dependencies can be installed using an existing Homebrew installation.

Give this prompt to an agent with local computer access. It will install and configure all three components:

> Read https://github.com/Frequenk/codex-focus-notifications/blob/main/INSTALL.md and install Codex Focus Notifications for me. You may use my existing Homebrew to install missing dependencies. Preserve my other settings and verify the installation when finished.

After installation, reload VS Code and restart the relevant Codex session when convenient. First use may require trusting the hook and allowing macOS notifications. [Installation, upgrades and uninstall →](INSTALL.md)

## Things to know

- **Foreground detection:** the focused VS Code window and its selected terminal determine the current session. Editing a file in that same window still counts as foreground. Keep terminal shell integration enabled.
- **Click navigation has limits:** automatic session switching currently targets Codex **0.163.0**. Active sessions, including some waiting for answers, duplicate names or unrecognized layouts stop at terminal focus; select the session manually. See [navigation details](docs/architecture.md#点击流程).
- **macOS controls persistence:** choose **Alerts** in System Settings → Notifications → Codex Focus Notifications to keep notifications until handled or cleared. The system may still group or collapse them.
- **Abnormal exits can leave notifications:** crashes, forced termination or application shutdown may bypass terminal events. Dismiss remaining notifications manually. Remote VS Code windows are outside the supported scope.

Session information stays on your machine. There is no telemetry or session upload. Diagnostic logs may contain session identifiers; redact them before sharing.

## Documentation and license

[Troubleshooting](docs/troubleshooting.md) · [Architecture](docs/architecture.md) · [Development and builds](docs/development.md) · [Releases](docs/releasing.md) · [Contributing](CONTRIBUTING.md)

MIT © 2026 **frequenk** · [Third-party notices](THIRD_PARTY_NOTICES.md). A community project, unaffiliated with OpenAI or Microsoft.
