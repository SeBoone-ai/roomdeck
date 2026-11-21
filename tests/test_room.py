import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roomdeck import room  # noqa: E402

APPROVAL_SCRIPT = "printf ' Do you want to proceed?\\n ❯ 1. Yes\\n   2. No\\n'; sleep 60"


def wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.1)
    return predicate()


class RoomTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        config = base / "config.json"
        config.write_text(json.dumps({"rooms": {"clients": {
            "idle": ["bash", "-c", "printf 'thinking about it\\n'; sleep 60"],
            "quick": ["true"],
            "asks": ["bash", "-c", APPROVAL_SCRIPT],
        }}}))
        self.env = mock.patch.dict(os.environ, {
            "ROOMDECK_TMUX_SOCKET": str(base / "tmux.sock"),
            "ROOMDECK_STATE": str(base / "state"),
            "ROOMDECK_CONFIG": str(config),
        })
        self.env.start()
        os.environ.pop("TMUX", None)
        os.environ.pop("TMUX_PANE", None)
        self.home = str(base)

    def tearDown(self):
        for row in room.sessions():
            room.tmux("kill-session", "-t", f"={row['name']}")
        self.env.stop()
        self.tmp.cleanup()

    def test_open_takes_smallest_free_work_room_and_main_is_fixed(self):
        self.assertEqual(room.open_room("idle", self.home), "room-1")
        self.assertEqual(room.open_room("idle", self.home), "room-2")
        self.assertEqual(room.open_room("shell", self.home, role="main"), "main")
        with self.assertRaises(room.RoomError) as caught:
            room.open_room("shell", self.home, role="main")
        self.assertEqual(caught.exception.code, room.EXIT_UNAVAILABLE)
        room.close_room("room-1", force=True)
        self.assertEqual(room.open_room("idle", self.home), "room-1")

    def test_open_records_client_folder_label_and_parent(self):
        parent = room.open_room("shell", self.home)
        pane = room.tmux("display-message", "-p", "-t", f"={parent}:", "#{pane_id}").stdout.strip()
        socket = os.environ["ROOMDECK_TMUX_SOCKET"]
        with mock.patch.dict(os.environ, {"TMUX": f"{socket},1,0", "TMUX_PANE": pane}):
            child = room.open_room("idle", self.home, name="  summary" + "x" * 80 + "  ")
        settled = lambda: os.path.realpath(next(r["cwd"] for r in room.sessions() if r["name"] == child)) == os.path.realpath(self.home)
        self.assertTrue(wait_for(settled))
        row = next(r for r in room.sessions() if r["name"] == child)
        self.assertEqual(row["parent"], parent)
        self.assertEqual(row["label"], ("summary" + "x" * 80)[:60])
        self.assertEqual(os.path.realpath(row["cwd"]), os.path.realpath(self.home))
        self.assertEqual(room.kind_of(child), "idle")

    def test_open_refuses_bad_input_before_starting_anything(self):
        for client, folder in (("nope", self.home), ("idle", "relative/path"), ("idle", "/no/such/dir")):
            with self.assertRaises(room.RoomError) as caught:
                room.open_room(client, folder)
            self.assertEqual(caught.exception.code, room.EXIT_INVALID)
        self.assertEqual(room.sessions(), [])

    def test_classify_reads_the_four_states(self):
        shell = room.open_room("shell", self.home)
        quick = room.open_room("quick", self.home)
        asks = room.open_room("asks", self.home)
        idle = room.open_room("idle", self.home)
        self.assertEqual(wait_for(lambda: room.classify(shell) == "input" and "input"), "input")
        self.assertEqual(wait_for(lambda: room.classify(quick) == "ended" and "ended"), "ended")
        self.assertEqual(wait_for(lambda: room.classify(asks) == "approval" and "approval"), "approval")
        self.assertEqual(room.classify(idle), "unknown")

    def test_classify_client_screens(self):
        codex = "› Ask Codex to do anything\n\n  GPT-6-Astra high · Context 80% left\n  ← for agents · ? for shor  ⚠ 2 · f2"
        agy = "────────────────\n>\n────────────────\n? for shortcuts    auto · Gemini 4 Hydrogen · xhigh"
        agy_bg = (
            "────────────────\n>\n────────────────\n"
            "  ● [21:43:48] task ... running\n"
            "────────────────\n? for shortcuts    Gemini 4 Neon · high · 1 task(s) · /tasks"
        )
        agy_trust = (
            "Do you trust the contents of this project?\n"
            "> Yes, I trust this folder\n  No, exit\n"
            "  ↑/↓ Navigate · enter Confirm\n    auto · Gemini 4 Neon · high"
        )
        grok_idle = (
            "  ╭──────────────────╮\n  │ ❯                │\n"
            "  ╰── Grok 4.7 (high) · always-approve ─╯\n  Shift+Tab:mode  │  Ctrl+x:shortcuts"
        )
        grok_running = (
            "   ⠋ Sleep… 7.7s   11s [stop]\n  ╭──────────────────╮\n  │ ❯                │\n"
            "  ╰── Grok 4.7 (high) · always-approve ─╯\n  Shift+Tab:mode  │  Ctrl+c:cancel  │  Ctrl+x:shortcuts"
        )
        grok_trust = "  Do you trust the contents of this directory?\n  Yes, proceed   y\n  No, quit   n\n  Grok Build 1.0.89"
        facts = {"dead": False, "command": "codex", "started": "", "exit": ""}
        for screen, kind, expected in (
            (codex, "shell", "input"),
            ("• Working (1m 02s • esc to interrupt)\n" + codex, "shell", "working"),
            (agy, "agy", "input"),
            (agy_bg, "agy", "working"),
            (agy_trust, "agy", "approval"),
            ("────────────────\n>\n────────────────\nesc to cancel    auto · Gemini 4 Hydrogen · xhigh", "agy", "working"),
            (grok_idle, "grok", "input"),
            (grok_running, "grok", "working"),
            (grok_trust, "grok", "approval"),
            ("unrecognized output", "shell", "unknown"),
            (codex, "grok", "unknown"),
            ("Do you want to proceed?\n❯ 1. Yes\n  2. No", "shell", "approval"),
        ):
            with self.subTest(kind=kind, expected=expected):
                self.assertEqual(room.classify_screen(screen, kind, facts), expected)
        self.assertEqual(room.classify_screen(codex, "shell", dict(facts, started="1", exit="0")), "ended")

    def test_close_needs_closing_mark_or_force_and_archives_inbox(self):
        name = room.open_room("idle", self.home)
        with self.assertRaises(room.RoomError) as caught:
            room.close_room(name)
        self.assertEqual(caught.exception.code, room.EXIT_REFUSED)
        inbox = room.state_dir() / "inbox" / name
        inbox.mkdir(parents=True)
        (inbox / "001-ASSIGN.txt").write_text("hello")
        room.tmux("set-option", "-t", f"={name}:", "@room_close_ok", "1")
        room.close_room(name)
        self.assertNotIn(name, [r["name"] for r in room.sessions()])
        archived = list((room.state_dir() / "archive").glob(f"{name}-*/001-ASSIGN.txt"))
        self.assertEqual(len(archived), 1)

    def test_names_are_checked_before_tmux_is_called(self):
        with mock.patch.object(room, "tmux") as fake:
            for bad in ("room-0", "room-100", "room-1;ls", "=main", "../x", "", "lane10", "room-01"):
                with self.assertRaises(room.RoomError):
                    room.close_room(bad)
            with self.assertRaises(room.RoomError):
                room.classify("a b")
        fake.assert_not_called()

    def test_cli_open_ls_and_close(self):
        script = str(Path(room.__file__))
        opened = subprocess.run(
            [sys.executable, script, "open", "idle", "--dir", self.home, "--detach", "--name", "draft"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(opened.returncode, 0, opened.stderr)
        self.assertEqual(opened.stdout.strip().splitlines()[-1], "room-1")
        listed = subprocess.run([sys.executable, script, "ls"], capture_output=True, text=True)
        self.assertEqual(listed.stdout.split("\t")[0], "room-1")
        self.assertIn("draft", listed.stdout)
        refused = subprocess.run([sys.executable, script, "close", "room-1"], capture_output=True, text=True)
        self.assertEqual(refused.returncode, room.EXIT_REFUSED)


if __name__ == "__main__":
    unittest.main()
