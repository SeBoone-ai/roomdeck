import pathlib
import subprocess
import unittest

STATIC_DIR = pathlib.Path(__file__).resolve().parents[1] / "roomdeck" / "static"


def run_node(script: str) -> None:
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(f"node exited {proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")


class ThemesAndFrontendTests(unittest.TestCase):
    def test_themes_palette_and_light_vars(self):
        themes_js = str(STATIC_DIR / "themes.js")
        run_node(f"""
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const props = new Map();
const docEl = {{
  style: {{
    colorScheme: '',
    setProperty(k, v) {{ props.set(k, v); }},
    removeProperty(k) {{ props.delete(k); }},
  }},
}};
const ctx = vm.createContext({{
  document: {{ documentElement: docEl }},
  localStorage: {{ getItem: () => null, setItem: () => {{}} }},
  addEventListener: () => {{}},
}});
vm.runInContext(fs.readFileSync({themes_js!r}, 'utf8'), ctx);
const t = vm.runInContext('({{ THEMES, applyTheme }})', ctx);

const expected = ['navy', 'light', 'black', 'tokyo', 'mocha', 'nord', 'solarized', 'paper'];
assert.deepEqual(Object.keys(t.THEMES), expected);
for (const k of expected) {{
  assert.equal(t.THEMES[k].palette.length, 16, `${{k}} palette length`);
}}

t.applyTheme('paper');
assert.equal(docEl.style.colorScheme, 'light');
assert.equal(props.get('--bg'), '#fbf7ef');
assert.equal(props.get('--c8bg'), '#e5dccb');

t.applyTheme('tokyo');
assert.equal(docEl.style.colorScheme, 'dark');
assert.equal(props.get('--bg'), '#1a1b26');
assert.equal(props.has('--c8bg'), false);
""")

    def test_agy_band_noise_folds_and_find_menu(self):
        themes_js = str(STATIC_DIR / "themes.js")
        deck_js = str(STATIC_DIR / "deck.js")
        run_node(f"""
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

function makeNode(tag = 'div', cls = '') {{
  const classes = new Set(cls ? cls.split(/\\s+/).filter(Boolean) : []);
  const children = [];
  let text = '';
  return {{
    tagName: tag.toUpperCase(),
    children,
    style: {{ setProperty() {{}}, removeProperty() {{}} }},
    dataset: {{}},
    classList: {{
      add(c) {{ classes.add(c); }},
      remove(c) {{ classes.delete(c); }},
      toggle(c, force) {{
        if (force === undefined) {{
          if (classes.has(c)) {{ classes.delete(c); return false; }}
          classes.add(c); return true;
        }}
        if (force) classes.add(c); else classes.delete(c);
        return Boolean(force);
      }},
      contains(c) {{ return classes.has(c); }},
    }},
    get className() {{ return [...classes].join(' '); }},
    set className(v) {{ classes.clear(); for (const c of String(v).split(/\\s+/).filter(Boolean)) classes.add(c); }},
    get childElementCount() {{ return children.length; }},
    get lastChild() {{ return children[children.length - 1] || null; }},
    appendChild(c) {{ children.push(c); return c; }},
    append(...cs) {{ for (const c of cs) children.push(c); }},
    remove() {{}},
    set textContent(v) {{ children.length = 0; text = String(v); }},
    get textContent() {{
      if (!children.length) return text;
      return children.map(c => c.nodeType === 3 ? c.data : c.textContent).join('');
    }},
  }};
}}

const ctx = vm.createContext({{
  document: {{
    documentElement: makeNode('html'),
    createElement: tag => makeNode(tag),
    createTextNode: data => ({{ nodeType: 3, data }}),
    createTreeWalker: () => ({{ nextNode: () => false }}),
    addEventListener: () => {{}},
  }},
  window: {{}},
  localStorage: {{ getItem: () => null, setItem: () => {{}} }},
  sessionStorage: {{ getItem: () => 'test-win', setItem: () => {{}} }},
  location: {{ search: '?embed=1&room=room-1' }},
  URLSearchParams,
  innerWidth: 1280,
  matchMedia: () => ({{ matches: false, addEventListener: () => {{}} }}),
  devicePixelRatio: 1,
  NodeFilter: {{ SHOW_TEXT: 4 }},
  addEventListener: () => {{}},
  crypto: {{ randomUUID: () => 'uuid-1' }},
}});
vm.runInContext(fs.readFileSync({themes_js!r}, 'utf8'), ctx);
const deckSrc = fs.readFileSync({deck_js!r}, 'utf8').replace(/\\ndeck\\.init\\(\\);\\s*$/, '\\n');
vm.runInContext(deckSrc, ctx);
const d = vm.runInContext('({{ BASE, parseLine, isAgyUserSegs, renderLine, applyNoiseFolds, Pane, FORCE_EMBED, EMBED_ROOM }})', ctx);

assert.equal(d.FORCE_EMBED, true);
assert.equal(d.EMBED_ROOM, 'room-1');

const st1 = {{ ...d.BASE }};
const segs1 = d.parseLine('\\x1b[1m\\x1b[34m> hello agy\\x1b[0m', st1);
assert.equal(d.isAgyUserSegs(segs1, false), true);
const ln1 = makeNode('div', 'ln');
d.renderLine(ln1, segs1, true);
assert.equal(ln1.classList.contains('agy-user'), true);
assert.equal(ln1.children[0].className, 'agy-caret');
assert.equal(ln1.textContent, '> hello agy');

function makePane(client) {{
  const p = Object.create(d.Pane.prototype);
  p.room = 'r1';
  p.deck = {{ rooms: [{{ name: 'r1', client }}] }};
  p.live = makeNode('div', 'live');
  p.dock = makeNode('div', 'dock');
  p.keys = [];
  p.dockStart = 0;
  p.alt = false;
  p.raw = [
    '\\x1b[1m\\x1b[34m> user prompt\\x1b[0m',
    '▸ Thought for 1s',
    '▸ Read file.txt',
    'AI response',
    '────────────────────',
    '\\x1b[1m\\x1b[34m> active input\\x1b[0m',
    '────────────────────',
  ];
  p.syncMenuMarks = () => {{}};
  return p;
}}

const agyPane = makePane('agy');
agyPane.render();
assert.equal(agyPane.live.children[0].classList.contains('agy-user'), true);
assert.equal(agyPane.live.children[1].classList.contains('fold-head'), true);
assert.equal(agyPane.live.children[2].classList.contains('fold-hide'), true);
assert.equal(agyPane.dock.children[1].classList.contains('agy-user'), false);

const menuPane = makePane('claude');
menuPane.raw = ['Do you want to proceed?', '❯ 1. Yes', '  2. No'];
menuPane.dockStart = menuPane.raw.length;
const menu = menuPane.findMenu();
assert.ok(menu);
assert.equal(menu.current, 0);
assert.equal(menu.items.length, 2);
""")


if __name__ == "__main__":
    unittest.main()
