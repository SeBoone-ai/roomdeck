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


def _run_join_pieces(pieces: list[dict[str, str]], cols: int) -> str:
    src = DECK_JS.read_text(encoding="utf-8")
    wide_line = next(ln for ln in src.splitlines() if ln.startswith("const WIDE ="))
    start = src.index("function cellWidth(")
    end = src.index("\nfunction color256(")
    snippet = f"{wide_line}\n{src[start:end]}"
    script = (
        f"{snippet}\n"
        f"const pieces = {json.dumps(pieces, ensure_ascii=False)};\n"
        f"process.stdout.write(joinSelectedLines(pieces, {cols}));\n"
    )
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    return res.stdout


def test_wrapped_url_unwraps_on_copy_and_preserves_non_wraps():
    assert (
        _run_join(
            [
                "  URL: https://example.org.",
                "  example/board/browser/",
            ],
            cols=120,
        )
        == "  URL: https://example.org.example/board/browser/"
    )
    assert (
        _run_join(
            [
                "  - https://example.org.",
                "    example/board/browser/ を開く",
                "  - 次の項目",
            ],
            cols=120,
        )
        == "  - https://example.org.example/board/browser/ を開く\n  - 次の項目"
    )
    assert (
        _run_join(
            [
                "  https://github.com/org-name/example-",
                "  repo/pull/639?tab=files&w=",
                "  1",
            ],
            cols=120,
        )
        == "  https://github.com/org-name/example-repo/pull/639?tab=files&w=1"
    )
    assert (
        _run_join(
            [
                "─" * 70,
                "https://docs.example.com/spreadsheets/d/AAAAAAAAAAAAAAAAAAAAAAAAAA",
                "BBBBBBBBBBBBBBBBBB/edit",
                "─" * 70,
            ],
            cols=70,
        )
        == ("─" * 70)
        + "\nhttps://docs.example.com/spreadsheets/d/AAAAAAAAAAAAAAAAAAAAAAAAAABBBBBBBBBBBBBBBBBB/edit\n"
        + ("─" * 70)
    )
    assert (
        _run_join(
            [
                "Here is the link you asked for: https://example.com/docs/overview",
                "Please check the report tomorrow.",
            ],
            cols=70,
        )
        == "Here is the link you asked for: https://example.com/docs/overview\nPlease check the report tomorrow."
    )
    assert (
        _run_join(
            [
                "Here is the link you asked for: https://example.com/docs/overview",
                "and let me know what you think.",
            ],
            cols=70,
        )
        == "Here is the link you asked for: https://example.com/docs/overview\nand let me know what you think."
    )
    assert (
        _run_join(
            [
                "https://a.example/one",
                "https://b.example/two",
            ],
            cols=120,
        )
        == "https://a.example/one\nhttps://b.example/two"
    )
    assert (
        _run_join(
            [
                "See https://example.com.",
                "This is a new sentence.",
            ],
            cols=120,
        )
        == "See https://example.com.\nThis is a new sentence."
    )
    assert (
        _run_join(
            [
                "https://example.com/",
                "確認をお願いします",
            ],
            cols=120,
        )
        == "https://example.com/\n確認をお願いします"
    )


def test_linkify_container_joins_wrapped_urls_across_rows_and_streams():
    deck_js = str(DECK_JS)
    script = f"""
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

function createMiniDom() {{
  class Node {{
    constructor(type) {{ this.nodeType = type; this.parentNode = null; this.childNodes = []; }}
    get parentElement() {{ return this.parentNode && this.parentNode.nodeType === 1 ? this.parentNode : null; }}
    get firstChild() {{ return this.childNodes[0] || null; }}
    get children() {{ return this.childNodes.filter(c => c.nodeType === 1); }}
    contains(other) {{
      let cur = other;
      while (cur) {{ if (cur === this) return true; cur = cur.parentNode; }}
      return false;
    }}
    appendChild(child) {{
      if (child.parentNode) child.remove();
      child.parentNode = this;
      this.childNodes.push(child);
      return child;
    }}
    insertBefore(child, ref) {{
      if (child.parentNode) child.remove();
      child.parentNode = this;
      const idx = ref ? this.childNodes.indexOf(ref) : -1;
      if (idx < 0) this.childNodes.push(child);
      else this.childNodes.splice(idx, 0, child);
      return child;
    }}
    remove() {{
      if (!this.parentNode) return;
      const idx = this.parentNode.childNodes.indexOf(this);
      if (idx >= 0) this.parentNode.childNodes.splice(idx, 1);
      this.parentNode = null;
    }}
    replaceWith(...nodes) {{
      const p = this.parentNode;
      if (!p) return;
      for (const n of nodes) p.insertBefore(n, this);
      this.remove();
    }}
    after(...nodes) {{
      const p = this.parentNode;
      if (!p) return;
      const idx = p.childNodes.indexOf(this);
      const ref = p.childNodes[idx + 1] || null;
      for (const n of nodes) p.insertBefore(n, ref);
    }}
    normalize() {{
      for (let i = 0; i < this.childNodes.length; i++) {{
        const c = this.childNodes[i];
        if (c.nodeType === 3) {{
          if (!c.data) {{ c.remove(); i--; continue; }}
          if (i > 0 && this.childNodes[i - 1].nodeType === 3) {{
            this.childNodes[i - 1].data += c.data;
            c.remove();
            i--;
          }}
        }} else {{
          c.normalize();
        }}
      }}
    }}
  }}
  class Text extends Node {{
    constructor(data) {{ super(3); this.data = String(data); }}
    get textContent() {{ return this.data; }}
    set textContent(v) {{ this.data = String(v); }}
  }}
  class Element extends Node {{
    constructor(tag) {{
      super(1);
      this.tagName = tag.toUpperCase();
      this.className = '';
      this.dataset = {{}};
      this.style = {{ setProperty() {{}} }};
      this.href = '';
      this.classList = {{
        add: c => {{ const s = new Set(this.className.split(/\\s+/).filter(Boolean)); s.add(c); this.className = [...s].join(' '); }},
        remove: c => {{ const s = new Set(this.className.split(/\\s+/).filter(Boolean)); s.delete(c); this.className = [...s].join(' '); }},
        toggle: (c, f) => {{ const has = this.classList.contains(c); const on = f === undefined ? !has : Boolean(f); if (on) this.classList.add(c); else this.classList.remove(c); return on; }},
        contains: c => this.className.split(/\\s+/).includes(c),
      }};
    }}
    get textContent() {{ return this.childNodes.map(c => c.textContent).join(''); }}
    set textContent(v) {{
      for (const c of [...this.childNodes]) c.remove();
      const s = String(v);
      if (s) this.appendChild(new Text(s));
    }}
    matches(sel) {{
      if (sel === 'a.u') return this.tagName === 'A' && this.classList.contains('u');
      if (sel === 'a.u[data-url-group]') return this.matches('a.u') && Boolean(this.dataset.urlGroup);
      if (sel === '.ln') return this.classList.contains('ln');
      return false;
    }}
    closest(sel) {{
      let cur = this;
      while (cur) {{ if (cur.nodeType === 1 && cur.matches(sel)) return cur; cur = cur.parentNode; }}
      return null;
    }}
    querySelectorAll(sel) {{
      const out = [];
      const walk = n => {{
        for (const c of n.childNodes) {{
          if (c.nodeType === 1) {{ if (c.matches(sel)) out.push(c); walk(c); }}
        }}
      }};
      walk(this);
      return out;
    }}
  }}
  const document = {{
    documentElement: new Element('html'),
    createElement: tag => new Element(tag),
    createTextNode: data => new Text(data),
    createTreeWalker(root, mask) {{
      const list = [];
      const walk = n => {{
        for (const c of n.childNodes) {{
          if (c.nodeType === 3 && (mask & 4)) list.push(c);
          if (c.nodeType === 1) walk(c);
        }}
      }};
      walk(root);
      let idx = -1;
      return {{
        currentNode: root,
        nextNode() {{ idx += 1; if (idx >= list.length) return false; this.currentNode = list[idx]; return true; }},
      }};
    }},
    addEventListener() {{}},
    getElementById: () => null,
  }};
  return {{ document, Element }};
}}

const {{ document, Element }} = createMiniDom();
const ctx = vm.createContext({{
  document,
  window: {{ getSelection: () => ({{ isCollapsed: true }}) }},
  localStorage: {{ getItem: () => null, setItem: () => {{}} }},
  sessionStorage: {{ getItem: () => 'w1', setItem: () => {{}} }},
  location: {{ search: '' }},
  URLSearchParams,
  matchMedia: () => ({{ matches: false, addEventListener: () => {{}} }}),
  devicePixelRatio: 1,
  NodeFilter: {{ SHOW_TEXT: 4 }},
  ResizeObserver: class {{ observe() {{}} }},
  addEventListener: () => {{}},
  crypto: {{ randomUUID: () => 'u1' }},
}});
const src = fs.readFileSync({deck_js!r}, 'utf8').replace(/\\ndeck\\.init\\(\\);\\s*$/, '\\n');
vm.runInContext(src, ctx);
const api = vm.runInContext('({{ renderParsedLines, linkifyContainer }})', ctx);

const live = new Element('div');
const lines1 = ['  Link: (https://example.org.'];
const keys = [];
for (let i = 0; i < lines1.length; i++) {{ const d = document.createElement('div'); d.className = 'ln'; live.appendChild(d); }}
api.renderParsedLines(lines1, {{ keys, getLine: i => live.children[i] }});
api.linkifyContainer(live, 100);
assert.equal(live.children[0].querySelectorAll('a.u')[0].dataset.url, 'https://example.org');

const lines2 = [
  '  Link: (https://example.org.',
  '  example/board/browser/) を確認してください',
  '  Other: https://example.com.',
  '  Next paragraph starts here.',
];
while (live.children.length < lines2.length) {{ const d = document.createElement('div'); d.className = 'ln'; live.appendChild(d); }}
api.renderParsedLines(lines2, {{ keys, getLine: i => live.children[i] }});
api.linkifyContainer(live, 100);

const row0Links = live.children[0].querySelectorAll('a.u');
const row1Links = live.children[1].querySelectorAll('a.u');
assert.equal(row0Links.length, 1);
assert.equal(row1Links.length, 1);
assert.equal(row0Links[0].textContent, 'https://example.org.');
assert.equal(row1Links[0].textContent, 'example/board/browser/');
assert.equal(row0Links[0].href, 'https://example.org.example/board/browser/');
assert.equal(row1Links[0].href, 'https://example.org.example/board/browser/');
assert.equal(row0Links[0].dataset.urlGroup, row1Links[0].dataset.urlGroup);
assert.ok(row0Links[0].dataset.urlGroup);
assert.equal(live.children[1].textContent, '  example/board/browser/) を確認してください');

const row2Links = live.children[2].querySelectorAll('a.u');
const row3Links = live.children[3].querySelectorAll('a.u');
assert.equal(row2Links.length, 1);
assert.equal(row2Links[0].href, 'https://example.com');
assert.equal(row2Links[0].textContent, 'https://example.com');
assert.equal(row3Links.length, 0);

const liveAnsi = new Element('div');
const rawAnsi = [
  '\\x1b[4mhttps://example.com/some-long-pag\\x1b[0m',
  '\\x1b[4metitle\\x1b[0m',
  '\\x1b]8;;https://docs.example.org/spec/full-target\\x07https://docs.example.org/spec/full-\\x1b]8;;\\x07',
  '\\x1b]8;;https://docs.example.org/spec/full-target\\x07target\\x1b]8;;\\x07',
];
const keysAnsi = [];
for (let i = 0; i < rawAnsi.length; i++) {{ const d = document.createElement('div'); d.className = 'ln'; liveAnsi.appendChild(d); }}
api.renderParsedLines(rawAnsi, {{ keys: keysAnsi, getLine: i => liveAnsi.children[i] }});
api.linkifyContainer(liveAnsi, 180);

const u0 = liveAnsi.children[0].querySelectorAll('a.u')[0];
const u1 = liveAnsi.children[1].querySelectorAll('a.u')[0];
assert.equal(u0.href, 'https://example.com/some-long-pagetitle');
assert.equal(u1.href, 'https://example.com/some-long-pagetitle');
assert.equal(u0.dataset.urlGroup, u1.dataset.urlGroup);

const o0 = liveAnsi.children[2].querySelectorAll('a.u')[0];
const o1 = liveAnsi.children[3].querySelectorAll('a.u')[0];
assert.equal(o0.href, 'https://docs.example.org/spec/full-target');
assert.equal(o1.href, 'https://docs.example.org/spec/full-target');
assert.equal(o0.dataset.urlGroup, o1.dataset.urlGroup);
assert.ok(o0.dataset.urlGroup);
"""
    proc = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"


def test_narrow_pane_wrapped_code_unwraps_and_preserves_command_boundaries():
    cmd_lines = [
        "    Add-WindowsCapability -Online -Name",
        "    OpenSSH.Server~~~~0.0.1.0",
        "    Start-Service sshd",
        '    New-NetFirewallRule -Name "DemoTempSSH"',
        '    -DisplayName "Demo Temp SSH" -Enabled True',
    ]
    cmd_expected = "\n".join([
        "    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0",
        "    Start-Service sshd",
        '    New-NetFirewallRule -Name "DemoTempSSH" -DisplayName "Demo Temp SSH" -Enabled True',
    ])
    for cols in (53, 55, 120):
        assert _run_join(cmd_lines, cols=cols) == cmd_expected, f"cmd_lines failed at cols={cols}"

    key_lines = [
        '    "C:\\ProgramData\\ssh\\administrators_authorized_key',
        '    s" -Value "ssh-ed25519',
        "    AAAAC3NzaC1lZDI1NTE5AAAAIExampleKeyDataForTest000",
        '    R6EqLU+PNDQb5+mgiLL demo-user@workstation"',
    ]
    key_expected = (
        '    "C:\\ProgramData\\ssh\\administrators_authorized_keys" -Value "ssh-ed25519'
        ' AAAAC3NzaC1lZDI1NTE5AAAAIExampleKeyDataForTest000R6EqLU+PNDQb5+mgiLL demo-user@workstation"'
    )
    for cols in (53, 55, 120):
        assert _run_join(key_lines, cols=cols) == key_expected, f"key_lines failed at cols={cols}"


def test_narrow_pane_partial_first_line_selection_and_short_lists():
    pieces = [
        {
            "full": "    Add-WindowsCapability -Online -Name",
            "part": "Add-WindowsCapability -Online -Name",
        },
        {
            "full": "    OpenSSH.Server~~~~0.0.1.0",
            "part": "    OpenSSH.Server~~~~0.0.1.0",
        },
    ]
    for cols in (53, 120):
        assert (
            _run_join_pieces(pieces, cols=cols)
            == "Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0"
        )

    assert _run_join(["foo", "bar"], cols=53) == "foo\nbar"
    assert _run_join(["ls", "pwd"], cols=53) == "ls\npwd"
    assert _run_join(["    ls", "    pwd"], cols=53) == "    ls\n    pwd"
    assert _run_join(["    - item 1", "    - item 2"], cols=53) == "    - item 1\n    - item 2"
