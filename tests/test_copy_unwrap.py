import json
import subprocess
from pathlib import Path

DECK_JS = Path(__file__).resolve().parents[1] / "roomdeck" / "static" / "deck.js"


def _run_join(lines: list[str], cols: int) -> str:
    src = DECK_JS.read_text(encoding="utf-8")
    wide_line = next(ln for ln in src.splitlines() if ln.startswith("const WIDE ="))
    start = src.index("function cellWidth(")
    end = src.index("\nfunction color256(")
    snippet = f"{wide_line}\n{src[start:end]}"
    pieces = [{"full": ln.rstrip(), "part": ln.rstrip()} for ln in lines]
    script = (
        f"{snippet}\n"
        f"const pieces = {json.dumps(pieces, ensure_ascii=False)};\n"
        f"process.stdout.write(joinSelectedLines(pieces, {cols}));\n"
    )
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    return res.stdout


def test_tui_indented_command_unwraps_cleanly():
    lines = [
        "    gh release create v0.1.0",
        "    /mnt/c/Users/example/Downloads/2026-11-21_roomdeck-v0.1.0.zip#roomdeck-v0.1.",
        '    0.zip -R org/roomdeck --title "RoomDeck v0.1.0" --notes',
        '    "Git不要で使えるZIP版です。解凍してAIエージェントにフォルダを渡すだけでセッ',
        '    トアップできます。" && gh repo edit org/roomdeck --visibility public',
        "    --accept-visibility-change-consequences",
    ]
    out = _run_join(lines, cols=140)
    assert "\n" not in out
    assert (
        out.strip()
        == 'gh release create v0.1.0 /mnt/c/Users/example/Downloads/2026-11-21_roomdeck-v0.1.0.zip#roomdeck-v0.1.0.zip'
        ' -R org/roomdeck --title "RoomDeck v0.1.0" --notes'
        ' "Git不要で使えるZIP版です。解凍してAIエージェントにフォルダを渡すだけでセットアップできます。"'
        " && gh repo edit org/roomdeck --visibility public --accept-visibility-change-consequences"
    )


def test_unindented_shell_output_preserves_newlines():
    cols = 80
    long_path = "/" + "p" * (cols - 4)
    lines = ["short1", long_path, "next"]
    assert _run_join(lines, cols=cols) == f"short1\n{long_path}\nnext"


def test_indented_bullets_and_short_commands_preserve_newlines():
    lines = [
        "    - 項目1です",
        "    - 項目2です",
    ]
    assert _run_join(lines, cols=120) == "    - 項目1です\n    - 項目2です"

    short_cmds = [
        "    git add foo.txt",
        '    git commit -m "msg"',
    ]
    assert _run_join(short_cmds, cols=120) == '    git add foo.txt\n    git commit -m "msg"'
