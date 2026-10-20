"""转发已有 Codex 完成回调，并提供 macOS 通知与本地扩展桥接。"""
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import subprocess
import time
import sys
import uuid

def runtime_config():
    try:
        return json.loads((Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "notification-bridge/runtime.json").read_text())
    except (OSError, ValueError):
        return {}


RUNTIME = runtime_config()
ORIGINAL_CALLBACK = RUNTIME.get("original_callback", [])
NOTIFIER = RUNTIME.get("notifier") or "terminal-notifier"
PYTHON = RUNTIME.get("python") or sys.executable
THREAD_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
TITLE_PREFIX = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{5}\Z")


def codex_home():
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))


def resolve_title_thread(prefix):
    """Resolve Codex's truncated title ID against known local sessions only."""
    if not isinstance(prefix, str) or not (THREAD_ID.fullmatch(prefix)
                                         or TITLE_PREFIX.fullmatch(prefix)):
        return None
    matches = set()
    try:
        with (codex_home() / "session_index.jsonl").open(encoding="utf-8") as index:
            for line in index:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                value = record.get("id") if isinstance(record, dict) else None
                if isinstance(value, str) and THREAD_ID.fullmatch(value) and value.startswith(prefix):
                    matches.add(value)
    except (OSError, UnicodeError):
        pass
    for database in codex_home().glob("state_*.sqlite"):
        try:
            connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=0.2)
            try:
                rows = connection.execute("SELECT id FROM threads WHERE id LIKE ? LIMIT 2",
                                          (prefix + "%",)).fetchall()
            finally:
                connection.close()
            matches.update(row[0] for row in rows
                           if isinstance(row[0], str) and THREAD_ID.fullmatch(row[0]))
        except (sqlite3.Error, OSError, ValueError):
            continue
    return next(iter(matches)) if len(matches) == 1 else None


def is_session_foreground(thread_id, window_id=None):
    if not isinstance(thread_id, str) or not THREAD_ID.fullmatch(thread_id):
        return False
    now = time.time() * 1000
    for path in (codex_home() / "vscode-focus").glob("*.json"):
        try:
            info = path.lstat()
            if path.is_symlink() or info.st_uid != os.getuid() or info.st_size > 8192:
                continue
            state = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                continue
            stamp, pid = state.get("updated_at_ms"), state.get("pid")
            if (state.get("version") != 1 or state.get("focused") is not True
                    or state.get("window_id") != path.stem
                    or (window_id is not None and state.get("window_id") != window_id)
                    or isinstance(stamp, bool) or not isinstance(stamp, (int, float))
                    or not 0 <= now - stamp <= 3000
                    or isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0):
                continue
            os.kill(pid, 0)
            visible = state.get("thread_id")
            if visible is None and isinstance(state.get("thread_prefix"), str):
                prefix = state["thread_prefix"]
                if thread_id.startswith(prefix):
                    visible = resolve_title_thread(prefix)
            if visible != thread_id:
                continue
            return True
        except (OSError, ValueError, OverflowError):
            continue
    return False


def clear_foreground_notification(thread_id, window_id=None, result="focus_clear"):
    if not is_session_foreground(thread_id, window_id):
        return False
    error = run_command([NOTIFIER, "-remove", "codex-" + thread_id], timeout=2)
    if not error:
        remove_click_tickets(thread_id)
    write_clear_log({"hook_event_name": "VSCodeFocus", "source": "vscode",
                     "session_id": thread_id}, "remove_failed" if error else result, error)
    return True


def read_private_json(path, limit=1024 * 1024):
    try:
        info = path.lstat()
        if path.is_symlink() or info.st_uid != os.getuid() or info.st_size > limit:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def write_private_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False)
        temporary.replace(path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def click_routes(thread_id):
    now = time.time() * 1000
    routes = []
    for path in (codex_home() / "vscode-click/windows").glob("*.json"):
        value = read_private_json(path)
        if not value:
            continue
        try:
            if (value.get("version") != 1 or value.get("window_id") != path.stem
                    or not THREAD_ID.fullmatch(path.stem)
                    or not 0 <= now - value["updated_at_ms"] <= 3000
                    or type(value.get("pid")) is not int or value["pid"] <= 0):
                continue
            os.kill(value["pid"], 0)
            for terminal in value.get("terminals", []):
                if (not isinstance(terminal, dict)
                        or not isinstance(terminal.get("terminal_id"), str)
                        or not THREAD_ID.fullmatch(terminal["terminal_id"])
                        ):
                    continue
                if thread_id not in terminal.get("thread_ids", []):
                    prefix = terminal.get("thread_prefix")
                    if (not isinstance(prefix, str) or not thread_id.startswith(prefix)
                            or resolve_title_thread(prefix) != thread_id):
                        continue
                routes.append({"window_id": value["window_id"],
                               "terminal_id": terminal["terminal_id"],
                               "thread_id": thread_id,
                               "showing": terminal.get("current_thread_id") == thread_id,
                               "seen_at_ms": terminal.get("seen_at_ms", 0)})
        except (OSError, KeyError, TypeError, ValueError):
            continue
    return sorted(routes, key=lambda item: (item["showing"], item["seen_at_ms"]), reverse=True)


def notification_click_action(thread_id):
    if not isinstance(thread_id, str) or not THREAD_ID.fullmatch(thread_id):
        return []
    routes = click_routes(thread_id)
    if not routes:
        return []
    token = str(uuid.uuid4())
    directory = codex_home() / "vscode-click/tickets"
    try:
        write_private_json(directory / (token + ".json"),
                           dict(routes[0], version=1, created_at_ms=time.time() * 1000))
    except OSError:
        return []
    command = ["/usr/bin/env", "CODEX_HOME=" + str(codex_home()), PYTHON,
               str(Path(__file__).resolve()), "--open-notification", token]
    return ["-execute", shlex.join(command)]


def remove_click_tickets(thread_id):
    for path in (codex_home() / "vscode-click/tickets").glob("*.json"):
        value = read_private_json(path, limit=8192)
        if value and value.get("thread_id") == thread_id:
            try:
                path.unlink()
            except OSError:
                pass


def open_notification(token):
    if not isinstance(token, str) or not THREAD_ID.fullmatch(token):
        return
    path = codex_home() / "vscode-click/tickets" / (token + ".json")
    ticket = read_private_json(path, limit=8192)
    try:
        if (not ticket or ticket.get("version") != 1
                or not 0 <= ticket["created_at_ms"] <= time.time() * 1000
                or not isinstance(ticket.get("thread_id"), str)
                or not THREAD_ID.fullmatch(ticket["thread_id"])):
            return
        routes = click_routes(ticket["thread_id"])
        route = next((item for item in routes
                      if item["window_id"] == ticket.get("window_id")
                      and item["terminal_id"] == ticket.get("terminal_id")),
                     routes[0] if routes else None)
        if route is None:
            write_clear_log({"hook_event_name": "NotificationClick", "source": "vscode",
                             "session_id": ticket["thread_id"]}, "target_unavailable")
            run_command(["/usr/bin/open", "-b", "com.microsoft.VSCode"], timeout=2)
            run_command([NOTIFIER, "-title", "Codex", "-message", "Original terminal is unavailable",
                         "-activate", "com.microsoft.VSCode"], timeout=2)
            return
        request = dict(route, version=1, request_id=token, created_at_ms=time.time() * 1000)
        write_private_json(codex_home() / "vscode-click/requests" / route["window_id"] / (token + ".json"), request)
        path.unlink()
    except (OSError, KeyError, TypeError, ValueError):
        return


def run_command(command, timeout=5):
    try:
        subprocess.run(command, timeout=timeout, check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as error:
        print("Codex notify: " + type(error).__name__, file=sys.stderr)
        return type(error).__name__


def lookup_thread_name(thread_id):
    if not isinstance(thread_id, str) or not thread_id:
        return ""
    codex_home = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
    name = ""
    try:
        with (codex_home / "session_index.jsonl").open(encoding="utf-8", errors="replace") as index:
            for line in index:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(entry, dict) or entry.get("id") != thread_id:
                    continue
                candidate = entry.get("thread_name")
                if isinstance(candidate, str) and candidate.strip():
                    name = " ".join(candidate.split())
    except OSError:
        return ""
    return name


def send_notification(cwd, thread_id, status):
    if clear_foreground_notification(thread_id, result="notification_suppressed"):
        return
    title_parts = []
    if isinstance(cwd, str) and cwd:
        project = Path(cwd).name
        if project:
            title_parts.append(project)
    thread_name = lookup_thread_name(thread_id)
    if thread_name:
        title_parts.append(thread_name)
    if not title_parts:
        title_parts.append("Codex")
    message = status
    command = [NOTIFIER, "-title", " · ".join(title_parts),
               "-message", message]
    if isinstance(thread_id, str) and thread_id:
        command += ["-group", "codex-" + thread_id]
    command += notification_click_action(thread_id)
    run_command(command)
    clear_foreground_notification(thread_id, result="cleared_after_send")


def handle_input_hook():
    try:
        event = json.load(sys.stdin)
    except (ValueError, TypeError, OSError):
        return
    if not isinstance(event, dict):
        return
    if (event.get("hook_event_name") != "PreToolUse"
            or event.get("tool_name") != "request_user_input"):
        return
    tool_input = event.get("tool_input")
    questions = tool_input.get("questions") if isinstance(tool_input, dict) else None
    status = "Input required"
    if isinstance(questions, list) and questions:
        count = len(questions)
        status = str(count) + (" question" if count == 1 else " questions")
    send_notification(event.get("cwd"), event.get("session_id"), status)


def write_clear_log(event, result, error=None):
    record = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "hook": event.get("hook_event_name"),
        "source": event.get("source") if isinstance(event.get("source"), str) else None,
        "session_id": event.get("session_id") if isinstance(event.get("session_id"), str) else None,
        "result": result,
    }
    if error:
        record["error"] = error
    home = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
    try:
        directory = home / "log"
        directory.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
        descriptor = os.open(str(directory / "notifications.jsonl"),
                             os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(descriptor, data)
        finally:
            os.close(descriptor)
    except OSError:
        pass


def handle_closed_terminal():
    try:
        event = json.load(sys.stdin)
    except (ValueError, OSError):
        return
    ids = event.get("thread_ids") if isinstance(event, dict) else None
    if not isinstance(ids, list):
        return
    for thread_id in dict.fromkeys(item for item in ids if isinstance(item, str) and THREAD_ID.fullmatch(item)):
        # 其他存活终端仍关联此会话时保留通知。
        if click_routes(thread_id):
            continue
        error = run_command([NOTIFIER, "-remove", "codex-" + thread_id], timeout=2)
        if not error:
            remove_click_tickets(thread_id)
        write_clear_log({"hook_event_name": "VSCodeTerminalExit", "source": "vscode", "session_id": thread_id},
                        "remove_failed" if error else "remove_succeeded", error)


def completion_status(event):
    fallback = "Finished • " + datetime.now().strftime("%H:%M")
    thread_id = event.get("thread-id")
    turn_id = event.get("turn-id")
    if not isinstance(thread_id, str) or not isinstance(turn_id, str):
        return fallback
    home = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
    databases = sorted(home.glob("state_*.sqlite"),
                       key=lambda p: int(p.stem.split("_")[-1])
                       if p.stem.split("_")[-1].isdigit() else -1, reverse=True)
    rollout = None
    for database in databases:
        try:
            connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=0.2)
            try:
                row = connection.execute("SELECT rollout_path FROM threads WHERE id = ?",
                                         (thread_id,)).fetchone()
            finally:
                connection.close()
            if row and isinstance(row[0], str):
                rollout = Path(row[0])
                break
        except (sqlite3.Error, OSError, ValueError):
            continue
    if rollout is None:
        return fallback
    for attempt in range(6):
        try:
            with rollout.open("rb") as transcript:
                transcript.seek(0, 2)
                offset = max(0, transcript.tell() - 2 * 1024 * 1024)
                transcript.seek(offset)
                if offset:
                    transcript.readline()
                lines = transcript.read().splitlines()
            for line in reversed(lines):
                try:
                    record = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                if not isinstance(record, dict) or record.get("type") != "event_msg":
                    continue
                payload = record.get("payload")
                if (not isinstance(payload, dict) or payload.get("type") != "task_complete"
                        or payload.get("turn_id") != turn_id):
                    continue
                duration = payload.get("duration_ms")
                completed = payload.get("completed_at")
                if (isinstance(duration, bool) or not isinstance(duration, (int, float))
                        or duration < 0 or isinstance(completed, bool)
                        or not isinstance(completed, (int, float))):
                    return fallback
                seconds = int(duration / 1000)
                minutes, seconds = divmod(seconds, 60)
                hours, minutes = divmod(minutes, 60)
                parts = []
                if hours:
                    parts.append(str(hours) + "h")
                if hours or minutes:
                    parts.append(str(minutes) + "m")
                parts.append(str(seconds) + "s")
                clock = datetime.fromtimestamp(completed).strftime("%H:%M")
                return "Worked for " + " ".join(parts) + " • " + clock
        except (OSError, ValueError, OverflowError):
            return fallback
        if attempt < 5:
            time.sleep(0.1)
    return fallback


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--open-notification":
        open_notification(sys.argv[2])
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--resolve-thread":
        print(json.dumps({"thread_id": resolve_title_thread(sys.argv[2])}))
        return
    if sys.argv[1:] == ["--vscode-clear"]:
        try:
            event = json.load(sys.stdin)
        except (ValueError, TypeError, OSError):
            return
        if isinstance(event, dict) and isinstance(event.get("window_id"), str):
            clear_foreground_notification(event.get("thread_id"), event["window_id"])
        return
    if sys.argv[1:] == ["--vscode-clear-closed"]:
        handle_closed_terminal()
        return
    if sys.argv[1:] == ["--input-hook"]:
        handle_input_hook()
        return
    arguments = sys.argv[1:]
    if ORIGINAL_CALLBACK:
        run_command(ORIGINAL_CALLBACK + arguments)
    if len(arguments) != 1:
        return
    try:
        event = json.loads(arguments[0])
    except (ValueError, TypeError):
        return
    if not isinstance(event, dict) or event.get("type") != "agent-turn-complete":
        return
    send_notification(event.get("cwd"), event.get("thread-id"), completion_status(event))


if __name__ == "__main__":
    main()
