#!/usr/bin/env python3
"""RoomDeck server: serves the deck UI and bridges it to tmux rooms via capture-pane / send-keys."""

import hashlib
import itertools
import json
import os
import re
import select
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import room

HOST = os.environ.get("ROOMDECK_HOST", "127.0.0.1")
PORT = int(os.environ.get("ROOMDECK_PORT", "7690"))
STATIC = Path(__file__).resolve().parent / "static"
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".png": "image/png",
}
DEFAULT_SITE = {
    "hosts": ["localhost", "127.0.0.1"],
    "origins": [f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}"],
    "devices": [],
}
DEFAULT_COMMANDS = [
    {"id": "compact", "label": "Compact", "text": "/compact"},
    {"id": "clear", "label": "Clear", "text": "/clear"},
]
SITE_ORIGIN_RE = re.compile(r"https?://[A-Za-z0-9.-]+(:\d+)?")
WHEEL = {"WheelUp": 64, "WheelDown": 65}
KEYS = {
    *WHEEL,
    "Enter",
    "Escape",
    "Tab",
    "BTab",
    "BSpace",
    "DC",
    "Up",
    "Down",
    "Left",
    "Right",
    "Home",
    "End",
    "PageUp",
    "PageDown",
    "M-Enter",
    *(f"F{n}" for n in range(1, 13)),
    *(f"C-{c}" for c in "abcdefghijklmnopqrstuvwxyz"),
}
STREAM_MAX = 16
DROP_MAX = 50 * 1024 * 1024
IMAGE_MAX = 20 * 1024 * 1024
IMAGE_TYPES = ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpg"), (b"GIF87a", "gif"), (b"GIF89a", "gif"))
DROP_KEEP_SECONDS = 7 * 86400
FRAME_SECONDS = 0.15
PING_SECONDS = 15
HISTORY_MAX = 2000
TEXT_MAX = 100_000
FACTS = "|".join(
    [
        "#{cursor_x}",
        "#{cursor_y}",
        "#{pane_width}",
        "#{pane_height}",
        "#{pane_current_path}",
        "#{alternate_on}",
        "#{cursor_flag}",
        "#{mouse_any_flag}",
        "#{mouse_sgr_flag}",
    ]
)

wakeups = {}
wakeups_lock = threading.Lock()
viewers = {}
views_lock = threading.Lock()
VIEW_MARK = "@roomdeck_view"
owners = {}
WIN_RE = re.compile(r"[A-Za-z0-9-]{1,64}")


class StreamTicket:
    def __init__(self, win, event):
        self.win, self.event, self.lost = win, event, set()


def take_rooms(ticket, sessions, claims):
    mine, moved = [], []
    with wakeups_lock:
        for session in sessions:
            owner = owners.get(session)
            if owner and owner["win"] != ticket.win and session not in claims:
                moved.append(session)
                continue
            if owner and owner["win"] != ticket.win:
                for other in owner["streams"]:
                    other.lost.add(session)
                    other.event.set()
                owner = None
            if owner is None:
                owner = owners[session] = {"win": ticket.win, "streams": set()}
            owner["streams"].add(ticket)
            mine.append(session)
    return mine, moved


def drop_rooms(ticket, sessions):
    with wakeups_lock:
        for session in sessions:
            owner = owners.get(session)
            if owner and ticket in owner["streams"]:
                owner["streams"].discard(ticket)
                if not owner["streams"]:
                    del owners[session]


def wake(session):
    with wakeups_lock:
        for event in wakeups.get(session, ()):
            event.set()


def subscribe(event, sessions):
    with wakeups_lock:
        for session in sessions:
            wakeups.setdefault(session, set()).add(event)


def unsubscribe(event, sessions):
    with wakeups_lock:
        for session in sessions:
            wakeups.get(session, set()).discard(event)


def session_id(session):
    return room.tmux("display-message", "-p", "-t", f"={session}:", "#{session_id}").stdout.strip()


def original_view(session):
    mark = room.tmux("show-options", "-w", "-v", "-t", f"={session}:", VIEW_MARK).stdout.split()
    if len(mark) == 3 and mark[0].isdigit() and mark[1].isdigit():
        return {"size": mark[:2], "manual": mark[2] == "1"}
    if mark:
        return {"size": [], "manual": False}
    size = room.tmux("display-message", "-p", "-t", f"={session}:", "#{window_width} #{window_height}").stdout.split()
    manual = room.tmux("show-options", "-w", "-t", f"={session}:", "window-size").stdout.strip()
    return {"size": size, "manual": bool(manual)}


def watch_start(session):
    with views_lock:
        if session in viewers:
            viewers[session]["count"] += 1
            return
        viewers[session] = dict(original_view(session), count=1, sid=session_id(session))


def watch_end(session):
    with views_lock:
        view = viewers.get(session)
        if not view:
            return
        view["count"] -= 1
        if view["count"]:
            return
        del viewers[session]
        if session_id(session) != view["sid"]:
            return
        if len(view["size"]) == 2 and all(v.isdigit() for v in view["size"]):
            room.tmux("resize-window", "-t", f"={session}:", "-x", view["size"][0], "-y", view["size"][1])
        if not view["manual"]:
            room.tmux("set-option", "-w", "-u", "-t", f"={session}:", "window-size")
        room.tmux("set-option", "-w", "-u", "-t", f"={session}:", VIEW_MARK)


def split_lines(text):
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def snapshot(session):
    facts = room.tmux("display-message", "-p", "-t", f"={session}:", FACTS)
    screen = room.tmux("capture-pane", "-p", "-e", "-N", "-t", f"={session}:")
    if facts.returncode or screen.returncode:
        error = (facts.stderr or screen.stderr).strip()
        raise RuntimeError(error.splitlines()[0] if error else "capture failed")
    x, y, cols, rows, cwd, alt, cursor, mouse, sgr = (facts.stdout.rstrip("\n").split("|") + [""] * 9)[:9]
    lines = split_lines(screen.stdout)
    return {
        "cursor": [int(x or 0), int(y or 0)],
        "cols": int(cols or 0),
        "rows": int(rows or 0),
        "cwd": cwd,
        "alt": alt == "1",
        "wheel": mouse == "1" and sgr == "1",
        "showCursor": cursor != "0",
        "lines": lines,
    }


def history(session, count):
    count = max(1, min(int(count), HISTORY_MAX))
    size = room.tmux("display-message", "-p", "-t", f"={session}:", "#{history_size}")
    if size.returncode:
        raise RuntimeError(size.stderr.strip() or "capture failed")
    avail = int(size.stdout.strip() or "0")
    if avail <= 0:
        return []
    result = room.tmux("capture-pane", "-p", "-e", "-N", "-S", f"-{min(count, avail)}", "-E", "-1", "-t", f"={session}:")
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "capture failed")
    return split_lines(result.stdout)


def send_keys(session, keys):
    if not isinstance(keys, list) or not keys or not all(k in KEYS for k in keys):
        raise ValueError("key not allowed")
    for wheel, group in itertools.groupby(keys, key=lambda k: k in WHEEL):
        group = list(group)
        if wheel:
            send_wheel(session, group)
            continue
        result = room.tmux("send-keys", "-t", f"={session}:", *group)
        if result.returncode:
            raise RuntimeError(result.stderr.strip())


def send_wheel(session, steps):
    # Only an app requesting SGR mouse reports reads these as wheel steps; elsewhere they arrive as typed text.
    info = room.tmux(
        "display-message",
        "-p",
        "-t",
        f"={session}:",
        "#{mouse_any_flag} #{mouse_sgr_flag} #{pane_width} #{pane_height}",
    ).stdout.split()
    if len(info) != 4 or info[:2] != ["1", "1"]:
        return
    x, y = max(1, int(info[2]) // 2), max(1, int(info[3]) // 3)
    result = room.tmux("send-keys", "-t", f"={session}:", "-l", "--", "".join(f"\x1b[<{WHEEL[k]};{x};{y}M" for k in steps))
    if result.returncode:
        raise RuntimeError(result.stderr.strip())


def send_text(session, text):
    if not isinstance(text, str) or not text or len(text) > TEXT_MAX:
        raise ValueError("bad text")
    # tmux treats a trailing ";" in an argument as a command separator, so route it through a paste buffer.
    if "\n" not in text and "\r" not in text and not text.endswith(";"):
        result = room.tmux("send-keys", "-t", f"={session}:", "-l", "--", text)
    else:
        buffer = f"roomdeck-{session}-{uuid.uuid4().hex[:12]}"
        result = room.tmux("load-buffer", "-b", buffer, "-", input_text=text.replace("\r\n", "\n"))
        if result.returncode == 0:
            result = room.tmux("paste-buffer", "-p", "-d", "-b", buffer, "-t", f"={session}:")
    if result.returncode:
        raise RuntimeError(result.stderr.strip())


def resize(session, cols, rows):
    cols, rows = int(cols), int(rows)
    if not (20 <= cols <= 500 and 5 <= rows <= 200):
        raise ValueError("bad size")
    with views_lock:
        view = viewers.get(session) or original_view(session)
        if len(view["size"]) == 2:
            room.tmux("set-option", "-w", "-t", f"={session}:", VIEW_MARK, f"{view['size'][0]} {view['size'][1]} {int(view['manual'])}")
    result = room.tmux("resize-window", "-t", f"={session}:", "-x", str(cols), "-y", str(rows))
    if result.returncode:
        raise RuntimeError(result.stderr.strip())


def config():
    return room.config()


def load_site():
    given = config().get("site")
    site = dict(DEFAULT_SITE, **(given if isinstance(given, dict) else {}))
    texts = lambda key: [v for v in site.get(key) or [] if isinstance(v, str)]
    origins = [o for o in texts("origins") if SITE_ORIGIN_RE.fullmatch(o)]
    devices = None if site.get("devices") is None else set(texts("devices"))
    return set(texts("hosts")), set(origins), devices


def load_commands():
    raw = config().get("commands")
    if not isinstance(raw, list):
        return list(DEFAULT_COMMANDS)
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("id") or "").strip()
        label = str(item.get("label") or cid).strip()
        text = item.get("text")
        if cid and label and isinstance(text, str) and text:
            out.append({"id": cid[:32], "label": label[:32], "text": text[:1000]})
    return out


SERVER_START = str(time.time_ns())
BUILD_ID_OVERRIDE = None


def build_id():
    if BUILD_ID_OVERRIDE is not None:
        return str(BUILD_ID_OVERRIDE)
    env_id = os.environ.get("ROOMDECK_BUILD_ID")
    if env_id:
        return env_id
    h = hashlib.sha256(SERVER_START.encode())
    for p in sorted(STATIC.glob("*")):
        if p.is_file():
            try:
                st = p.stat()
                h.update(f"{p.name}:{st.st_size}:{st.st_mtime_ns};".encode())
            except OSError:
                pass
    return h.hexdigest()[:12]


ALLOWED_HOSTS, ALLOWED_ORIGINS, DEVICES = load_site()


def room_rows():
    rows = []
    for row in room.sessions():
        kind = room.kind_of(row["name"])
        try:
            state = room.classify(row["name"])
        except room.RoomError:
            state = "unknown"
        if row["name"] == room.WATCH and state == "input":
            state = "standby"
        rows.append(dict(row, client=kind, state=state, stateLabel=room.STATES[state]))
    return rows


cpu_sample = {"stat": None}


def cpu_percent():
    fields = [int(v) for v in Path("/proc/stat").read_text().split("\n", 1)[0].split()[1:]]
    idle, total = fields[3] + fields[4], sum(fields)
    last, cpu_sample["stat"] = cpu_sample["stat"], (idle, total)
    if not last or total == last[1]:
        return None
    return round(100 * (1 - (idle - last[0]) / (total - last[1])))


def memory_percent():
    info = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines() if ":" in line)
    total, available = int(info["MemTotal"].split()[0]), int(info["MemAvailable"].split()[0])
    return round(100 * (1 - available / total))


def disk_free_gb():
    st = os.statvfs("/")
    return round(st.f_bavail * st.f_frsize / 1e9)


def machine_load():
    readings = {}
    for name, read in (("cpu", cpu_percent), ("memory", memory_percent), ("diskFreeGb", disk_free_gb)):
        try:
            readings[name] = read()
        except (OSError, ValueError, KeyError, ZeroDivisionError):
            readings[name] = None
    return readings


def usage():
    url = config().get("usage_url")
    if not isinstance(url, str) or not url.startswith("http://127.0.0.1:"):
        raise OSError("no usage monitor configured")
    with urllib.request.urlopen(url, timeout=3) as response:
        data = json.load(response)
    agents = [
        {
            "label": a.get("label", ""),
            "ok": bool(a.get("ok")),
            "stale": bool(a.get("stale")),
            "windows": [
                {"win": w.get("win", ""), "pct": w.get("pct", 0), "reset": w.get("reset", 0)}
                for w in a.get("windows", [])
            ],
        }
        for a in data.get("agents", [])
    ]
    return {"agents": agents}


def image_kind(head):
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return next((ext for magic, ext in IMAGE_TYPES if head.startswith(magic)), None)


def read_exact(stream, count):
    data = stream.read(count)
    if len(data) != count:
        raise ValueError("upload cut short")
    return data


def save_drop(name, length, stream, image=False):
    base = room.state_dir() / "drops"
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    now = time.time()
    for old in base.iterdir():
        if old.is_dir() and now - old.stat().st_mtime > DROP_KEEP_SECONDS:
            shutil.rmtree(old, ignore_errors=True)
    head = read_exact(stream, min(length, 12))
    if image:
        kind = image_kind(head)
        if not kind:
            raise ValueError("not a PNG, JPEG, GIF or WebP image")
        clean = f"paste-{os.urandom(4).hex()}.{kind}"
    else:
        clean = "".join(ch for ch in Path(name).name if ch.isprintable())[:120]
        if clean in ("", ".", ".."):
            clean = "file"
    folder = base / f"{time.strftime('%Y%m%d-%H%M%S')}-{os.urandom(3).hex()}"
    folder.mkdir(mode=0o700)
    target = folder / clean
    with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as out:
        out.write(head)
        remaining = length - len(head)
        while remaining:
            chunk = read_exact(stream, min(remaining, 1 << 20))
            out.write(chunk)
            remaining -= len(chunk)
    return str(target)


def list_dirs(path):
    home = Path.home().resolve()
    target = Path(path or home).resolve()
    if target != home and home not in target.parents:
        raise ValueError("outside home")
    names = sorted(p.name for p in target.iterdir() if p.is_dir() and not p.name.startswith(".")) if target.is_dir() else []
    return {"path": str(target), "parent": str(target.parent) if target != home else "", "dirs": names[:500]}


def frame_delta(session, frame, prev):
    if prev is not None and frame == prev:
        return None
    changed = {
        i: line
        for i, line in enumerate(frame["lines"])
        if prev is None or i >= len(prev["lines"]) or prev["lines"][i] != line
    }
    return dict(frame, room=session, lines=changed, total=len(frame["lines"]), full=prev is None)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _allowed(self, post, content_type="application/json"):
        if urlsplit("//" + self.headers.get("Host", "")).hostname not in ALLOWED_HOSTS:
            return False
        forwarded = self.headers.get("X-Forwarded-For")
        if DEVICES is not None and forwarded is not None and forwarded.split(",")[-1].strip() not in DEVICES:
            return False
        if post:
            return (
                self.headers.get("Origin") in ALLOWED_ORIGINS
                and self.headers.get("Content-Type", "").startswith(content_type)
            )
        origin = self.headers.get("Origin")
        return origin is None or origin in ALLOWED_ORIGINS

    def _send(self, status, body, content_type="application/json; charset=utf-8", framable=False):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN" if framable else "DENY")
        self.send_header("Content-Security-Policy", "frame-ancestors 'self'" if framable else "frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def _query(self):
        return {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}

    def do_GET(self):
        if not self._allowed(post=False):
            return self._send(403, {"error": "forbidden"})
        path = urlsplit(self.path).path
        query = self._query()
        try:
            if path == "/":
                return self._send(200, (STATIC / "index.html").read_bytes(), STATIC_TYPES[".html"])
            if path.startswith("/static/"):
                name = path.removeprefix("/static/")
                file = STATIC / name
                if not re.fullmatch(r"[a-z0-9-]+\.(html|css|js|png)", name) or not file.is_file():
                    return self._send(404, {"error": "not found"})
                return self._send(200, file.read_bytes(), STATIC_TYPES[file.suffix])
            if path == "/api/rooms":
                return self._send(
                    200,
                    {
                        "rooms": room_rows(),
                        "clients": sorted(room.clients()),
                        "home": str(Path.home()),
                        "commands": load_commands(),
                        "buildId": build_id(),
                    },
                )
            if path == "/api/history":
                return self._send(200, {"lines": history(room.check_session(query.get("room")), query.get("lines", "500"))})
            if path == "/api/load":
                return self._send(200, machine_load())
            if path == "/api/usage":
                try:
                    return self._send(200, usage())
                except (OSError, ValueError):
                    return self._send(502, {"error": "usage monitor unreachable"})
            if path == "/api/dirs":
                return self._send(200, list_dirs(query.get("path")))
            if path == "/api/stream":
                rooms = [room.check_session(r) for r in dict.fromkeys(query.get("rooms", "").split(",")) if r]
                if not rooms or len(rooms) > STREAM_MAX:
                    raise ValueError("bad room list")
                win = query.get("win", "")
                win = win if WIN_RE.fullmatch(win) else uuid.uuid4().hex
                return self._stream(rooms, win, set(query.get("claim", "").split(",")))
        except (room.RoomError, ValueError) as exc:
            return self._send(400, {"error": str(exc)})
        except RuntimeError as exc:
            return self._send(502, {"error": str(exc)})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path == "/api/drop":
            return self._drop()
        if not self._allowed(post=True):
            return self._send(403, {"error": "forbidden"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > TEXT_MAX * 4:
                return self._send(413, {"error": "too large"})
            body = json.loads(self.rfile.read(length) or b"{}")
            if path == "/api/open":
                name = room.open_room(
                    body.get("client", ""),
                    body.get("dir") or None,
                    body.get("name", ""),
                    body.get("role") if body.get("role") in ("main", "watch") else None,
                )
                return self._send(200, {"room": name})
            session = room.check_session(body.get("room"))
            if path == "/api/keys":
                send_keys(session, body.get("keys"))
            elif path == "/api/text":
                send_text(session, body.get("text"))
            elif path == "/api/label":
                room.set_label(session, body.get("label", ""))
            elif path == "/api/resize":
                resize(session, body.get("cols", 0), body.get("rows", 0))
            elif path == "/api/close":
                room.close_room(session, force=True)
            else:
                return self._send(404, {"error": "not found"})
            wake(session)
            return self._send(200, {"ok": True})
        except room.RoomError as exc:
            return self._send(409 if exc.code in (room.EXIT_REFUSED, room.EXIT_UNAVAILABLE) else 400, {"error": str(exc)})
        except (ValueError, TypeError) as exc:
            return self._send(400, {"error": str(exc)})
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            return self._send(502, {"error": str(exc) or "tmux failed"})

    def _drop(self):
        if not self._allowed(post=True, content_type="application/octet-stream"):
            return self._send(403, {"error": "forbidden"})
        length = int(self.headers.get("Content-Length", "0") or 0)
        query = self._query()
        image = query.get("image") == "1"
        if not 0 < length <= (IMAGE_MAX if image else DROP_MAX):
            return self._send(413, {"error": "file too large"})
        try:
            return self._send(200, {"path": save_drop(query.get("name", ""), length, self.rfile, image)})
        except ValueError as exc:
            return self._send(400, {"error": str(exc)})
        except OSError as exc:
            return self._send(500, {"error": str(exc)})

    def _client_gone(self):
        readable, _, _ = select.select([self.connection], [], [], 0)
        if not readable:
            return False
        try:
            return self.connection.recv(1, socket.MSG_PEEK) == b""
        except OSError:
            return True

    def _event(self, payload, kind=None):
        head = f"event: {kind}\n".encode() if kind else b""
        self.wfile.write(head + b"data: " + json.dumps(payload, ensure_ascii=False).encode() + b"\n\n")
        self.wfile.flush()

    def _stream(self, rooms, win, claims):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.close_connection = True
        event = threading.Event()
        ticket = StreamTicket(win, event)
        sessions, started = [], []
        sent, failed, last_ping = {}, set(), time.monotonic()
        try:
            sessions, moved = take_rooms(ticket, rooms, claims)
            subscribe(event, sessions)
            for session in sessions:
                watch_start(session)
                started.append(session)
            for session in moved:
                self._event({"room": session}, "moved")
            while not self._client_gone():
                event.clear()
                with wakeups_lock:
                    lost = [s for s in sessions if s in ticket.lost]
                for session in lost:
                    sessions.remove(session)
                    unsubscribe(event, [session])
                    if session in started:
                        started.remove(session)
                        watch_end(session)
                    sent.pop(session, None)
                    self._event({"room": session}, "moved")
                for session in sessions:
                    try:
                        frame = snapshot(session)
                    except (RuntimeError, subprocess.TimeoutExpired) as exc:
                        if session not in failed:
                            failed.add(session)
                            sent.pop(session, None)
                            self._event({"room": session, "error": str(exc)}, "failure")
                        continue
                    failed.discard(session)
                    payload = frame_delta(session, frame, sent.get(session))
                    if payload is None:
                        continue
                    self._event(payload)
                    sent[session], last_ping = frame, time.monotonic()
                if time.monotonic() - last_ping > PING_SECONDS:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    last_ping = time.monotonic()
                event.wait(FRAME_SECONDS)
        except (BrokenPipeError, ConnectionResetError, subprocess.TimeoutExpired):
            return
        finally:
            unsubscribe(event, sessions)
            drop_rooms(ticket, sessions)
            for session in started:
                watch_end(session)


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()
