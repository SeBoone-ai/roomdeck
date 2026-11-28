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


class MobileArrowsAndMenuTests(unittest.TestCase):
    def test_index_cache_bust_and_sound_toggle(self):
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn("static/deck.css?v=2", html)
        self.assertIn("static/deck.js?v=2", html)
        self.assertIn('id="sound-toggle"', html)

    def test_nav_mode_toggle_and_api_keys_dispatch(self):
        themes_js = str(STATIC_DIR / "themes.js")
        deck_js = str(STATIC_DIR / "deck.js")
        run_node(f"""
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

function makeNode(tag = 'div', cls = '') {{
  const classes = new Set(cls ? cls.split(/\\s+/).filter(Boolean) : []);
  const children = [];
  const attrs = {{}};
  let text = '';
  return {{
    tagName: tag.toUpperCase(),
    children,
    hidden: false,
    title: '',
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
    setAttribute(k, v) {{ attrs[k] = String(v); }},
    getAttribute(k) {{ return attrs[k] ?? null; }},
    getBoundingClientRect() {{ return {{ width: 80, height: 18 }}; }},
    addEventListener() {{}},
    appendChild(c) {{ children.push(c); return c; }},
    append(...cs) {{ for (const c of cs) children.push(c); }},
    remove() {{}},
    set textContent(v) {{ children.length = 0; text = String(v); }},
    get textContent() {{ return text; }},
  }};
}}

const posted = [];
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
  location: {{ search: '' }},
  URLSearchParams,
  innerWidth: 390,
  matchMedia: () => ({{ matches: true, addEventListener: () => {{}} }}),
  devicePixelRatio: 1,
  NodeFilter: {{ SHOW_TEXT: 4 }},
  addEventListener: () => {{}},
  crypto: {{ randomUUID: () => 'uuid-1' }},
  fetch: async (url, init) => {{
    posted.push({{ url, body: JSON.parse(init.body) }});
    return {{ ok: true, status: 200, json: async () => ({{}}) }};
  }},
}});
vm.runInContext(fs.readFileSync({themes_js!r}, 'utf8'), ctx);
const deckSrc = fs.readFileSync({deck_js!r}, 'utf8').replace(/\\ndeck\\.init\\(\\);\\s*$/, '\\n');
vm.runInContext(deckSrc, ctx);
const d = vm.runInContext('({{ Pane, deck }})', ctx);

const p = Object.create(d.Pane.prototype);
p.deck = d.deck;
p.room = 'room-1';
p.answers = makeNode('div', 'answers');
p.navToggleBtn = makeNode('button', 'icon-btn nav-toggle');
p.cmdBar = makeNode('span', 'choices');
p.navKeys = makeNode('span', 'nav-keys');
p.navKeys.hidden = true;
const typedCalls = [];
p.typed = jump => typedCalls.push(jump);

p.syncCommands();
assert.equal(p.answers.hidden, false);
assert.equal(p.navToggleBtn.hidden, false);
assert.equal(p.answers.classList.contains('nav-mode'), false);

p.setNavMode(true);
assert.equal(p.answers.classList.contains('nav-mode'), true);
assert.equal(p.navKeys.hidden, false);

for (const k of ['Left', 'Up', 'Down', 'Right', 'Escape', 'Enter']) {{
  p.sendNavKey(k);
}}
await new Promise(r => setTimeout(r, 20));
assert.deepEqual(typedCalls, [false, false, false, false, false, true]);
assert.ok(posted.length >= 1);
assert.ok(posted.every(x => x.url === 'api/keys' && x.body.room === 'room-1'));
assert.deepEqual(posted.flatMap(x => x.body.keys), ['Left', 'Up', 'Down', 'Right', 'Escape', 'Enter']);
const postedBeforeGuard = posted.length;

p.room = null;
p.syncCommands();
assert.equal(p.navToggleBtn.hidden, true);
assert.equal(p.answers.classList.contains('nav-mode'), false);
assert.equal(p.navKeys.hidden, true);
p.setNavMode(true);
assert.equal(p.answers.classList.contains('nav-mode'), false);
p.sendNavKey('Up');
await new Promise(r => setTimeout(r, 10));
assert.equal(posted.length, postedBeforeGuard);
""")

    def test_menu_pane_dropdown_and_serialize(self):
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
  const node = {{
    tagName: tag.toUpperCase(),
    children,
    parentElement: null,
    hidden: false,
    title: '',
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
    setAttribute() {{}},
    getBoundingClientRect() {{ return {{ width: 80, height: 18 }}; }},
    addEventListener() {{}},
    appendChild(c) {{
      if (c.parentElement && c.parentElement !== node) {{
        const i = c.parentElement.children.indexOf(c);
        if (i >= 0) c.parentElement.children.splice(i, 1);
      }}
      c.parentElement = node;
      children.push(c);
      return c;
    }},
    insertBefore(c, ref) {{
      if (c.parentElement && c.parentElement !== node) {{
        const i = c.parentElement.children.indexOf(c);
        if (i >= 0) c.parentElement.children.splice(i, 1);
      }}
      c.parentElement = node;
      const idx = ref ? children.indexOf(ref) : -1;
      if (idx < 0) children.push(c);
      else children.splice(idx, 0, c);
      return c;
    }},
    append(...cs) {{ for (const c of cs) node.appendChild(c); }},
    remove() {{}},
    set textContent(v) {{ children.length = 0; text = String(v); }},
    get textContent() {{ return text; }},
  }};
  if (tag === 'select') {{
    let selected = '';
    Object.defineProperty(node, 'value', {{
      get() {{ return selected; }},
      set(v) {{ selected = children.some(o => o.value === v) ? v : ''; }},
    }});
  }}
  return node;
}}

const app = makeNode('div');
const side = makeNode('aside');
const resizer = makeNode('div');
const panes = makeNode('main');
app.append(side, resizer, panes);
const ids = {{
  app,
  side,
  'side-resizer': resizer,
  panes,
  'v-room': makeNode('div'),
}};
const ctx = vm.createContext({{
  document: {{
    documentElement: makeNode('html'),
    createElement: tag => makeNode(tag),
    getElementById: id => ids[id] || null,
    addEventListener: () => {{}},
  }},
  window: {{}},
  localStorage: {{ getItem: () => null, setItem: () => {{}} }},
  sessionStorage: {{ getItem: () => 'test-win', setItem: () => {{}} }},
  location: {{ search: '' }},
  URLSearchParams,
  innerWidth: 390,
  matchMedia: () => ({{ matches: true, addEventListener: () => {{}} }}),
  devicePixelRatio: 1,
  NodeFilter: {{ SHOW_TEXT: 4 }},
  ResizeObserver: class {{ observe() {{}} }},
  setTimeout,
  clearTimeout,
  addEventListener: () => {{}},
  crypto: {{ randomUUID: () => 'uuid-1' }},
}});
vm.runInContext(fs.readFileSync({themes_js!r}, 'utf8'), ctx);
const deckSrc = fs.readFileSync({deck_js!r}, 'utf8').replace(/\\ndeck\\.init\\(\\);\\s*$/, '\\n');
vm.runInContext(deckSrc, ctx);
const d = vm.runInContext('({{ Pane, deck, MENU_OPTION }})', ctx);

const p1 = new d.Pane(d.deck);
d.deck.root = {{ pane: p1 }};
d.deck.panes = [p1];
d.deck.active = p1;
d.deck.rooms = [{{ name: 'main', label: '', state: 'input', room: true }}];
d.deck.resubscribe = () => {{}};

d.deck.renderRooms();
assert.equal(p1.select.children[1].value, d.MENU_OPTION);
assert.equal(p1.select.children[1].textContent, 'Menu');

d.deck.openMenu(p1);
assert.equal(p1.isMenuPane, true);
assert.equal(p1.select.value, d.MENU_OPTION);
assert.equal(p1.answers.hidden, true);
assert.equal(side.parentElement, p1.menuSlot);
assert.equal(JSON.stringify(d.deck.serialize(d.deck.root)), JSON.stringify({{ menu: true }}));

p1.show('main', false);
assert.equal(p1.isMenuPane, false);
assert.equal(side.parentElement, app);
assert.equal(p1.select.value, 'main');
assert.equal(JSON.stringify(d.deck.serialize(d.deck.root)), JSON.stringify({{ room: 'main' }}));
""")

    def test_attention_sound_chime_triggers_and_toggle(self):
        themes_js = str(STATIC_DIR / "themes.js")
        deck_js = str(STATIC_DIR / "deck.js")
        run_node(f"""
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

function makeNode(tag = 'div') {{
  return {{
    tagName: tag.toUpperCase(),
    children: [],
    textContent: '',
    title: '',
    value: '',
    style: {{ setProperty() {{}}, removeProperty() {{}} }},
    classList: {{ add() {{}}, remove() {{}}, toggle() {{ return false; }}, contains() {{ return false; }} }},
    appendChild(c) {{ this.children.push(c); return c; }},
    addEventListener() {{}},
  }};
}}

const storage = new Map();
const soundBtn = makeNode('button');
const ids = {{
  'sound-toggle': soundBtn,
  'fs-base': makeNode('span'),
  'fs-down': makeNode('button'),
  'fs-up': makeNode('button'),
  'theme-select': makeNode('select'),
}};
const ctx = vm.createContext({{
  document: {{
    documentElement: makeNode('html'),
    createElement: tag => makeNode(tag),
    getElementById: id => ids[id] || null,
    addEventListener: () => {{}},
  }},
  window: {{}},
  localStorage: {{
    getItem: k => storage.has(k) ? storage.get(k) : null,
    setItem: (k, v) => storage.set(k, String(v)),
  }},
  sessionStorage: {{ getItem: () => 'test-win', setItem: () => {{}} }},
  location: {{ search: '' }},
  URLSearchParams,
  matchMedia: () => ({{ matches: false, addEventListener: () => {{}} }}),
  devicePixelRatio: 1,
  addEventListener: () => {{}},
  crypto: {{ randomUUID: () => 'uuid-1' }},
}});
vm.runInContext(fs.readFileSync({themes_js!r}, 'utf8'), ctx);
const deckSrc = fs.readFileSync({deck_js!r}, 'utf8').replace(/\\ndeck\\.init\\(\\);\\s*$/, '\\n');
vm.runInContext(deckSrc, ctx);
const deckObj = vm.runInContext('deck', ctx);

let chimes = 0;
deckObj.playChime = () => {{ chimes += 1; }};
deckObj.bindView();
assert.equal(soundBtn.textContent, '🔔');

deckObj.rooms = [{{ name: 'main', state: 'working' }}, {{ name: 'room-1', state: 'working' }}];
deckObj.checkAttentionSound();
assert.equal(chimes, 0);

deckObj.rooms = [{{ name: 'main', state: 'input' }}, {{ name: 'room-1', state: 'working' }}];
deckObj.checkAttentionSound();
assert.equal(chimes, 1);

deckObj.rooms = [{{ name: 'main', state: 'input' }}, {{ name: 'room-1', state: 'approval' }}];
deckObj.checkAttentionSound();
assert.equal(chimes, 2);

soundBtn.onclick();
assert.equal(soundBtn.textContent, '🔕');
assert.equal(storage.get('sound'), 'false');
soundBtn.onclick();
assert.equal(soundBtn.textContent, '🔔');
assert.equal(chimes, 3);
""")
