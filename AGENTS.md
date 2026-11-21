# AGENTS.md — RoomDeck Architecture & Invariants

## Architecture Map

| File | Responsibility |
|---|---|
| `roomdeck/room.py` | `tmux` session lifecycle (`open`, `ls`, `attach`, `classify`, `close`, `mark-closed`), input/approval/working screen classification, config loading |
| `roomdeck/server.py` | Stdlib `ThreadingHTTPServer`, SSE frame-delta streaming (`/api/stream`), text/key input (`/api/text`, `/api/keys` -> tmux `send-keys` / `load-buffer`), file/image drop (`/api/drop`), directory browser (`/api/dirs`), host/origin checks |
| `roomdeck/static/index.html` | App shell, sidebar (`USAGE`, `ROOMS`, `MACHINE`, font/theme controls), new-room modal |
| `roomdeck/static/themes.js` | 8 color themes (`THEMES`), CSS variable application (`applyTheme`) |
| `roomdeck/static/deck.css` | Layout, splitters, ANSI/wide-char line styling, `.agy-user` band, `.fold-head` / `.fold-hide`, mobile & embed modes |
| `roomdeck/static/deck.js` | `Pane` & `deck` state, ANSI/SGR parser, dock detection, `applyNoiseFolds`, clickable `findMenu`, IME/keyboard/mouse/touch input, drag-and-drop |
| `tests/` | `test_room.py` (tmux integration), `test_server.py` (HTTP/SSE/security), `test_themes_and_agy_band.py` (Node VM frontend tests) |

## Safe Extension Points

- **CLI clients & toolbar shortcuts**: Configured in `~/.config/roomdeck/config.json` (`rooms.clients`, `commands`) without modifying source code.
- **Custom themes**: Add entries to `THEMES` in `roomdeck/static/themes.js` following the existing palette shape (16 ANSI colors + optional light-mode UI tokens).
- **Client screen classifiers**: Extend `classify_client()` in `roomdeck/room.py` for new CLI TUIs.
- **Usage widget**: Point `config.json`'s `"usage_url"` to a local `http://127.0.0.1:<port>/...` endpoint returning `{"agents": [{"label", "ok", "stale", "windows": [{"win", "pct", "reset"}]}]}`.

## Security Invariants (Strict)

1. **Loopback bind by default**: `server.py` defaults to `HOST = "127.0.0.1"`. Never default to `0.0.0.0` or disable `Host` / `Origin` checks.
2. **No unauthenticated public exposure**: RoomDeck executes interactive shells and `tmux` commands. Remote access must go through an authenticated tunnel or reverse proxy (e.g. Tailscale Serve) with explicit `site.hosts` and `site.origins`.
3. **Strict input validation**:
   - Room names must match `ROOM_RE` (`main|watch|room-[1-9][0-9]?`) or `SESSION_RE` (`^[A-Za-z0-9_.-]{1,64}$`) before reaching `tmux`.
   - Keys sent to `/api/keys` must be in the `KEYS` allowlist.
   - `/api/dirs` must resolve within `Path.home()`.
   - `/api/drop` must strip directory components (`Path(name).name`), validate image headers when `image=1`, and write with `0o600` inside `0o700` per-drop directories.
   - `/static/*` must match `[a-z0-9-]+\.(html|css|js|png)`.
4. **Zero external runtime dependencies**: Keep `roomdeck/` 100% Python 3 stdlib + Vanilla JS/CSS + `tmux`.
