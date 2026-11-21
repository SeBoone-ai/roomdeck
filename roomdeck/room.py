#!/usr/bin/env python3
"""room: open, list, classify, attach and close RoomDeck tmux rooms."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

MAIN = "main"
WATCH = "watch"
FIXED = (MAIN, WATCH)
WORK = tuple(f"room-{n}" for n in range(1, 100))
ROOM_RE = re.compile(r"^(main|watch|room-[1-9][0-9]?)$")
SESSION_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
NAME_MAX = 60
SUMMARY_MAX = 40

CLIENTS = {
    "claude": ["claude"],
    "codex": ["codex"],
    "agy": ["agy"],
    "grok": ["grok"],
    "shell": [],
}
SHELLS = {"bash", "zsh", "sh", "fish"}
STATES = {
    "working": "Working",
    "input": "Input",
    "approval": "Approval",
    "ended": "Ended",
    "unknown": "Unknown",
    "standby": "Idle",
}

WRAPPER = """cd "$1" || exit
shift
tmux set-option -p -t "$TMUX_PANE" @roomdeck_agent_exit ""
tmux set-option -p -t "$TMUX_PANE" @roomdeck_agent_started "$(date +%s%N)"
"$@"
agent_rc=$?
tmux set-option -p -t "$TMUX_PANE" @roomdeck_agent_exit "$agent_rc"
exec "${SHELL:-bash}" """.strip()

FIELD_SEP = "|"
EXIT_INVALID, EXIT_REFUSED, EXIT_UNAVAILABLE, EXIT_TMUX = 2, 3, 4, 5

NUMBERED_RE = re.compile(r"^\s*(?:[❯›>]\s*)?\d\.\s")
POINTED_RE = re.compile(r"^\s*[❯›>]\s*\d\.\s")
TRUST_HEADER_RE = re.compile(r"Do you trust the contents of this (?:directory|project)\?")
TRUST_CHOICE_RE = re.compile(r"\b(?:Yes, proceed|Yes, I trust this folder)\b")
ARROW_CONFIRM_RE = re.compile(r"↑/↓\s+Navigate\s*·\s*enter\s+Confirm")
ARROW_SELECTED_RE = re.compile(r"^\s*[❯›>]\s+\S")
APPROVAL_BOTTOM_LINES = 12


class RoomError(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def state_dir():
    return Path(os.environ.get("ROOMDECK_STATE") or Path.home() / ".local/state/roomdeck")


def socket_path():
    return os.environ.get("ROOMDECK_TMUX_SOCKET", "")


def config():
    path = os.environ.get("ROOMDECK_CONFIG") or Path.home() / ".config/roomdeck/config.json"
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def clients():
    try:
        extra = config().get("rooms", {}).get("clients", {})
        custom = {k: v for k, v in extra.items() if isinstance(v, list) and all(isinstance(a, str) for a in v)}
    except AttributeError:
        custom = {}
    table = dict(CLIENTS)
    table.update(custom)
    return table


def tmux(*args, input_text=None):
    sock = socket_path()
    env = dict(os.environ, LC_ALL="C.UTF-8")
    if sock:
        env.pop("TMUX", None)
    base = ["tmux", "-S", sock] if sock else ["tmux"]
    return subprocess.run([*base, *args], capture_output=True, text=True, input=input_text, env=env, timeout=10)


def check_room(room):
    if not ROOM_RE.match(room or ""):
        raise RoomError(f"invalid room name: {room!r}", EXIT_INVALID)
    return room


def check_session(name):
    if not SESSION_RE.match(name or ""):
        raise RoomError(f"invalid session name: {name!r}", EXIT_INVALID)
    return name


def clean_label(name):
    label = "".join(ch for ch in (name or "").strip() if ch.isprintable())
    return label[:NAME_MAX]


def check_dir(path):
    if not path or not os.path.isabs(path) or not os.path.isdir(path):
        raise RoomError(f"folder must be an existing absolute path: {path!r}", EXIT_INVALID)
    return os.path.realpath(path)


def sessions():
    result = tmux(
        "list-sessions",
        "-F",
        FIELD_SEP.join(
            ["#{session_name}", "#{session_created}", "#{pane_current_path}", "#{@room_parent}", "#{@room_label}", "#{@room_summary}"]
        ),
    )
    if result.returncode:
        return []
    rows = []
    for line in result.stdout.splitlines():
        parts = line.split(FIELD_SEP, 5)
        if len(parts) == 6:
            name, created, cwd, parent, label, summary = parts
            rows.append(
                {
                    "name": name,
                    "created": created,
                    "cwd": cwd,
                    "parent": parent,
                    "label": label,
                    "summary": summary,
                    "room": bool(ROOM_RE.match(name)),
                }
            )
    return rows


def parse_kind_env(out):
    text = out.strip()
    return text.removeprefix("COCKPIT_KIND=") if text.startswith("COCKPIT_KIND=") else ""


def kind_of(session):
    return parse_kind_env(tmux("show-environment", "-t", f"={session}", "COCKPIT_KIND").stdout)


def caller_session():
    pane = os.environ.get("TMUX_PANE", "")
    caller_socket = os.environ.get("TMUX", "").split(",")[0]
    if not pane or not caller_socket or (socket_path() and os.path.realpath(caller_socket) != os.path.realpath(socket_path())):
        return ""
    result = tmux("display-message", "-p", "-t", pane, "#{session_name}")
    return result.stdout.strip() if result.returncode == 0 else ""


def open_room(client, directory=None, name="", role=None):
    table = clients()
    if client not in table:
        raise RoomError(f"unknown client: {client!r}", EXIT_INVALID)
    directory = check_dir(directory or str(Path.home()))
    label = clean_label(name)
    candidates = {"main": (MAIN,), "watch": (WATCH,)}.get(role, WORK)
    parent = caller_session()
    argv = table[client]
    command = ["--", "bash", "-c", WRAPPER, "_", directory, *argv] if argv else []
    for room in candidates:
        result = tmux(
            "new-session",
            "-d",
            "-s",
            room,
            "-c",
            directory,
            "-x",
            "220",
            "-y",
            "50",
            "-e",
            f"COCKPIT_KIND={client}",
            *command,
        )
        if result.returncode == 0:
            tmux("set-option", "-t", f"={room}:", "@room_parent", parent)
            tmux("set-option", "-t", f"={room}:", "@room_label", label)
            return room
        if "duplicate session" not in result.stderr:
            raise RoomError(result.stderr.strip() or "tmux new-session failed", EXIT_TMUX)
    raise RoomError(f"{candidates[0]} is already open" if role in ("main", "watch") else "no free room", EXIT_UNAVAILABLE)


def pane_facts(session):
    result = tmux(
        "display-message",
        "-p",
        "-t",
        f"={session}:",
        FIELD_SEP.join(["#{pane_dead}", "#{pane_current_command}", "#{@roomdeck_agent_started}", "#{@roomdeck_agent_exit}"]),
    )
    if result.returncode:
        raise RoomError(result.stderr.strip() or f"room not found: {session}", EXIT_UNAVAILABLE)
    dead, command, started, code = (result.stdout.rstrip("\n").split(FIELD_SEP) + [""] * 4)[:4]
    return {"dead": dead == "1", "command": command, "started": started, "exit": code}


def waiting_for_approval(screen):
    lines = [line for line in screen.splitlines() if line.strip()][-APPROVAL_BOTTOM_LINES:]
    if any(POINTED_RE.match(line) for line in lines) and sum(bool(NUMBERED_RE.match(line)) for line in lines) >= 2:
        return True
    if any(TRUST_HEADER_RE.search(line) for line in lines) and any(TRUST_CHOICE_RE.search(line) for line in lines):
        return True
    if any(ARROW_CONFIRM_RE.search(line) for line in lines) and any(ARROW_SELECTED_RE.match(line) for line in lines):
        return True
    return False


def base_client(kind):
    head = (kind or "").split("-", 1)[0]
    return head if head in {"codex", "agy", "claude", "grok"} else kind


def classify_client(screen, kind, command=""):
    if kind == "shell" and command in {"codex", "agy", "claude", "grok"}:
        kind = command
    kind = base_client(kind)
    lines = screen.rstrip().splitlines()
    footer = "\n".join(lines[-5:])
    if kind == "codex":
        if "tab to queue message" in footer or any(
            re.match(r"^\s*• .+\([^\n]*esc to interrupt\)", line) for line in lines[-12:]
        ):
            return "running"
        if (
            "← for agents" in footer
            and any(re.match(r"^\s*\S+ .*Context \d+% left", line, re.I) for line in lines[-5:])
            and any(re.match(r"^\s*› ", line) for line in lines[-8:])
        ):
            return "waiting"
    if kind == "agy":
        if re.search(r"^\s*esc to cancel\b[^\n]*\bGemini ", footer, re.M):
            return "running"
        if lines and re.search(r"\bGemini\b", lines[-1]):
            if re.search(r"\b[1-9]\d*\s+task\(s\)(?=\s|$)", lines[-1]) or any(
                re.match(r"^\s*●\s+\[\d\d:\d\d:\d\d\].*\brunning\b", line) for line in lines[-6:-1]
            ):
                return "running"
            if any(re.search(r"↑/↓\s+Navigate\s*·\s*enter\s+Confirm", line) for line in lines[-6:-1]):
                return "waiting"
            if len(lines) >= 4 and re.fullmatch(r"\s*─+\s*", lines[-2]):
                for idx in range(len(lines) - 3, max(0, len(lines) - 9), -1):
                    if re.match(r"^\s*>(?:\s|$)", lines[idx]) and re.fullmatch(r"\s*─+\s*", lines[idx - 1]):
                        return "waiting"
    if kind == "grok":
        if re.search(r"^\s*╰─.*\bGrok\b.*─╯\s*$", footer, re.M):
            if "Ctrl+c:cancel" in footer or any(re.search(r"\[stop\]\s*$", line) for line in lines[-8:]):
                return "running"
            if any(re.match(r"^\s*│\s*❯(?:\s|│|$)", line) for line in lines[-8:]):
                return "waiting"
        if "Grok Build" in footer and any("Do you trust the contents of this directory?" in line for line in lines[-12:]):
            return "waiting"
    if kind == "claude":
        if "esc to interrupt" in footer or any(re.match(r"^\s*\S\s\S+…\s\(", line) for line in lines[-12:]):
            return "running"
        if re.search(r"Do you want to proceed\?|Esc to cancel", footer):
            return "waiting"
        if re.search(r"bypass permissions|shift\+tab to cycle|\? for shortcuts", footer) and any(
            re.match(r"^\s*❯", line) for line in lines[-8:]
        ):
            return "waiting"
    return "unknown"


def classify_screen(screen, kind, facts):
    if facts["dead"] or (facts["started"] and facts["exit"] != ""):
        return "ended"
    if waiting_for_approval(screen):
        return "approval"
    state = classify_client(screen, kind, facts["command"])
    if state == "running":
        return "working"
    if state == "waiting":
        return "input"
    if kind == "shell" and facts["command"] in SHELLS:
        return "input"
    return "unknown"


def classify(session):
    check_session(session)
    facts = pane_facts(session)
    screen = tmux("capture-pane", "-p", "-t", f"={session}:")
    if screen.returncode:
        raise RoomError(screen.stderr.strip() or "capture-pane failed", EXIT_TMUX)
    return classify_screen(screen.stdout, kind_of(session), facts)


def close_room(room, force=False):
    check_room(room)
    if tmux("has-session", "-t", f"={room}").returncode:
        raise RoomError(f"room not found: {room}", EXIT_UNAVAILABLE)
    if not force and not tmux("show-options", "-v", "-t", f"={room}:", "@room_close_ok").stdout.strip():
        raise RoomError(f"{room} has no closing mark; use --force", EXIT_REFUSED)
    inbox = state_dir() / "inbox" / room
    if inbox.is_dir() and any(inbox.iterdir()):
        archive = state_dir() / "archive" / f"{room}-{time.strftime('%Y%m%dT%H%M%S')}"
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(inbox), str(archive))
    result = tmux("kill-session", "-t", f"={room}")
    if result.returncode:
        raise RoomError(result.stderr.strip() or "kill-session failed", EXIT_TMUX)


def mark_closed(room=None, clear=False):
    room = check_room(room or caller_session())
    if room in FIXED:
        raise RoomError(f"{room} is never closed by a mark", EXIT_REFUSED)
    mark = ["-u", "-t", f"={room}:", "@room_close_ok"] if clear else ["-t", f"={room}:", "@room_close_ok", time.strftime("%Y-%m-%dT%H:%M:%S")]
    result = tmux("set-option", *mark)
    if result.returncode:
        raise RoomError(result.stderr.strip() or f"room not found: {room}", EXIT_UNAVAILABLE)
    return room


def _set_room_option(room, option, value):
    result = tmux("set-option", *(["-t", f"={room}:", option, value] if value else ["-u", "-t", f"={room}:", option]))
    if result.returncode:
        raise RoomError(result.stderr.strip() or f"room not found: {room}", EXIT_UNAVAILABLE)
    return value


def set_label(room, text):
    check_session(room)
    return _set_room_option(room, "@room_label", clean_label(text))


def set_summary(room, text):
    check_session(room)
    return _set_room_option(room, "@room_summary", clean_label(text)[:SUMMARY_MAX])


def attach(room):
    check_session(room)
    sock = socket_path()
    os.execvp("tmux", ["tmux", "-S", sock, "attach", "-t", f"={room}"] if sock else ["tmux", "attach", "-t", f"={room}"])


def main(argv=None):
    parser = argparse.ArgumentParser(prog="room")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("open")
    p.add_argument("client")
    p.add_argument("--dir")
    p.add_argument("--name", default="")
    p.add_argument("--detach", action="store_true")
    p.add_argument("--role", choices=["main", "watch"])
    p = sub.add_parser("ls")
    p.add_argument("--all", action="store_true")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("attach")
    p.add_argument("room")
    p = sub.add_parser("classify")
    p.add_argument("room")
    p = sub.add_parser("close")
    p.add_argument("room")
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("mark-closed")
    p.add_argument("room", nargs="?")
    p.add_argument("--clear", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "open":
            room = open_room(args.client, args.dir, args.name, args.role)
            if not args.detach and sys.stdout.isatty():
                print(room, flush=True)
                attach(room)
            print(room)
        elif args.cmd == "ls":
            rows = [dict(r, client=kind_of(r["name"])) for r in sessions() if args.all or r["room"]]
            if args.json:
                print(json.dumps(rows, ensure_ascii=False))
            for r in [] if args.json else rows:
                print("\t".join([r["name"], r["client"] or "-", r["cwd"], r["label"]]))
        elif args.cmd == "attach":
            attach(args.room)
        elif args.cmd == "classify":
            state = classify(args.room)
            print(f"{state}\t{STATES[state]}")
        elif args.cmd == "close":
            close_room(args.room, args.force)
        elif args.cmd == "mark-closed":
            print(mark_closed(args.room, args.clear))
    except RoomError as exc:
        print(f"room: {exc}", file=sys.stderr)
        return exc.code
    except subprocess.TimeoutExpired:
        print("room: tmux timed out", file=sys.stderr)
        return EXIT_TMUX
    return 0


if __name__ == "__main__":
    sys.exit(main())
