"""隔离执行真实完成回调，通知和原回调使用可记录的命令替身。"""
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
THREAD = "00111111-1111-1111-1111-111111111111"
TURN = "00222222-2222-2222-2222-222222222222"
WINDOW = "aaaaaaaa-1111-1111-1111-111111111111"
TERMINAL = "bbbbbbbb-2222-2222-2222-222222222222"
COMPLETED = int(datetime(2024, 1, 2, 3, 4, 5).timestamp())
EVENT = {"type": "agent-turn-complete", "thread-id": THREAD, "turn-id": TURN,
         "cwd": "/private/example-project", "last-assistant-message": "PRIVATE_BODY"}


def completion(turn=TURN, duration=42000):
    return json.dumps({"type": "event_msg", "payload": {
        "type": "task_complete", "turn_id": turn,
        "duration_ms": duration, "completed_at": COMPLETED}}) + "\n"


with tempfile.TemporaryDirectory(prefix="codex-completion-smoke-") as temporary:
    root = Path(temporary)
    mock = root / "notifier"
    mock.write_text("#!" + sys.executable + "\n" + '''import json,os,sys
from pathlib import Path
with (Path(os.environ["CODEX_HOME"]) / "commands.jsonl").open("a") as stream:
    stream.write(json.dumps(sys.argv[1:]) + "\\n")
if "-title" in sys.argv and os.environ.get("MOCK_FAIL"):
    sys.exit(1)
''')
    mock.chmod(0o700)

    def scenario(name, *, registered=False, transcript=None, database=True,
                 index=None, route=False, foreground=False, fail=False, event=None,
                 delayed=False):
        home = root / name
        home.mkdir()
        rollout = home / "rollout.jsonl"
        if transcript is not None:
            rollout.write_text(transcript)
        if database == "broken":
            (home / "state_5.sqlite").write_text("not a database")
        elif database:
            with sqlite3.connect(home / "state_5.sqlite") as connection:
                connection.execute("CREATE TABLE threads (id TEXT, rollout_path TEXT)")
                if registered:
                    connection.execute("INSERT INTO threads VALUES (?, ?)",
                                       (THREAD, None if registered == "no-path" else str(rollout)))
        if index is not None:
            (home / "session_index.jsonl").write_text(index)
        if route:
            directory = home / "vscode-click/windows"
            directory.mkdir(parents=True)
            (directory / (WINDOW + ".json")).write_text(json.dumps({
                "version": 1, "window_id": WINDOW, "updated_at_ms": time.time() * 1000,
                "pid": os.getpid(), "terminals": [{"terminal_id": TERMINAL,
                "thread_ids": [THREAD], "current_thread_id": THREAD}]}))
            if route == "broken":
                (directory / (WINDOW + ".json")).write_text("{invalid")
            elif route == "invalid":
                value = json.loads((directory / (WINDOW + ".json")).read_text())
                value["terminals"] = None
                (directory / (WINDOW + ".json")).write_text(json.dumps(value))
        if foreground:
            directory = home / "vscode-focus"
            directory.mkdir()
            (directory / (WINDOW + ".json")).write_text(json.dumps({
                "version": 1, "window_id": WINDOW, "updated_at_ms": time.time() * 1000,
                "pid": os.getpid(), "focused": True, "thread_id": THREAD}))
        directory = home / "notification-bridge"
        directory.mkdir()
        (directory / "runtime.json").write_text(json.dumps({
            "notifier": str(mock), "original_callback": [sys.executable, str(mock), "--original"]}))
        payload = event if event is not None else EVENT
        worker = None
        if delayed:
            def append_completion():
                deadline = time.monotonic() + 5
                while not (home / "commands.jsonl").exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                time.sleep(0.18)
                with rollout.open("a") as stream:
                    stream.write("\n" + completion())
            worker = threading.Thread(target=append_completion)
            worker.start()
        started = datetime.now()
        try:
            subprocess.run([sys.executable, "-B", str(ROOT / "scripts/notify.py"), json.dumps(payload)],
                           env={**os.environ, "CODEX_HOME": str(home), "MOCK_FAIL": "1" if fail else ""},
                           check=True, timeout=8, capture_output=True)
        finally:
            if worker:
                worker.join(timeout=6)
                assert not worker.is_alive(), name
        commands = [json.loads(line) for line in (home / "commands.jsonl").read_text().splitlines()]
        assert commands[0] == ["--original", json.dumps(payload)], name + "：原回调未原样转发"
        records = [json.loads(line) for line in (home / "log/notifications.jsonl").read_text().splitlines()]
        record = records[-1]
        assert record["hook"] == "agent-turn-complete", name
        assert "PRIVATE_BODY" not in json.dumps(records), name + "：日志包含正文"
        assert str(home) not in json.dumps(records), name + "：日志包含私有路径"
        sent = [args for args in commands if "-title" in args]
        for args in sent:
            message = args[args.index("-message") + 1]
            assert re.fullmatch(r".+ • \d{2}:\d{2}:\d{2}", message) and message.count(" • ") == 1, name
            if record["status_kind"] == "finished":
                clock = message.rsplit(" • ", 1)[1]
                # 允许流程跨过秒或午夜边界，核对时间属于本次调用区间。
                stamp = datetime.strptime(clock, "%H:%M:%S").time()
                start, end = started.time().replace(microsecond=0), datetime.now().time()
                assert start <= stamp <= end if start <= end else stamp >= start or stamp <= end, name
        return record, sent

    record, sent = scenario("temporary")
    assert not sent and record["reason"] == "unrecognized_session" and record["timing_attempts"] == 0

    record, sent = scenario("normal", registered=True, transcript=completion())
    assert record["result"] == "notification_sent" and record["timing_reason"] == "timing_found"
    assert sent[0][sent[0].index("-message") + 1] == "Worked for 42s • 03:04:05"

    for duration, expected in [(125000, "2m 5s"), (3725000, "1h 2m 5s")]:
        record, sent = scenario("duration-" + str(duration), registered=True, transcript=completion(duration=duration))
        assert sent[0][sent[0].index("-message") + 1] == "Worked for " + expected + " • 03:04:05"

    for name, transcript, reason in [
        ("missing-file", None, "rollout_unreadable"),
        ("other-turn", completion("other-turn"), "turn_not_found"),
        ("invalid-duration", completion(duration=-1), "invalid_timing"),
        ("non-finite-duration", completion(duration=float("inf")), "invalid_timing"),
    ]:
        record, sent = scenario(name, registered=True, transcript=transcript)
        assert record["timing_reason"] == reason and record["status_kind"] == "finished", name
        assert sent[0][sent[0].index("-message") + 1].startswith("Finished • "), name
        if name == "other-turn":
            assert record["timing_attempts"] == 6

    record, sent = scenario("delayed", registered=True, transcript='{"partial":', delayed=True)
    assert record["timing_reason"] == "timing_found" and 1 < record["timing_attempts"] <= 6

    record, sent = scenario("index-only", index=json.dumps({"id": THREAD}) + "\n")
    assert sent and record["identity_sources"] == ["index"]
    record, sent = scenario("terminal-only", route=True)
    assert sent and record["identity_sources"] == ["terminal"]
    for route, reason in [("broken", "terminal_state_unreadable"), ("invalid", "terminal_state_invalid")]:
        record, sent = scenario("terminal-" + route, route=route)
        assert sent and record["identity_errors"] == [reason]
    record, sent = scenario("no-database", database=False)
    assert sent and record["timing_reason"] == "lookup_failed"
    record, sent = scenario("broken-database", database="broken")
    assert sent and record["result"] == "notification_sent" and record["identity_errors"]
    record, sent = scenario("broken-index", index="{invalid\n")
    assert sent and record["identity_errors"] == ["index_invalid"]
    record, sent = scenario("invalid-index", index="[]\n")
    assert sent and record["identity_errors"] == ["index_invalid"]
    record, sent = scenario("no-rollout-path", registered="no-path")
    assert sent and record["timing_reason"] == "rollout_unavailable"
    record, sent = scenario("missing-identifiers", event={**EVENT, "thread-id": None})
    assert sent and record["timing_reason"] == "missing_identifiers"
    record, sent = scenario("missing-turn", event={**EVENT, "turn-id": None})
    assert sent and record["timing_reason"] == "missing_identifiers"
    record, sent = scenario("foreground", registered=True, transcript=completion(), foreground=True)
    assert not sent and record["result"] == "notification_suppressed"
    record, sent = scenario("send-failure", registered=True, transcript=completion(), fail=True)
    assert sent and record["result"] == "send_failed" and record["error"] == "CalledProcessError"

    for name, questions, expected in [
        ("one-question", [{}], "1 question"),
        ("three-questions", [{}, {}, {}], "3 questions"),
        ("unknown-count", None, "Input required"),
        ("empty-questions", [], "Input required"),
        ("missing-terminal", None, "Original terminal is unavailable"),
    ]:
        home = root / name
        directory = home / "notification-bridge"
        directory.mkdir(parents=True)
        (directory / "runtime.json").write_text(json.dumps({"notifier": str(mock)}))
        command = [sys.executable, "-B", str(ROOT / "scripts/notify.py"), "--input-hook"]
        payload = {"hook_event_name": "PreToolUse", "tool_name": "request_user_input",
                   "cwd": "/private/example-project", "session_id": THREAD,
                   "tool_input": {"questions": questions}}
        if name == "missing-terminal":
            directory = home / "vscode-click/tickets"
            directory.mkdir(parents=True)
            (directory / (TURN + ".json")).write_text(json.dumps({
                "version": 1, "thread_id": THREAD, "created_at_ms": time.time() * 1000}))
            # 只替换打开应用的外部动作；仍执行真实点击入口、凭据读取和通知命令。
            bootstrap = '''import runpy,subprocess,sys
original = subprocess.run
def isolated(command, *args, **kwargs):
    if command[0] == "/usr/bin/open":
        return subprocess.CompletedProcess(command, 0)
    return original(command, *args, **kwargs)
subprocess.run = isolated
sys.argv = [sys.argv[1], "--open-notification", sys.argv[2]]
runpy.run_path(sys.argv[0], run_name="__main__")
'''
            command = [sys.executable, "-B", "-c", bootstrap, str(ROOT / "scripts/notify.py"), TURN]
        started = datetime.now()
        subprocess.run(command, input=json.dumps(payload), text=True,
                       env={**os.environ, "CODEX_HOME": str(home), "MOCK_FAIL": ""},
                       check=True, capture_output=True, timeout=8)
        commands = [json.loads(line) for line in (home / "commands.jsonl").read_text().splitlines()]
        assert len(commands) == 1, name
        message = commands[0][commands[0].index("-message") + 1]
        assert re.fullmatch(re.escape(expected) + r" • \d{2}:\d{2}:\d{2}", message), name
        stamp = datetime.strptime(message.rsplit(" • ", 1)[1], "%H:%M:%S").time()
        start, end = started.time().replace(microsecond=0), datetime.now().time()
        assert start <= stamp <= end if start <= end else stamp >= start or stamp <= end, name

print("PASS: 完成回调过滤、原回调转发、耗时重试、故障兜底、前台静默、诊断日志及系统通知秒级时间")
