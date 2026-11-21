import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roomdeck import room, server  # noqa: E402


class ViewSizeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patched = mock.patch.dict(os.environ, {"ROOMDECK_TMUX_SOCKET": str(Path(self.tmp.name) / "tmux.sock")})
        self.patched.start()
        os.environ.pop("TMUX", None)
        room.tmux("new-session", "-d", "-s", "room-1", "-x", "120", "-y", "40", "sleep 60")
        room.tmux("set-option", "-w", "-u", "-t", "=room-1:", "window-size")
        server.viewers.clear()

    def tearDown(self):
        room.tmux("kill-session", "-t", "=room-1")
        self.patched.stop()
        self.tmp.cleanup()

    def window_size_option(self):
        return room.tmux("show-options", "-w", "-t", "=room-1:", "window-size").stdout.strip()

    def size(self):
        return room.tmux("display-message", "-p", "-t", "=room-1:", "#{window_width}x#{window_height}").stdout.strip()

    def test_restarted_deck_restores_room_size(self):
        server.watch_start("room-1")
        server.resize("room-1", 60, 20)
        self.assertTrue(self.window_size_option())
        server.viewers.clear()
        server.watch_start("room-1")
        server.watch_end("room-1")
        self.assertEqual(self.window_size_option(), "")
        self.assertEqual(room.tmux("show-options", "-w", "-v", "-t", "=room-1:", server.VIEW_MARK).stdout.strip(), "")

    def test_manual_size_is_preserved(self):
        room.tmux("set-option", "-w", "-t", "=room-1:", "window-size", "manual")
        server.watch_start("room-1")
        server.resize("room-1", 60, 20)
        server.watch_end("room-1")
        self.assertIn("manual", self.window_size_option())
        self.assertEqual(self.size(), "120x40")

    def test_text_ending_in_semicolon_arrives_whole(self):
        room.tmux("new-session", "-d", "-s", "room-2", "-x", "80", "-y", "10", "cat")
        server.send_text("room-2", "ls;")
        server.send_text("room-2", ";")
        time.sleep(0.3)
        self.assertIn("ls;;", room.tmux("capture-pane", "-p", "-t", "=room-2:").stdout)
        room.tmux("kill-session", "-t", "=room-2")

    def test_wheel_step_reaches_only_sgr_mouse_apps(self):
        room.tmux("new-session", "-d", "-s", "room-2", "-x", "80", "-y", "10", "cat -v")
        room.tmux(
            "new-session", "-d", "-s", "room-3", "-x", "80", "-y", "10",
            "printf '\\033[?1000h\\033[?1006h'; cat -v",
        )
        time.sleep(0.3)
        server.send_keys("room-2", ["WheelUp"])
        server.send_keys("room-3", ["WheelUp", "WheelDown"])
        time.sleep(0.3)
        self.assertNotIn("<64;", room.tmux("capture-pane", "-p", "-t", "=room-2:").stdout)
        self.assertIn("^[[<64;40;3M^[[<65;40;3M", room.tmux("capture-pane", "-p", "-t", "=room-3:").stdout)
        room.tmux("kill-session", "-t", "=room-2")
        room.tmux("kill-session", "-t", "=room-3")

    def test_history_empty_before_scrollback_and_returns_lines_after(self):
        room.tmux("new-session", "-d", "-s", "room-4", "-x", "80", "-y", "10", "bash --norc --noprofile")
        try:
            time.sleep(0.3)
            self.assertEqual(server.history("room-4", 500), [])
            server.send_text("room-4", "seq -f 'HLINE_%02g' 1 25")
            server.send_keys("room-4", ["Enter"])
            time.sleep(0.5)
            lines = server.history("room-4", 500)
            self.assertTrue(any("HLINE_01" in ln for ln in lines), f"missing HLINE_01 in {lines[:5]}")
        finally:
            room.tmux("kill-session", "-t", "=room-4")


class SecurityAndConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "config.json"
        self.patched = mock.patch.dict(os.environ, {"ROOMDECK_CONFIG": str(self.path), "ROOMDECK_STATE": self.tmp.name})
        self.patched.start()

    def tearDown(self):
        self.patched.stop()
        self.tmp.cleanup()

    def write(self, data):
        self.path.write_text(json.dumps(data))

    def test_default_host_and_site_security(self):
        self.assertEqual(server.HOST, "127.0.0.1")
        self.write({})
        hosts, origins, devices = server.load_site()
        self.assertEqual(hosts, {"localhost", "127.0.0.1"})
        self.assertEqual(devices, set())
        self.assertEqual(server.load_commands(), server.DEFAULT_COMMANDS)

    def test_custom_commands_from_config(self):
        self.write({"commands": [{"id": "status", "label": "Status", "text": "/status"}]})
        self.assertEqual(server.load_commands(), [{"id": "status", "label": "Status", "text": "/status"}])

    def test_headers_and_traversal_blocked(self):
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_port}"
        try:
            with urllib.request.urlopen(f"{base}/") as response:
                self.assertEqual(response.headers["X-Frame-Options"], "DENY")
                self.assertEqual(response.headers["Content-Security-Policy"], "frame-ancestors 'none'")
            with urllib.request.urlopen(f"{base}/api/rooms") as r_res:
                payload = json.loads(r_res.read())
            self.assertIn("commands", payload)
            self.assertIn("buildId", payload)
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(f"{base}/static/../../etc/passwd")
            self.assertEqual(ctx.exception.code, 404)
            with self.assertRaises(urllib.error.HTTPError) as ctx_dir:
                urllib.request.urlopen(f"{base}/api/dirs?path=/etc")
            self.assertEqual(ctx_dir.exception.code, 400)
        finally:
            httpd.shutdown()


class PasteImageTest(unittest.TestCase):
    PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patched = mock.patch.dict(os.environ, {"ROOMDECK_STATE": self.tmp.name})
        self.patched.start()

    def tearDown(self):
        self.patched.stop()
        self.tmp.cleanup()

    def save(self, data, name="../../evil.sh", image=True):
        return Path(server.save_drop(name, len(data), io.BytesIO(data), image))

    def test_pasted_image_gets_random_name_and_owner_only_modes(self):
        path = self.save(self.PNG)
        self.assertEqual(path.read_bytes(), self.PNG)
        self.assertRegex(path.name, r"^paste-[0-9a-f]{8}\.png$")
        self.assertEqual(path.parent.parent, Path(self.tmp.name) / "drops")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    def test_non_image_is_refused(self):
        with self.assertRaises(ValueError):
            self.save(b"#!/bin/sh\nrm -rf ~\n")
        self.assertEqual([p for p in (Path(self.tmp.name) / "drops").rglob("*") if p.is_file()], [])

    def test_dropped_file_strips_directory_traversal(self):
        path = self.save(b"hello", image=False)
        self.assertEqual(path.name, "evil.sh")
        self.assertEqual(path.parent.parent, Path(self.tmp.name) / "drops")


class FrameDeltaTest(unittest.TestCase):
    def test_frame_delta_full_suppressed_cursor_only_and_shortened(self):
        f1 = {"cursor": [0, 0], "cols": 80, "rows": 24, "cwd": "/tmp", "alt": False, "wheel": False,
              "showCursor": True, "lines": ["a", "b", "c"]}
        d1 = server.frame_delta("main", f1, None)
        self.assertTrue(d1["full"])
        self.assertEqual(d1["lines"], {0: "a", 1: "b", 2: "c"})
        self.assertEqual(d1["total"], 3)
        self.assertIsNone(server.frame_delta("main", dict(f1, lines=["a", "b", "c"]), f1))
        f2 = dict(f1, cursor=[1, 0])
        d2 = server.frame_delta("main", f2, f1)
        self.assertFalse(d2["full"])
        self.assertEqual(d2["lines"], {})
        f3 = dict(f1, lines=["a", "X"])
        d3 = server.frame_delta("main", f3, f1)
        self.assertEqual(d3["lines"], {1: "X"})
        self.assertEqual(d3["total"], 2)


if __name__ == "__main__":
    unittest.main()
