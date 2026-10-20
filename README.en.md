# Codex Focus Notifications

[中文](README.md) · [Agent installation guide](INSTALL.md)

A community macOS notification integration for Codex CLI running inside local VS Code terminals. Maintained by **frequenk**, unaffiliated with OpenAI or Microsoft. No custom Codex build is needed.

## Ask your agent to install

> Read https://github.com/Frequenk/codex-focus-notifications/blob/main/INSTALL.md and install the complete integration on my Mac. You may install ordinary dependencies using my existing Homebrew. Preserve other settings, callbacks and hooks, verify the installation, and report any system permissions or reloads I need to handle.

The agent downloads a matching VSIX and installation toolkit from GitHub Releases, verifies SHA-256, backs up existing files and configures the entire integration. No Marketplace account or manually entered installation sequence is required.

## Experience

- Completion: `Worked for 42s • 16:38`, using the matching turn's recorded duration, or `Finished • HH:mm` when unavailable.
- Questions: `1 question`, `2 questions`, etc.
- Titles use project and session names. Notifications are silent and grouped by session.
- Returning to the focused VS Code window and selected terminal clears that session's notifications and suppresses new ones.
- Normal TUI exit or terminal closure clears known sessions, including background terminals, unless another live terminal still owns the session.
- Clicking a notification focuses its original window and terminal, then switches to the target session when the guarded navigation is supported.

Only completion `notify` and `PreToolUse: request_user_input` generate notifications. The extension owns all cleanup; four historical cleanup hooks are migrated away without removing unrelated hooks. Existing completion callbacks continue to run.

## Compatibility and limits

Local macOS only. Python 3.9+, VS Code CLI, Codex CLI and terminal-notifier 3.x are required. VS Code shell integration must remain enabled. VS Code 1.141.2 and Codex CLI 0.163.0 have been exercised; the extension requires VS Code 1.100+.

Automatic session switching is pinned to Codex 0.163.0, local Unix transport, a unique visible session name and the standard English command center. Active sessions (including some input-waiting sessions), duplicate names, narrow layouts and unknown versions stop at terminal focus. Drafts are preserved and no messages are submitted.

Restart an existing TUI after reloading the extension so its output can be observed. Reloading is not an exit. Crashes, forced termination or application shutdown may bypass terminal cleanup events; stale state expires and normal notifications resume. Remote windows are not supported for focus/click integration.

macOS controls notification permissions and duration. Select **Alerts** for persistent presentation; the installer does not edit the system notification database. An original icon is supplied, with an optional local PNG override.

## Privacy, build and release

No telemetry or session upload. Local indexes, read-only databases and matching transcript tails supply identity and timing. Temporary screen projection is kept only in memory during navigation. Diagnostic logs can contain session IDs; redact them before sharing.

See the [Chinese README](README.md) for exact build commands, [release guide](docs/releasing.md), [verification guide](docs/verification.md) and [architecture](docs/architecture.md). Tag pushes matching package.json publish VSIX, agent toolkit and checksums to GitHub Releases; no Marketplace publication occurs.

The installer supports dry runs, idempotent upgrades, conflict-aware uninstall and optional legacy extension restoration. It does not reload or terminate your current sessions. MIT © 2026 frequenk. See [third-party notices](THIRD_PARTY_NOTICES.md).
