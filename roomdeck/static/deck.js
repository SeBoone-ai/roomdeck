'use strict';

const WIDE = /[ᄀ-ᅟ⺀-〾ぁ-㏿㐀-䶿一-鿿ꀀ-꓏가-힣豈-﫿︰-﹏＀-｠￠-￦\u{1F300}-\u{1F64F}\u{1F900}-\u{1F9FF}\u{20000}-\u{3FFFD}]/u;
const ESC = /\x1b\[([0-9;:?<>=]*)[ -/]*([@-~])|\x1b\]([\s\S]*?)(?:\x07|\x1b\\)|\x1b[P^_][\s\S]*?\x1b\\|\x1b[@-Z\\-_]|[\x00-\x08\x0b-\x1f\x7f]/g;
const URL_RE = /https?:\/\/[^\s"'<>`\u3000-\u303f\uff00-\uffef]+/g;
const KEYMAP = {
  Escape: 'Escape', Backspace: 'BSpace', Delete: 'DC', ArrowUp: 'Up', ArrowDown: 'Down',
  ArrowLeft: 'Left', ArrowRight: 'Right', Home: 'Home', End: 'End', PageUp: 'PageUp', PageDown: 'PageDown',
};
const ICONS = {
  dpad: '<path d="M12 3v18M3 12h18M9 6l3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3"/>',
};
function iconButton(paths, title) {
  const b = el('button', 'icon-btn');
  b.title = title;
  b.setAttribute('aria-label', title);
  b.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
  return b;
}
const CLIENT_LABELS = { claude: 'Claude', codex: 'Codex', agy: 'Antigravity', grok: 'Grok', shell: 'Shell' };
const RENAME = '__rename';
const MENU_OPTION = '__menu';
const STATE_LABELS = { working: 'Working', input: 'Input', approval: 'Approval', standby: 'Idle', ended: 'Ended', unknown: 'Unknown' };
const BASE = { fg: null, bg: null, bold: false, dim: false, italic: false, underline: false, inverse: false, oscUrl: null };
const HISTORY_STEP = 500;
const HISTORY_MAX = 2000;
const NARROW = 700;

const store = {
  get(key, fallback) { try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage unavailable */ } },
};
const queryParams = new URLSearchParams(location.search);
const slot = queryParams.get('w') || '1';
const FORCE_MOBILE = queryParams.get('mobile') === '1';
const FORCE_EMBED = queryParams.get('embed') === '1';
const EMBED_ROOM = queryParams.get('room') || '';
const FS_MIN = 10;
const FS_MAX = 40;
const clampFs = px => Math.max(FS_MIN, Math.min(FS_MAX, Math.round(px)));
const narrowQuery = matchMedia(`(max-width: ${NARROW - 1}px)`);
const isMobile = () => FORCE_MOBILE || narrowQuery.matches;
const baseFs = () => clampFs(isMobile() ? store.get('fsBaseMobile', 15) : store.get('fsBase', 16));
const metricsCtx = (() => { try { return new OffscreenCanvas(1, 1).getContext('2d'); } catch { return null; } })();

function rowHeight(px) {
  const spec = Math.ceil(px * 1.25);
  if (!metricsCtx) return spec;
  metricsCtx.font = `${px}px ${getComputedStyle(document.documentElement).getPropertyValue('--font')}`;
  const m = metricsCtx.measureText('W');
  const natural = m.fontBoundingBoxAscent + m.fontBoundingBoxDescent;
  if (!(natural > 0)) return spec;
  const dpr = devicePixelRatio || 1;
  return Math.max(spec, Math.ceil(natural * dpr) / dpr);
}

const winId = (() => {
  const key = `winid:${slot}`;
  try { const kept = sessionStorage.getItem(key); if (kept) return kept; } catch { /* storage unavailable */ }
  const id = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`).replace(/[^A-Za-z0-9-]/g, '');
  try { sessionStorage.setItem(key, id); } catch { /* storage unavailable */ }
  return id;
})();

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function cellWidth(ch) { return WIDE.test(ch) ? 2 : 1; }
function textWidth(s) { let w = 0; for (const ch of s) w += cellWidth(ch); return w; }

const NEW_BLOCK_RE = /^(?:[-*+•◦▪▸▹►●○]\s|\d+[.)]\s|#{1,6}\s|[>$│╭╰┌└├┤┬┴┼])/;
const DIVIDER_RE = /^[─━═\-=_*]{10,}$/;
const URL_END_PUNCT_RE = /[。、．，）」』】〉》〕］｝・：；！？,;:!?]$/;
const URL_CONT_RE = /^[^\s"'<>`\u3000-\u303f\u3040-\u30ff\u3400-\u9fff\uff00-\uffef]+/;
const URL_TRAILING_RE = /https?:\/\/[^\s"'<>`\u3000-\u303f\uff00-\uffef]+$/;
const URL_TLD_RE = /^(?:com|net|org|jp|io|dev|app|ai|co|uk|de|fr|us|edu|gov|me|tv|gg|xyz|info|biz|site|online|cloud|page|link|work|tech|tools)$/i;

function leadingSpaces(s) {
  let n = 0;
  while (n < s.length && s[n] === ' ') n++;
  return n;
}

function trimUrlEnd(raw) {
  let s = raw;
  while (s.length > 8) {
    if (URL_END_PUNCT_RE.test(s) || s.endsWith('.')) { s = s.slice(0, -1); continue; }
    const last = s[s.length - 1];
    if (last === ')' && (s.split('(').length - 1) < (s.split(')').length - 1)) { s = s.slice(0, -1); continue; }
    if (last === ']' && (s.split('[').length - 1) < (s.split(']').length - 1)) { s = s.slice(0, -1); continue; }
    if (last === '}' && (s.split('{').length - 1) < (s.split('}').length - 1)) { s = s.slice(0, -1); continue; }
    break;
  }
  return s;
}

function urlContinuation(prevFull, prevUrl, nextFull, cols, peerMax = 0, ansiUnderlineCont = false) {
  if (!prevFull || !prevUrl || !nextFull) return null;
  const nextTrim = nextFull.trimStart();
  if (!nextTrim || /^https?:\/\//i.test(nextTrim) || NEW_BLOCK_RE.test(nextTrim)) return null;
  if (/[)\]}>"'`。、）」』】]$/.test(prevUrl)) return null;
  const m = nextTrim.match(URL_CONT_RE);
  if (!m) return null;
  const cont = m[0];
  const prevIndent = leadingSpaces(prevFull);
  const nextIndent = leadingSpaces(nextFull);
  if (nextIndent !== 0 && nextIndent !== prevIndent && !(nextIndent > prevIndent && nextIndent <= prevIndent + 6)) {
    return null;
  }
  if (ansiUnderlineCont) return { indent: nextIndent, raw: cont };
  const width = textWidth(prevFull);
  const firstChar = cont[0] || '';
  const looksLikeProseWord = /^[A-Z][a-z]+(?:\s|$)/.test(nextTrim);
  const contHasUrlPunct = /[/?&=#.%_-]/.test(cont);
  const hardEdgeWrap = cols > 0 && width + cellWidth(firstChar) > cols;
  const softMarginWrap = cols > 0 && width >= Math.max(30, cols - 8) && !looksLikeProseWord
    && (nextIndent > 0 || !/\s/.test(nextTrim) || contHasUrlPunct);
  const peerWrap = peerMax >= 40 && width >= peerMax - 4 && width <= peerMax + 4 && !looksLikeProseWord
    && (!/\s/.test(nextTrim) || contHasUrlPunct);
  const hostPart = prevUrl.replace(/^https?:\/\//i, '');
  const hasPathInPrev = /^https?:\/\/[^/?#]+\//.test(prevUrl);
  const incompleteHost = !/[/?#]/.test(hostPart) && !hostPart.includes('.') && /^[.a-z0-9-]/i.test(cont);
  const brokenDot = prevUrl.endsWith('.') && /^[a-z0-9]/.test(cont) && !/^[a-z]+:$/.test(cont)
    && (hardEdgeWrap || softMarginWrap || peerWrap || contHasUrlPunct || URL_TLD_RE.test(cont));
  const brokenMid = /(?:\/\/|[:?&=%_~+-])$/.test(prevUrl);
  const contPrefix = /^[/?&=#.%]/.test(cont);
  const brokenSlash = prevUrl.endsWith('/') && (contHasUrlPunct || /^\d+$/.test(cont));
  const urlPathCont = hasPathInPrev && !/^[A-Z][a-z]+:$/.test(cont)
    && (/[/?&=#%]/.test(cont) || (/[A-Za-z]/.test(cont) && /\d/.test(cont)) || /[a-z][A-Z]|[A-Z]{2,}|[_-]/.test(cont));
  if (!hardEdgeWrap && !softMarginWrap && !peerWrap && !incompleteHost && !brokenDot && !brokenMid && !contPrefix && !brokenSlash && !urlPathCont) {
    return null;
  }
  return { indent: nextIndent, raw: cont };
}

function joinSelectedLines(pieces, cols) {
  if (!pieces.length) return '';
  let max1 = 0, max2 = 0;
  for (const p of pieces) {
    const trimmed = (p.full || '').trim();
    if (!trimmed || DIVIDER_RE.test(trimmed)) continue;
    const w = textWidth(p.full || '');
    if (w > max1) { max2 = max1; max1 = w; }
    else if (w > max2) { max2 = w; }
  }
  const peerMax = max2 >= 40 ? max2 : 0;
  let text = pieces[0].part;
  let activeUrl = (pieces[0].full.match(URL_TRAILING_RE) || [null])[0];
  for (let i = 1; i < pieces.length; i++) {
    const prev = pieces[i - 1], cur = pieces[i];
    const up = prev.full;
    const curTrim = cur.full.trimStart();
    if (!up || !curTrim || DIVIDER_RE.test(up.trim()) || DIVIDER_RE.test(curTrim)) {
      text += `\n${cur.part}`;
      activeUrl = (cur.full.match(URL_TRAILING_RE) || [null])[0];
      continue;
    }
    if (prev.urlGroupEnd && prev.urlGroupEnd === cur.urlGroupStart) {
      const tail = cur.part.replace(/^\s+/, '');
      text += tail;
      activeUrl = activeUrl ? activeUrl + tail : (cur.full.match(URL_TRAILING_RE) || [null])[0];
      continue;
    }
    if (activeUrl) {
      const cont = urlContinuation(up, activeUrl, cur.full, cols, peerMax);
      if (cont) {
        const tail = cur.part.replace(/^\s+/, '');
        text += tail;
        activeUrl = (cont.indent + cont.raw.length >= cur.full.length) ? activeUrl + cont.raw : null;
        continue;
      }
    }
    activeUrl = (cur.full.match(URL_TRAILING_RE) || [null])[0];
    const width = textWidth(up);
    const firstChar = [...curTrim][0] || '';
    if (cols > 0 && width + cellWidth(firstChar) > cols) {
      text += cur.part.replace(/^\s+/, '');
      continue;
    }
    const upIndent = leadingSpaces(up);
    if (upIndent >= 2 && leadingSpaces(cur.full) === upIndent && !NEW_BLOCK_RE.test(curTrim)) {
      let blockMax = 0;
      for (const p of pieces) {
        if (p.full && leadingSpaces(p.full) === upIndent) blockMax = Math.max(blockMax, textWidth(p.full));
      }
      if (blockMax >= 36 && (cols <= 0 || blockMax <= cols)) {
        const tail = cur.part.replace(/^\s+/, '');
        if (blockMax >= 48 && width + cellWidth(firstChar) > blockMax) {
          text += tail;
          continue;
        }
        const firstTok = curTrim.split(/\s+/)[0];
        if (/[A-Za-z0-9_./"'=-]$/.test(up) && /^[\x21-\x7e]/.test(curTrim) && width + 1 + textWidth(firstTok) > blockMax) {
          text += (/\s$/.test(text) ? '' : ' ') + tail;
          continue;
        }
      }
    }
    text += `\n${cur.part}`;
  }
  return text;
}

function color256(n) {
  if (n < 16) return `var(--c${n})`;
  if (n < 232) { n -= 16; const s = [0, 95, 135, 175, 215, 255]; return `rgb(${s[Math.floor(n / 36)]},${s[Math.floor(n / 6) % 6]},${s[n % 6]})`; }
  const g = 8 + (n - 232) * 10;
  return `rgb(${g},${g},${g})`;
}

function applySgr(st, params) {
  const groups = params === '' ? ['0'] : params.split(';');
  for (let i = 0; i < groups.length; i++) {
    const sub = groups[i].split(':').map(x => (x === '' ? null : Number(x)));
    const c = sub[0] ?? 0;
    if (c === 38 || c === 48) {
      let col = null;
      if (sub.length > 1) {
        if (sub[1] === 5) col = color256(sub[2] ?? 0);
        else if (sub[1] === 2) col = `rgb(${(sub.length >= 6 ? sub.slice(3, 6) : sub.slice(2, 5)).map(v => v ?? 0).join(',')})`;
      } else if (Number(groups[i + 1]) === 5) {
        col = color256(Number(groups[i + 2]) || 0); i += 2;
      } else if (Number(groups[i + 1]) === 2) {
        col = `rgb(${[groups[i + 2], groups[i + 3], groups[i + 4]].map(v => Number(v) || 0).join(',')})`; i += 4;
      }
      if (col === 'var(--c8)' && c === 48) col = 'var(--c8bg, var(--c8))';
      if (col) st[c === 38 ? 'fg' : 'bg'] = col;
    } else if (c === 0) { const keepOsc = st.oscUrl; Object.assign(st, BASE); st.oscUrl = keepOsc; }
    else if (c === 1) st.bold = true;
    else if (c === 2) st.dim = true;
    else if (c === 3) st.italic = true;
    else if (c === 4) st.underline = true;
    else if (c === 7) st.inverse = true;
    else if (c === 22) { st.bold = false; st.dim = false; }
    else if (c === 23) st.italic = false;
    else if (c === 24) st.underline = false;
    else if (c === 27) st.inverse = false;
    else if (c >= 30 && c <= 37) st.fg = `var(--c${c - 30})`;
    else if (c === 39) st.fg = null;
    else if (c >= 40 && c <= 47) st.bg = `var(--c${c - 40})`;
    else if (c === 49) st.bg = null;
    else if (c >= 90 && c <= 97) st.fg = `var(--c${c - 82})`;
    else if (c === 100) st.bg = 'var(--c8bg, var(--c8))';
    else if (c >= 101 && c <= 107) st.bg = `var(--c${c - 92})`;
  }
}

// tmux carries attributes across lines in capture-pane -e output, so st flows from one line to the next.
function parseLine(raw, st) {
  const segs = [];
  let last = 0, m;
  ESC.lastIndex = 0;
  const push = text => { if (text) segs.push({ text, st: { ...st } }); };
  while ((m = ESC.exec(raw))) {
    push(raw.slice(last, m.index));
    if (m[2] === 'm' && m[1] !== undefined && !/[?<>=]/.test(m[1])) applySgr(st, m[1]);
    else if (m[3] !== undefined && m[3].startsWith('8;')) {
      const sep = m[3].indexOf(';', 2);
      if (sep >= 0) {
        const u = m[3].slice(sep + 1);
        st.oscUrl = /^https?:\/\/[^\s"'<>`]+$/.test(u) ? u : null;
      }
    }
    last = ESC.lastIndex;
  }
  push(raw.slice(last));
  return segs;
}

function appendText(parent, text) {
  let run = '', wide = false;
  const flush = () => {
    if (!run) return;
    if (wide) parent.appendChild(el('span', 'w', run));
    else parent.appendChild(document.createTextNode(run));
    run = '';
  };
  for (const ch of text) {
    const w = WIDE.test(ch);
    if (run && w !== wide) flush();
    run += ch; wide = w;
  }
  flush();
}

function isAgyUserSegs(segs, inBlock) {
  if (!segs.length) return false;
  const isBandStyle = st => st.bold && st.fg === 'var(--c4)' && !st.bg && !st.inverse;
  const nonWs = segs.filter(s => s.text.trim().length > 0);
  if (nonWs.length ? !nonWs.every(s => isBandStyle(s.st)) : !isBandStyle(segs[0].st)) return false;
  const plain = segs.map(s => s.text).join('');
  if (plain.startsWith('> ')) return true;
  return inBlock && plain.startsWith('  ');
}

function renderLine(line, segs, agyUser = false) {
  line.textContent = '';
  line.classList.toggle('agy-user', agyUser);
  if (agyUser) {
    const text = segs.map(s => s.text).join('');
    if (text.startsWith('> ')) {
      line.appendChild(el('span', 'agy-caret', '>'));
      appendText(line, text.slice(1));
    } else {
      appendText(line, text);
    }
    linkify(line);
    return;
  }
  for (const s of segs) {
    let fg = s.st.fg, bg = s.st.bg;
    if (s.st.inverse) [fg, bg] = [bg || 'var(--bg)', fg || 'var(--fg)'];
    if (!s.st.oscUrl && !fg && !bg && !s.st.bold && !s.st.dim && !s.st.italic && !s.st.underline) { appendText(line, s.text); continue; }
    const node = s.st.oscUrl ? el('a', bg ? 'u b' : 'u') : el('span', bg ? 'b' : '');
    if (s.st.oscUrl) {
      node.dataset.oscUrl = s.st.oscUrl;
      node.dataset.url = s.st.oscUrl;
      node.href = s.st.oscUrl;
      node.target = '_blank';
      node.rel = 'noopener';
    }
    if (fg) node.style.color = fg;
    if (bg) node.style.background = bg;
    if (s.st.bold) node.style.fontWeight = 'bold';
    if (s.st.dim) node.style.opacity = 'var(--dim, .6)';
    if (s.st.italic) node.style.fontStyle = 'italic';
    if (s.st.underline) {
      node.style.textDecoration = 'underline';
      node.dataset.uStyle = '1';
    }
    appendText(node, s.text);
    line.appendChild(node);
  }
  linkify(line);
}

function renderParsedLines(rawLines, { agy = false, agyLimit = rawLines.length, keys = null, getLine }) {
  let inAgyUser = false;
  let dirty = false;
  const st = { ...BASE };
  rawLines.forEach((raw, i) => {
    const startSt = keys ? JSON.stringify(st) : '';
    const segs = parseLine(raw ?? '', st);
    inAgyUser = agy && i < agyLimit && isAgyUserSegs(segs, inAgyUser);
    if (keys) {
      const key = startSt + '\u0000' + (inAgyUser ? '1' : '0') + '\u0000' + raw;
      if (keys[i] === key) return;
      keys[i] = key;
    }
    dirty = true;
    renderLine(getLine(i), segs, inAgyUser);
  });
  return dirty;
}

function bindPointerDrag(target, onStart) {
  target.addEventListener('pointerdown', e => {
    const handlers = onStart(e);
    if (!handlers) return;
    target.setPointerCapture(e.pointerId);
    const move = ev => handlers.move?.(ev);
    const up = ev => {
      target.removeEventListener('pointermove', move);
      target.removeEventListener('pointerup', up);
      handlers.up?.(ev);
    };
    target.addEventListener('pointermove', move);
    target.addEventListener('pointerup', up);
  });
}

const SYS_MSG_RE = /^>\s+\[[a-z0-9_-]+→[a-z0-9_-]+\]/i;
const TOOL_LOG_RE = /^(?:[▸○●]\s+(?:Thought for|Explored|Ran|Edited|Wrote|Read|Calling|Searched|Listed|Updated|Created|Deleted|Checked)\b|…\s+\d+\s+more\s+actions?\b|\s*└\s+Tip:)/;

function applyNoiseFolds(container, openSet) {
  const rows = [...container.children];
  const flags = [];
  let inSys = false;
  for (const ln of rows) {
    const t = ln.textContent || '';
    if (SYS_MSG_RE.test(t)) { flags.push('sys'); inSys = true; }
    else if (inSys && /^\s{2}\S/.test(t)) { flags.push('sys'); }
    else if (TOOL_LOG_RE.test(t)) { flags.push('tool'); inSys = false; }
    else { flags.push(''); inSys = false; }
  }
  let i = 0;
  while (i < rows.length) {
    const ln = rows[i];
    if (!flags[i]) {
      ln.classList.remove('fold-head', 'fold-body', 'fold-hide', 'fold-open');
      delete ln.dataset.foldKey;
      delete ln.dataset.foldLabel;
      i += 1;
      continue;
    }
    let j = i;
    let hasSys = false, hasTool = false;
    while (j < rows.length && flags[j]) {
      if (flags[j] === 'sys') hasSys = true;
      else hasTool = true;
      j += 1;
    }
    const count = j - i;
    const key = (rows[i].textContent || '').trim().slice(0, 80);
    const open = openSet.has(key);
    const kind = hasSys && hasTool ? 'Agent messages & tools' : (hasSys ? 'Agent messages' : 'Tool logs');
    const head = rows[i];
    head.classList.add('fold-head');
    head.classList.remove('fold-body', 'fold-hide');
    head.classList.toggle('fold-open', open);
    head.dataset.foldKey = key;
    head.dataset.foldLabel = `▸ ${kind} (${count} lines)`;
    for (let k = i + 1; k < j; k++) {
      const body = rows[k];
      body.classList.remove('fold-head', 'fold-open');
      body.classList.add('fold-body');
      body.classList.toggle('fold-hide', !open);
      delete body.dataset.foldKey;
      delete body.dataset.foldLabel;
    }
    i = j;
  }
}

function linkify(line) {
  const walker = document.createTreeWalker(line, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) {
    const tn = walker.currentNode;
    if (!tn.data.includes('http')) continue;
    if (tn.parentElement && typeof tn.parentElement.closest === 'function' && tn.parentElement.closest('a.u')) continue;
    nodes.push(tn);
  }
  for (const node of nodes) {
    const parts = [];
    let last = 0, m;
    URL_RE.lastIndex = 0;
    while ((m = URL_RE.exec(node.data))) {
      parts.push(document.createTextNode(node.data.slice(last, m.index)));
      const a = el('a', 'u', m[0]);
      parts.push(a);
      last = URL_RE.lastIndex;
    }
    if (!parts.length) continue;
    parts.push(document.createTextNode(node.data.slice(last)));
    node.replaceWith(...parts);
  }
}

let urlGroupSeq = 0;

function resetLinkify(line) {
  if (typeof line.querySelectorAll !== 'function') return false;
  const links = line.querySelectorAll('a.u');
  if (!links.length) return false;
  let removed = false;
  for (const a of links) {
    if (a.dataset && a.dataset.oscUrl) {
      delete a.dataset.urlGroup;
      delete a.dataset.urlCont;
      continue;
    }
    const parent = a.parentNode;
    if (!parent) continue;
    while (a.firstChild) parent.insertBefore(a.firstChild, a);
    a.remove();
    removed = true;
  }
  if (removed && typeof line.normalize === 'function') line.normalize();
  return removed;
}

function hasAnsiUnderline(node) {
  let cur = node;
  while (cur && cur.nodeType) {
    if (cur.nodeType === 1 && cur.dataset && cur.dataset.uStyle === '1') return true;
    cur = cur.parentNode;
  }
  return false;
}

function hasAnsiUnderlineAt(line, offset) {
  const walker = document.createTreeWalker(line, NodeFilter.SHOW_TEXT);
  let pos = 0;
  while (walker.nextNode()) {
    const tn = walker.currentNode;
    const len = tn.data.length;
    if (offset >= pos && offset < pos + len) return hasAnsiUnderline(tn.parentElement);
    pos += len;
  }
  return false;
}

function trailingTextAfter(line, node) {
  const walker = document.createTreeWalker(line, NodeFilter.SHOW_TEXT);
  let seen = false;
  let out = '';
  while (walker.nextNode()) {
    const cur = walker.currentNode;
    if (node.contains(cur)) { seen = true; continue; }
    if (seen) out += cur.data;
  }
  return out;
}

function wrapLineRangeAsLink(line, startOffset, length) {
  for (const existing of [...line.querySelectorAll('a.u')]) {
    if (existing.dataset.url) continue;
    const parent = existing.parentNode;
    if (!parent) continue;
    while (existing.firstChild) parent.insertBefore(existing.firstChild, existing);
    existing.remove();
  }
  if (typeof line.normalize === 'function') line.normalize();
  const created = [];
  const endOffset = startOffset + length;
  const walker = document.createTreeWalker(line, NodeFilter.SHOW_TEXT);
  const ops = [];
  let pos = 0;
  while (walker.nextNode()) {
    const tn = walker.currentNode;
    const len = tn.data.length;
    const lo = Math.max(0, startOffset - pos);
    const hi = Math.min(len, endOffset - pos);
    if (lo < hi) ops.push({ tn, lo, hi });
    pos += len;
    if (pos >= endOffset) break;
  }
  for (const { tn, lo, hi } of ops) {
    const parts = [];
    if (lo > 0) parts.push(document.createTextNode(tn.data.slice(0, lo)));
    const a = el('a', 'u', tn.data.slice(lo, hi));
    a.dataset.urlCont = '1';
    parts.push(a);
    created.push(a);
    if (hi < tn.data.length) parts.push(document.createTextNode(tn.data.slice(hi)));
    tn.replaceWith(...parts);
  }
  linkify(line);
  return created;
}

function trimAnchorsEnd(anchors, trimChars) {
  let rem = trimChars;
  while (rem > 0 && anchors.length) {
    const a = anchors[anchors.length - 1];
    const txt = a.textContent || '';
    if (rem >= txt.length) {
      rem -= txt.length;
      a.replaceWith(document.createTextNode(txt));
      anchors.pop();
    } else {
      a.textContent = txt.slice(0, txt.length - rem);
      a.after(document.createTextNode(txt.slice(txt.length - rem)));
      rem = 0;
    }
  }
}

function linkifyContainer(container, cols) {
  if (!container || !container.children || !container.children.length) return;
  const rows = [...container.children];
  let max1 = 0, max2 = 0;
  for (const ln of rows) {
    const full = (ln.textContent || '').trimEnd();
    const trimmed = full.trim();
    if (!trimmed || DIVIDER_RE.test(trimmed)) continue;
    const w = textWidth(full);
    if (w > max1) { max2 = max1; max1 = w; }
    else if (w > max2) { max2 = w; }
  }
  const peerMax = max2 >= 40 ? max2 : 0;
  for (const ln of rows) {
    if (resetLinkify(ln)) linkify(ln);
  }
  for (let i = 0; i < rows.length; i++) {
    const ln = rows[i];
    if (typeof ln.querySelectorAll !== 'function') continue;
    const anchors = [...ln.querySelectorAll('a.u')];
    for (const a of anchors) {
      if (a.dataset.oscUrl) {
        if (a.dataset.urlGroup) continue;
        if (!trailingTextAfter(ln, a).trim()) {
          const oscGroup = [a];
          let curRowIdx = i;
          while (curRowIdx + 1 < rows.length) {
            const nextLn = rows[curRowIdx + 1];
            if (typeof nextLn.querySelectorAll !== 'function') break;
            const nextLinks = [...nextLn.querySelectorAll('a.u')].filter(x => x.dataset.oscUrl === a.dataset.oscUrl);
            if (!nextLinks.length) break;
            const nextLead = (nextLn.textContent || '').trimStart();
            if (!nextLead.startsWith(nextLinks[0].textContent || '')) break;
            for (const nl of nextLinks) { nl.dataset.urlCont = '1'; oscGroup.push(nl); }
            curRowIdx += 1;
            if (trailingTextAfter(nextLn, nextLinks[nextLinks.length - 1]).trim()) break;
          }
          if (oscGroup.length > 1) {
            const gid = String(++urlGroupSeq);
            for (const segA of oscGroup) segA.dataset.urlGroup = gid;
          }
        }
        continue;
      }
      if (a.dataset.url) continue;
      const group = [a];
      let rawFull = a.textContent || '';
      if (!trailingTextAfter(ln, a).trim()) {
        let curRowIdx = i;
        while (curRowIdx + 1 < rows.length) {
          const prevFull = (rows[curRowIdx].textContent || '').trimEnd();
          const nextFull = (rows[curRowIdx + 1].textContent || '').trimEnd();
          const nextIndent = leadingSpaces(nextFull);
          const ansiU = hasAnsiUnderline(group[group.length - 1]) && hasAnsiUnderlineAt(rows[curRowIdx + 1], nextIndent);
          const cont = urlContinuation(prevFull, rawFull, nextFull, cols, peerMax, ansiU);
          if (!cont) break;
          const added = wrapLineRangeAsLink(rows[curRowIdx + 1], cont.indent, cont.raw.length);
          if (!added.length) break;
          group.push(...added);
          rawFull += cont.raw;
          curRowIdx += 1;
          if (cont.indent + cont.raw.length < nextFull.length) break;
        }
      }
      const trimmed = trimUrlEnd(rawFull);
      const cut = rawFull.length - trimmed.length;
      if (cut > 0) trimAnchorsEnd(group, cut);
      if (!group.length || !/^https?:\/\//.test(trimmed)) continue;
      const groupId = group.length > 1 ? String(++urlGroupSeq) : '';
      for (const segA of group) {
        segA.dataset.url = trimmed;
        segA.href = trimmed;
        segA.target = '_blank';
        segA.rel = 'noopener';
        if (groupId) segA.dataset.urlGroup = groupId;
      }
    }
  }
}

async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); return true; }
  } catch { /* fall back below */ }
  const area = el('textarea');
  area.value = text;
  area.style.position = 'fixed';
  area.style.opacity = '0';
  document.body.appendChild(area);
  area.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch { ok = false; }
  area.remove();
  return ok;
}

function shellEscape(path) { return path.replace(/([ \t'"\\$`!&;|<>()[\]{}*?#~^])/g, '\\$1'); }

async function post(path, body) {
  const res = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

const outbox = { items: [], busy: false };
function send(pane, kind, value) {
  const last = outbox.items[outbox.items.length - 1];
  if (last && !last.started && last.room === pane.room && last.kind === kind) {
    if (kind === 'text') last.value += value; else last.value.push(value);
  } else {
    outbox.items.push({ pane, room: pane.room, kind, value: kind === 'text' ? value : [value] });
  }
  pump();
}
async function pump() {
  if (outbox.busy) return;
  outbox.busy = true;
  while (outbox.items.length) {
    const item = outbox.items[0];
    item.started = true;
    try {
      await post(item.kind === 'text' ? 'api/text' : 'api/keys',
        item.kind === 'text' ? { room: item.room, text: item.value } : { room: item.room, keys: item.value });
    } catch (err) {
      item.pane.fail(`Send failed: ${err.message}`);
    }
    outbox.items.shift();
  }
  outbox.busy = false;
}

function keyName(e) {
  if (e.isComposing || e.keyCode === 229) return null;
  const k = e.key;
  if (e.ctrlKey && !e.altKey && !e.metaKey && /^[a-zA-Z]$/.test(k)) {
    const lower = k.toLowerCase();
    if (lower === 'v' || e.shiftKey) return null;
    if (lower === 'c' && !window.getSelection().isCollapsed) return null;
    return `C-${lower}`;
  }
  if (e.ctrlKey || e.metaKey) return null;
  if (k === 'Enter') return e.shiftKey || e.altKey ? 'M-Enter' : 'Enter';
  if (k === 'Tab') return e.shiftKey ? 'BTab' : 'Tab';
  if (/^F([1-9]|1[0-2])$/.test(k)) return k;
  return e.altKey ? null : KEYMAP[k] || null;
}

class Pane {
  constructor(deck) {
    this.deck = deck;
    this.room = null;
    this.isMenuPane = false;
    this.wantedMenu = false;
    this.raw = [];
    this.keys = [];
    this.histLines = 0;
    this.histAllFrame = -1;
    this.histPending = null;
    this.histGen = 0;
    this.frameSeq = 0;
    this.dockStart = 0;
    this.menu = null;
    this.lastCursor = [0, 0];
    this.lastShowCursor = false;
    this.size = '';
    this.node = el('div', 'pane');
    this.tab = el('div', 'tab');
    this.menuBtn = el('button', 'menu', '☰');
    this.stateDot = el('span', 'dot state-dot');
    this.select = el('select', 'room-select');
    this.cwd = el('span', 'cwd');
    this.err = el('span', 'err');
    this.arrows = [['up', '↑'], ['down', '↓'], ['left', '←'], ['right', '→']].map(([dir, text]) => {
      const b = el('button', 'split-btn', text);
      b.onclick = () => this.deck.split(this, dir);
      return b;
    });
    this.smaller = el('button', 'size-btn', '−');
    this.bigger = el('button', 'size-btn', '＋');
    this.fsVal = el('span', 'fs-val', String(baseFs()));
    this.fsGroup = el('span', 'fs-group');
    this.fsGroup.append(this.smaller, this.fsVal, this.bigger);
    this.hideBtn = el('button', 'hide-btn', '✕');
    this.closeBtn = el('button', 'close-btn', 'Close');
    this.tab.append(this.menuBtn, this.stateDot, this.select, this.cwd, this.err, ...this.arrows, this.fsGroup, this.hideBtn, this.closeBtn);
    this.screen = el('div', 'screen');
    this.hist = el('div', 'hist');
    this.live = el('div', 'live');
    this.dock = el('div', 'dock');
    this.dock.hidden = true;
    this.cursor = el('div', 'cur');
    this.ime = el('textarea', 'ime');
    this.ime.setAttribute('autocapitalize', 'off');
    this.ime.setAttribute('autocomplete', 'off');
    this.ime.setAttribute('spellcheck', 'false');
    this.measure = el('span', 'measure', 'MMMMMMMMMM');
    this.chooser = el('div', 'chooser');
    this.menuSlot = el('div', 'menu-slot');
    this.menuSlot.hidden = true;
    this.toastEl = el('div', 'toast', '✂');
    this.toastEl.setAttribute('aria-label', 'Copied');
    this.answers = el('div', 'answers');
    this.answers.setAttribute('role', 'toolbar');
    this.choices = el('span', 'choices');
    for (const word of ['yes', 'no', '', '1', '2', '3', '4', '5']) {
      if (!word) { this.choices.append(el('span', 'sep')); continue; }
      const b = el('button', '', word[0].toUpperCase());
      b.dataset.word = b.title = word;
      this.choices.append(b);
    }
    this.cmdBar = el('span', 'choices');
    this.navToggleBtn = iconButton(ICONS.dpad, 'Arrow keys');
    this.navToggleBtn.classList.add('nav-toggle');
    this.navKeys = el('span', 'nav-keys');
    this.navKeys.hidden = true;
    for (const [label, key, cls] of [
      ['←', 'Left', ''], ['↑', 'Up', ''], ['↓', 'Down', ''], ['→', 'Right', ''],
      ['Esc', 'Escape', 'esc'], ['⏎', 'Enter', 'enter'],
    ]) {
      const b = el('button', cls ? `nav-key ${cls}` : 'nav-key', label);
      b.dataset.key = b.title = key;
      b.setAttribute('aria-label', key);
      this.navKeys.append(b);
    }
    this.navBackBtn = el('button', 'icon-btn nav-toggle active nav-back', '123');
    this.navBackBtn.title = 'Choices';
    this.navBackBtn.setAttribute('aria-label', 'Choices');
    this.navKeys.append(this.navBackBtn);
    this.answers.append(this.choices, this.navToggleBtn, el('span', 'grow'), this.cmdBar, this.navKeys);
    this.answers.hidden = true;
    this.screen.append(this.hist, this.live, this.dock, this.cursor, this.ime, this.measure);
    this.node.append(this.tab, this.screen, this.answers, this.chooser, this.menuSlot, this.toastEl);
    this.screen.hidden = true;
    this.bind();
  }

  bind() {
    this.bindToolbar();
    this.bindDrop();
    this.bindScreenClick();
    this.bindScroll();
    this.bindInput();
    new ResizeObserver(() => this.fit()).observe(this.screen);
  }

  bindToolbar() {
    this.menuBtn.onclick = () => document.getElementById('app').classList.toggle('drawer');
    this.answers.onpointerdown = e => e.preventDefault();
    this.choices.onclick = e => {
      const word = e.target.closest('button')?.dataset.word;
      if (word) this.answerChoice(word);
    };
    this.navToggleBtn.onclick = () => this.setNavMode(true);
    this.navBackBtn.onclick = () => this.setNavMode(false);
    this.navKeys.onclick = e => {
      const key = e.target.closest('button')?.dataset.key;
      if (!key) return;
      this.sendNavKey(key);
    };
    this.select.onchange = () => {
      if (this.select.value === RENAME) { this.select.value = this.room || ''; this.renameRoom(); return; }
      if (this.select.value === MENU_OPTION) { this.deck.openMenu(this); return; }
      this.deck.openRoom(this.select.value, this);
    };
    this.smaller.onclick = () => this.setFont(this.fontSize() - 1);
    this.bigger.onclick = () => this.setFont(this.fontSize() + 1);
    this.hideBtn.onclick = () => this.deck.removePane(this);
    this.closeBtn.onclick = () => this.closeRoom();
    this.node.addEventListener('mousedown', () => this.deck.setActive(this));
    this.screen.addEventListener('mouseup', () => {
      if (window.getSelection().isCollapsed) this.focus(); else this.copySelection();
    });
    this.screen.addEventListener('copy', e => {
      const text = this.selectedText();
      if (!text || !e.clipboardData) return;
      e.preventDefault();
      e.clipboardData.setData('text/plain', text);
      this.toast();
    });
  }

  bindDrop() {
    this.screen.addEventListener('dragover', e => {
      if (!this.room || ![...e.dataTransfer.types].includes('Files')) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
      this.node.classList.add('dropping');
    });
    this.screen.addEventListener('dragleave', () => this.node.classList.remove('dropping'));
    this.screen.addEventListener('drop', e => {
      this.node.classList.remove('dropping');
      if (!this.room || !e.dataTransfer.files.length) return;
      e.preventDefault();
      this.dropFiles([...e.dataTransfer.files]);
    });
  }

  bindScreenClick() {
    this.screen.addEventListener('click', e => {
      const fh = e.target.closest('.ln.fold-head');
      if (fh && window.getSelection().isCollapsed) {
        e.preventDefault();
        const key = fh.dataset.foldKey;
        const openSet = this.openFolds || (this.openFolds = new Set());
        if (openSet.has(key)) openSet.delete(key); else openSet.add(key);
        applyNoiseFolds(fh.parentElement, openSet);
        return;
      }
      const a = e.target.closest('a.u');
      if (a) {
        e.preventDefault();
        if (!window.getSelection().isCollapsed) return;
        const url = a.dataset.url || this.fullUrl(a);
        if (/^https?:\/\//.test(url)) window.open(url, '_blank', 'noopener');
        return;
      }
      if (!window.getSelection().isCollapsed || !this.menu) return;
      const ln = e.target.closest('.live > .ln, .dock > .ln');
      if (!ln) return;
      const item = this.menuItemForNode(ln);
      if (item) {
        e.preventDefault();
        this.selectMenuItem(this.menu, item);
      }
    });
  }

  bindScroll() {
    this.screen.addEventListener('wheel', e => this.onWheel(e), { passive: false });
    this.screen.addEventListener('scroll', () => {
      if (this.screen.scrollTop <= 2 && this.histLines && !this.historyExhausted()) this.loadHistory();
      if (this.dock.childElementCount) this.placeCursor(this.lastCursor, this.lastShowCursor);
    });
    let touchY = null;
    this.screen.addEventListener('touchstart', e => { touchY = e.touches[0].clientY; }, { passive: true });
    this.screen.addEventListener('touchmove', e => {
      if (touchY === null) return;
      const y = e.touches[0].clientY;
      if (this.alt) { this.onWheel({ deltaY: touchY - y, deltaMode: 0, preventDefault() {} }); touchY = y; return; }
      if (y - touchY > 24 && this.screen.scrollTop <= 2) { touchY = null; this.loadHistory(-rowHeight(this.fontSize())); }
    }, { passive: true });
  }

  bindInput() {
    const ime = this.ime;
    ime.addEventListener('keydown', e => {
      if (this.scrollKey(e)) { e.preventDefault(); return; }
      const name = keyName(e);
      if (!name) return;
      e.preventDefault();
      this.typed(name === 'Enter');
      send(this, 'keys', name);
    });
    ime.addEventListener('beforeinput', e => {
      if (e.isComposing) return;
      if (e.inputType === 'insertText' && e.data) { e.preventDefault(); this.typed(false); send(this, 'text', e.data); }
      else if (e.inputType === 'insertLineBreak' || e.inputType === 'insertParagraph') { e.preventDefault(); this.typed(true); send(this, 'keys', 'Enter'); }
      else if (e.inputType === 'deleteContentBackward' && !ime.value) { e.preventDefault(); this.typed(false); send(this, 'keys', 'BSpace'); }
    });
    ime.addEventListener('input', e => {
      if (e.isComposing || ime.classList.contains('composing') || !ime.value) return;
      this.typed(false);
      send(this, 'text', ime.value);
      ime.value = '';
    });
    ime.addEventListener('compositionstart', () => ime.classList.add('composing'));
    ime.addEventListener('compositionend', e => {
      ime.classList.remove('composing');
      if (e.data) { this.typed(false); send(this, 'text', e.data); }
      ime.value = '';
    });
    ime.addEventListener('paste', e => {
      e.preventDefault();
      const text = e.clipboardData.getData('text/plain');
      this.typed(false);
      if (text) { send(this, 'text', text); return; }
      const images = [...e.clipboardData.items].filter(i => i.kind === 'file' && i.type.startsWith('image/')).map(i => i.getAsFile()).filter(Boolean);
      if (images.length) this.dropFiles(images, true);
    });
  }

  focus() { if (this.room) this.ime.focus({ preventScroll: true }); }

  scrollKey(e) {
    if (e.ctrlKey || e.metaKey || e.altKey || e.isComposing) return false;
    if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return false;
    if (this.alt) {
      if (!e.shiftKey) return false;
      send(this, 'keys', e.key === 'ArrowUp' ? 'WheelUp' : 'WheelDown');
      return true;
    }
    const s = this.screen;
    if (!e.shiftKey && s.scrollHeight - s.scrollTop - s.clientHeight < 4) return false;
    const line = parseFloat(s.style.getPropertyValue('--ch')) || 20;
    if (e.key === 'ArrowUp' && s.scrollTop <= 2 && !this.historyExhausted()) this.loadHistory(-line);
    else s.scrollBy(0, e.key === 'ArrowUp' ? -line : line);
    return true;
  }

  toast() {
    clearTimeout(this.toastTimer);
    this.toastEl.classList.add('on');
    this.toastTimer = setTimeout(() => this.toastEl.classList.remove('on'), 1500);
  }

  selectedText() {
    const sel = window.getSelection();
    if (sel.isCollapsed || !sel.rangeCount) return '';
    const range = sel.getRangeAt(0);
    const lines = [...this.screen.querySelectorAll('.ln')].filter(ln => sel.containsNode(ln, true));
    if (!lines.length) return '';
    const cols = this.cols || 0;
    const pieces = lines.map(ln => {
      const r = document.createRange();
      r.selectNodeContents(ln);
      if (ln.contains(range.startContainer)) r.setStart(range.startContainer, range.startOffset);
      if (ln.contains(range.endContainer)) r.setEnd(range.endContainer, range.endOffset);
      const links = [...ln.querySelectorAll('a.u[data-url-group]')];
      const firstA = links.find(a => a.dataset.urlCont === '1');
      const lastA = links.length ? links[links.length - 1] : null;
      return {
        full: ln.textContent.trimEnd(),
        part: r.toString().trimEnd(),
        urlGroupStart: firstA ? firstA.dataset.urlGroup : null,
        urlGroupEnd: (lastA && !trailingTextAfter(ln, lastA).trim()) ? lastA.dataset.urlGroup : null,
      };
    });
    return joinSelectedLines(pieces, cols);
  }

  async copySelection() {
    const text = this.selectedText();
    if (text && await copyText(text)) this.toast();
  }

  async dropFiles(files, image = false) {
    const paths = [];
    for (const file of files) {
      try {
        const res = await fetch(`api/drop?name=${encodeURIComponent(file.name)}${image ? '&image=1' : ''}`, {
          method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || res.status);
        paths.push(shellEscape(data.path));
      } catch (err) {
        this.fail(`Failed to upload ${file.name}: ${err.message}`);
      }
    }
    if (paths.length) { this.typed(); send(this, 'text', paths.join(' ')); this.focus(); }
  }

  fontKey() {
    const key = this.room ? `fs:${this.room}` : '';
    return key && isMobile() ? key.replace('fs:', 'fs:m:') : key;
  }

  fontSize() { return this.fontKey() ? clampFs(store.get(this.fontKey(), baseFs())) : baseFs(); }

  setFont(px) {
    if (this.fontKey()) store.set(this.fontKey(), clampFs(px));
    this.applyFont();
  }

  isAgy() {
    const r = this.room && this.deck.rooms.find(x => x.name === this.room);
    const c = r ? (r.client || '') : '';
    return c.startsWith('agy');
  }

  applyFont() {
    const px = this.fontSize();
    this.fsVal.textContent = px;
    this.screen.style.setProperty('--fs', `${px}px`);
    this.screen.style.setProperty('--ch', `${rowHeight(px)}px`);
    this.fit();
  }

  refit() {
    this.size = '';
    this.fit();
  }

  fit() {
    if (!this.room) return;
    const cw = this.measure.getBoundingClientRect().width / 10;
    const ch = rowHeight(this.fontSize());
    if (!cw) return;
    const cols = Math.floor(this.screen.clientWidth / cw);
    const rows = Math.floor(this.screen.clientHeight / ch);
    const size = `${cols}x${rows}`;
    if (size === this.size || cols < 20 || rows < 5) return;
    this.size = size;
    clearTimeout(this.fitTimer);
    this.fitTimer = setTimeout(() => this.room && post('api/resize', { room: this.room, cols, rows }).catch(err => this.fail(err.message)), 120);
  }

  show(room, claim = true) {
    this.wantedMenu = false;
    this.dropMenu();
    if (room && claim) this.deck.claims.add(room);
    this.room = room;
    this.raw = [];
    this.keys = [];
    this.size = '';
    this.live.textContent = '';
    this.dock.textContent = '';
    this.dock.hidden = true;
    this.dockStart = 0;
    this.menu = null;
    this.clearHistory();
    this.err.textContent = '';
    this.cwd.textContent = '';
    this.screen.hidden = !room;
    this.chooser.hidden = !!room;
    if (room) this.applyFont(); else this.renderChooser();
    this.syncCommands();
    this.deck.changed();
  }

  showMenu() {
    for (const p of this.deck.panes) {
      if (p !== this && p.isMenuPane) p.show(null, false);
    }
    this.wantedMenu = false;
    this.room = null;
    this.raw = [];
    this.keys = [];
    this.size = '';
    this.menu = null;
    this.clearHistory();
    this.err.textContent = '';
    this.cwd.textContent = '';
    this.screen.hidden = true;
    this.chooser.hidden = true;
    this.isMenuPane = true;
    this.node.classList.add('menu-pane');
    const side = document.getElementById('side');
    if (side) this.menuSlot.appendChild(side);
    this.menuSlot.hidden = false;
    this.syncCommands();
    this.deck.changed();
  }

  dropMenu() {
    if (!this.isMenuPane) return;
    this.isMenuPane = false;
    this.node.classList.remove('menu-pane');
    this.menuSlot.hidden = true;
    const side = document.getElementById('side');
    const app = document.getElementById('app');
    const resizer = document.getElementById('side-resizer');
    if (side && app && side.parentElement === this.menuSlot) {
      app.insertBefore(side, resizer || document.getElementById('panes'));
    }
  }

  fail(message) { this.err.textContent = message; }

  syncCommands() {
    this.answers.hidden = !this.room;
    this.navToggleBtn.hidden = !this.room;
    if (!this.room) this.setNavMode(false);
    this.cmdBar.textContent = '';
    for (const cmd of this.deck.commands || []) {
      const b = el('button', 'cmd-btn', cmd.label);
      b.title = cmd.text;
      b.onclick = () => this.submit(cmd.text);
      this.cmdBar.appendChild(b);
    }
  }

  setNavMode(on) {
    const active = Boolean(on && this.room);
    this.answers.classList.toggle('nav-mode', active);
    this.navKeys.hidden = !active;
  }

  sendNavKey(key) {
    if (!this.room) return;
    this.typed(key === 'Enter');
    send(this, 'keys', key);
  }

  submit(text) {
    if (!this.room) return;
    this.typed();
    send(this, 'text', text);
    setTimeout(() => send(this, 'keys', 'Enter'), 500);
    this.focus();
  }

  frame(f) {
    this.err.textContent = '';
    if (f.full) this.raw = [];
    for (const [i, line] of Object.entries(f.lines)) this.raw[Number(i)] = line;
    this.raw.length = f.total;
    this.alt = f.alt;
    this.wheel = f.wheel;
    this.cols = f.cols;
    this.cwd.textContent = f.cwd;
    const changed = Object.keys(f.lines).length > 0;
    if (changed) this.frameSeq += 1;
    const atBottom = this.screen.scrollHeight - this.screen.scrollTop - this.screen.clientHeight < 4;
    if (atBottom && !this.histPending && (this.histLines || this.histAllFrame >= 0) && changed) this.clearHistory();
    this.render();
    this.lastCursor = f.cursor;
    this.lastShowCursor = f.showCursor;
    this.placeCursor(f.cursor, f.showCursor);
    if (atBottom) this.screen.scrollTop = this.screen.scrollHeight;
  }

  findDockStart() {
    if (this.alt || this.raw.length < 4) return this.raw.length;
    const plain = i => (this.raw[i] ?? '').replace(ESC, '').trim();
    const isRule = s => /^[─━]{10,}$/.test(s);
    let end = this.raw.length - 1;
    while (end >= 0 && !plain(end)) end--;
    let bot = -1;
    for (let i = end; i >= Math.max(0, end - 3); i--) {
      if (isRule(plain(i))) { bot = i; break; }
    }
    if (bot < 2) return this.raw.length;
    let top = -1;
    for (let i = bot - 1; i >= Math.max(0, bot - 14); i--) {
      if (isRule(plain(i))) { top = i; break; }
    }
    if (top < 0 || bot - top < 2) return this.raw.length;
    if (!/^[>❯›](?:\s|$)/.test(plain(top + 1))) return this.raw.length;
    return top;
  }

  lineAt(i) {
    const n = this.live.children.length;
    return i < n ? this.live.children[i] : this.dock.children[i - n];
  }

  applyNoiseFoldsTo(container) {
    applyNoiseFolds(container, this.openFolds || (this.openFolds = new Set()));
  }

  render() {
    const dockStart = this.findDockStart();
    const dockCount = this.raw.length - dockStart;
    let dirty = dockStart !== this.dockStart
      || this.live.children.length !== dockStart
      || this.dock.children.length !== dockCount;
    if (dockStart !== this.dockStart) {
      this.keys.length = Math.min(this.keys.length, dockStart, this.dockStart);
      this.dockStart = dockStart;
    }
    while (this.live.children.length < dockStart) this.live.appendChild(el('div', 'ln'));
    while (this.live.children.length > dockStart) this.live.lastChild.remove();
    while (this.dock.children.length < dockCount) this.dock.appendChild(el('div', 'ln'));
    while (this.dock.children.length > dockCount) this.dock.lastChild.remove();
    this.dock.hidden = dockCount === 0;
    const agy = this.isAgy();
    dirty = renderParsedLines(this.raw, { agy, agyLimit: dockStart, keys: this.keys, getLine: i => this.lineAt(i) }) || dirty;
    this.keys.length = this.raw.length;
    if (dirty) {
      linkifyContainer(this.live, this.cols || 0);
      if (dockCount > 0) linkifyContainer(this.dock, this.cols || 0);
    }
    if (agy) this.applyNoiseFoldsTo(this.live);
    this.syncMenuMarks();
  }

  findMenu() {
    if (!this.raw.length || this.dockStart < this.raw.length) return null;
    const n = this.raw.length;
    const plain = i => (this.raw[i] ?? '').replace(ESC, '');
    let end = n - 1;
    while (end >= 0 && !plain(end).trim()) end--;
    if (end < 1) return null;
    const start = Math.max(0, end - 28);
    const hasHighlight = i => /\x1b\[[0-9;]*(?:7|4[0-7]|48;|10[0-7])(?:[;m])/.test(this.raw[i] ?? '');
    const CHECK_RE = /^(\s*)([❯›>▸▶→●])?\s*(?:(\d+)[.)]\s*)?(\[[ xX✓✔]\]|[☐☑□■◯◉])\s*(?:(\d+)[.)]\s*)?(.*)$/;
    const NUM_RE = /^(\s*)([❯›>▸▶→●])?\s*(\d+)[.)]\s+(\S.*)$/;
    const SUBMIT_RE = /^\s*([❯›>▸▶→●])?\s*(?:\[\s*)?(submit|confirm|done|next|apply|送信|確定|次へ|完了)(?:\s*\])?\s*$/i;
    const RULE_RE = /^[─━]{10,}$/;
    const HINT_RE = /(?:↑\/↓|↓\/↑|to navigate|to select|to toggle|to confirm|esc to|space to|enter to|矢印|スペース)/i;

    const checkItems = [];
    const numItems = [];
    for (let i = start; i <= end; i++) {
      const text = plain(i);
      const trimmed = text.trim();
      if (!trimmed) continue;
      let m = CHECK_RE.exec(text);
      if (m) {
        const num = m[3] ? Number(m[3]) : (m[5] ? Number(m[5]) : null);
        checkItems.push({ row: i, pointed: Boolean(m[2]), highlighted: hasHighlight(i), num, label: (m[6] || '').trim(), isSubmit: false });
        continue;
      }
      if (checkItems.length) {
        const sm = SUBMIT_RE.exec(text);
        if (sm) {
          checkItems.push({ row: i, pointed: Boolean(sm[1]), highlighted: hasHighlight(i), num: null, label: sm[2], isSubmit: true });
          continue;
        }
      }
      m = NUM_RE.exec(text);
      if (m) {
        numItems.push({ row: i, pointed: Boolean(m[2]), highlighted: hasHighlight(i), num: Number(m[3]), label: m[4].trim(), isSubmit: false });
      }
    }

    const pick = (items, multi) => {
      if (items.length < 2) return null;
      let list = items;
      if (!multi) {
        let lastOne = -1;
        for (let i = list.length - 1; i >= 0; i--) {
          if (list[i].num === 1) { lastOne = i; break; }
        }
        if (lastOne < 0) return null;
        const seq = [list[lastOne]];
        for (let i = lastOne + 1; i < list.length; i++) {
          if (list[i].num === seq[seq.length - 1].num + 1) seq.push(list[i]);
          else break;
        }
        list = seq;
        if (list.length < 2) return null;
      }
      let pointedIdxs = list.map((it, idx) => it.pointed ? idx : -1).filter(i => i >= 0);
      if (pointedIdxs.length !== 1) {
        pointedIdxs = list.map((it, idx) => it.highlighted ? idx : -1).filter(i => i >= 0);
      }
      if (pointedIdxs.length !== 1) return null;
      const current = pointedIdxs[0];
      const out = list.map((it, idx) => {
        const nextRow = idx + 1 < list.length ? list[idx + 1].row : n;
        let endRow = it.row;
        for (let r = it.row + 1; r < nextRow; r++) {
          const t = plain(r).trim();
          if (!t || RULE_RE.test(t) || HINT_RE.test(t)) break;
          if (r - it.row >= 5) break;
          endRow = r;
        }
        return { ...it, index: idx, endRow };
      });
      return { multi, current, items: out };
    };

    return pick(checkItems, true) || pick(numItems, false);
  }

  syncMenuMarks() {
    this.menu = this.findMenu();
    const rows = new Set();
    if (this.menu) {
      for (const item of this.menu.items) {
        for (let r = item.row; r <= item.endRow; r++) rows.add(r);
      }
    }
    const total = this.live.children.length + this.dock.children.length;
    for (let i = 0; i < total; i++) {
      const node = this.lineAt(i);
      if (node) node.classList.toggle('choice', rows.has(i));
    }
  }

  menuItemForNode(ln) {
    if (!this.menu) return null;
    let row = [...this.live.children].indexOf(ln);
    if (row < 0) {
      const d = [...this.dock.children].indexOf(ln);
      if (d < 0) return null;
      row = this.live.children.length + d;
    }
    return this.menu.items.find(it => row >= it.row && row <= it.endRow) || null;
  }

  selectMenuItem(menu, item) {
    if (!this.room || !menu || !item) return;
    const delta = item.index - menu.current;
    const arrow = delta > 0 ? 'Down' : 'Up';
    for (let i = 0; i < Math.abs(delta); i++) send(this, 'keys', arrow);
    const delay = delta ? 80 : 0;
    const act = () => {
      if (item.isSubmit || !menu.multi) send(this, 'keys', 'Enter');
      else send(this, 'text', ' ');
    };
    if (delay) setTimeout(act, delay); else act();
    this.focus();
  }

  answerChoice(word) {
    if (!this.room) return;
    const menu = this.findMenu();
    if (menu) {
      if (/^[1-9]$/.test(word)) {
        const n = Number(word);
        const item = menu.items.find(it => it.num === n) || menu.items[n - 1];
        if (item) { this.selectMenuItem(menu, item); return; }
      }
      if (word === 'yes') {
        if (menu.multi) { send(this, 'keys', 'Enter'); this.focus(); return; }
        const yesItem = menu.items.find(it => /^(?:yes|はい|許可|allow|proceed|ok)\b/i.test(it.label));
        if (yesItem) { this.selectMenuItem(menu, yesItem); return; }
      }
      if (word === 'no') {
        const noItem = menu.items.find(it => /^(?:no|いいえ|拒否|cancel|キャンセル|deny)\b/i.test(it.label));
        if (noItem) { this.selectMenuItem(menu, noItem); return; }
      }
    }
    this.submit(word);
  }

  caretLeft(line, col) {
    const walker = document.createTreeWalker(line, NodeFilter.SHOW_TEXT);
    const range = document.createRange();
    let c = 0, lastNode = null;
    while (walker.nextNode()) {
      const node = walker.currentNode;
      let off = 0;
      for (const ch of node.data) {
        if (c >= col) { range.setStart(node, off); range.setEnd(node, off + ch.length); return range.getBoundingClientRect().left; }
        c += cellWidth(ch); off += ch.length;
      }
      lastNode = node;
    }
    const cw = this.measure.getBoundingClientRect().width / 10;
    if (!lastNode) return line.getBoundingClientRect().left + col * cw;
    range.selectNodeContents(lastNode);
    return range.getBoundingClientRect().right + (col - c) * cw;
  }

  placeCursor([x, y], visible) {
    const line = this.lineAt(y);
    if (!line) return;
    const base = this.screen.getBoundingClientRect();
    const left = this.caretLeft(line, x) - base.left;
    const top = line.getBoundingClientRect().top - base.top + this.screen.scrollTop;
    for (const node of [this.cursor, this.ime]) { node.style.left = `${left}px`; node.style.top = `${top}px`; }
    this.cursor.hidden = !visible;
  }

  fullUrl(a) {
    if (a.dataset && a.dataset.url) return a.dataset.url;
    let url = a.textContent;
    let line = a.closest('.ln');
    const container = a.closest('.live, .hist, .dock');
    const lines = [...container.children];
    let index = lines.indexOf(line);
    if (trailingTextAfter(line, a).trim()) return trimUrlEnd(url);
    while (index + 1 < lines.length) {
      const prevFull = (line.textContent || '').trimEnd();
      const nextFull = (lines[index + 1].textContent || '').trimEnd();
      const cont = urlContinuation(prevFull, url, nextFull, this.cols || 0, 0);
      if (!cont) break;
      url += cont.raw;
      line = lines[++index];
      if (cont.indent + cont.raw.length < nextFull.length) break;
    }
    return trimUrlEnd(url);
  }

  onWheel(e) {
    if (this.alt && this.wheel) {
      e.preventDefault();
      const line = rowHeight(this.fontSize());
      this.wheelRest = (this.wheelRest || 0) + (e.deltaMode === 1 ? e.deltaY * line : e.deltaMode === 2 ? e.deltaY * this.screen.clientHeight : e.deltaY);
      if (Math.abs(this.wheelRest) < line) return;
      const up = this.wheelRest < 0;
      this.wheelRest %= line;
      send(this, 'keys', up ? 'WheelUp' : 'WheelDown');
      return;
    }
    if (this.alt) {
      e.preventDefault();
      const now = Date.now();
      if (now - (this.lastPage || 0) > 120) { this.lastPage = now; send(this, 'keys', e.deltaY < 0 ? 'PageUp' : 'PageDown'); }
      return;
    }
    const line = rowHeight(this.fontSize());
    const dy = e.deltaMode === 1 ? e.deltaY * line : e.deltaMode === 2 ? e.deltaY * this.screen.clientHeight : e.deltaY;
    if (dy < 0 && this.screen.scrollTop <= 2 && !this.historyExhausted()) {
      e.preventDefault();
      this.loadHistory(Math.min(dy, -line));
    }
  }

  historyExhausted() { return this.histAllFrame === this.frameSeq; }

  async loadHistory(deltaPx = 0) {
    if (!this.room) return;
    if (this.histPending) {
      await this.histPending;
      if (deltaPx < 0) this.screen.scrollBy(0, deltaPx);
      return;
    }
    if (this.historyExhausted()) return;
    const room = this.room;
    const gen = this.histGen;
    const seq = this.frameSeq;
    const stale = this.histAllFrame >= 0 && this.histAllFrame !== seq;
    const want = Math.min(HISTORY_MAX, stale ? Math.max(this.histLines, HISTORY_STEP) : this.histLines + HISTORY_STEP);
    const task = (async () => {
      try {
        const res = await fetch(`api/history?room=${encodeURIComponent(room)}&lines=${want}`);
        const data = await res.json();
        if (!res.ok || room !== this.room || gen !== this.histGen) return;
        const fromBottom = this.screen.scrollHeight - this.screen.scrollTop;
        this.hist.textContent = '';
        const agy = this.isAgy();
        renderParsedLines(data.lines, {
          agy,
          getLine: () => {
            const line = el('div', 'ln');
            this.hist.appendChild(line);
            return line;
          },
        });
        this.histLines = data.lines.length;
        linkifyContainer(this.hist, this.cols || 0);
        if (agy) this.applyNoiseFoldsTo(this.hist);
        this.histAllFrame = (data.lines.length < want || want >= HISTORY_MAX) ? seq : -1;
        if (data.lines.length) this.screen.scrollTop = Math.max(0, this.screen.scrollHeight - fromBottom + deltaPx);
      } catch (err) {
        this.fail(err.message);
      } finally {
        if (this.histPending === task) this.histPending = null;
      }
    })();
    this.histPending = task;
    await task;
  }

  clearHistory() {
    this.hist.textContent = '';
    this.histLines = 0;
    this.histAllFrame = -1;
    this.histPending = null;
    this.histGen += 1;
  }

  typed(jump = true) {
    if (!jump && this.dock.childElementCount) return;
    if (this.histLines || this.histAllFrame >= 0) this.clearHistory();
    this.screen.scrollTop = this.screen.scrollHeight;
  }

  async renameRoom() {
    const room = this.room;
    const current = this.deck.rooms.find(r => r.name === room)?.label || '';
    const label = prompt(`Rename ${room}`, current);
    if (label === null) return;
    try {
      await post('api/label', { room, label });
      await this.deck.refresh();
    } catch (err) {
      this.fail(err.message);
    }
  }

  async closeRoom() {
    if (!this.room || !confirm(`Close ${this.room}? The running process inside will be terminated.`)) return;
    const room = this.room;
    try {
      await post('api/close', { room });
      this.show(null);
      this.deck.refresh();
    } catch (err) {
      this.fail(err.message);
    }
  }

  renderChooser() {
    const d = this.deck;
    this.chooser.textContent = '';
    const holders = new Map();
    for (const p of d.panes.filter(p => p !== this)) {
      if (p.room) holders.set(`r:${p.room}`, p);
      if (p.isMenuPane) holders.set('m:menu', p);
    }
    const section = title => this.chooser.appendChild(el('div', 'sec-title', title));
    const item = (key, state, name, label, open) => {
      const b = el('button', holders.has(key) ? 'pick elsewhere' : 'pick');
      b.append(el('span', state ? `dot on state-${state}` : 'dot'), el('span', 'name', name));
      if (label) b.appendChild(el('span', 'label', label));
      b.onclick = () => {
        const holder = holders.get(key);
        if (holder) holder.show(null);
        d.setActive(this);
        open();
      };
      this.chooser.appendChild(b);
    };
    section('MENU');
    item('m:menu', '', 'Menu', 'Rooms / Agent Status / Settings', () => this.showMenu());
    const byName = Object.fromEntries(d.rooms.map(r => [r.name, r]));
    const order = [byName.main, byName.watch, ...d.rooms.filter(r => r.room && r.name !== 'main' && r.name !== 'watch'),
      ...d.rooms.filter(r => !r.room)].filter(Boolean);
    section('ROOMS');
    for (const r of order) item(`r:${r.name}`, r.state, r.name, r.label, () => this.show(r.name));
    const make = el('button', 'pick add', '＋ New room');
    make.onclick = () => { d.setActive(this); d.newRoom(); };
    this.chooser.appendChild(make);
  }
}

const WIN_LABELS = { session: '5h', weekly_all: '7d', weekly_scoped: 'Scoped', '3p-5h': 'Other 5h', '3p-7d': 'Other 7d' };
const WIN_HOURS = { session: 5, '5h': 5, '3p-5h': 5, weekly_all: 168, weekly_scoped: 168, '7d': 168, '3p-7d': 168 };

function resetSeconds(reset) { return reset > 1e12 ? reset / 1000 : reset; }

function untilText(reset, now) {
  if (reset <= 0) return '';
  const left = Math.floor(resetSeconds(reset) - now);
  if (left <= 0) return '0m';
  const d = Math.floor(left / 86400), h = Math.floor(left % 86400 / 3600), m = Math.floor(left % 3600 / 60);
  return d ? `${d}d${h}h` : h ? `${h}h${m}m` : `${m}m`;
}

function evenPoint(win, reset, now) {
  const hours = WIN_HOURS[win];
  if (!hours || reset <= 0) return null;
  const end = resetSeconds(reset), start = end - hours * 3600;
  return now < start || now > end ? null : (now - start) / (end - start) * 100;
}

function paceHue(p, e) {
  if (e === null) return (100 - p) * 1.2;
  if (p >= 100) return 0;
  if (e <= 0) return p <= 0 ? 120 : 0;
  if (p <= e) return 120 - 60 * (p / e);
  return 100 - e <= 0 ? 0 : 60 * (1 - (p - e) / (100 - e));
}

function renderUsage(data) {
  const box = document.getElementById('usage');
  box.textContent = '';
  const now = Date.now() / 1000;
  let agentCount = 0;
  let thirdLastRow = null;
  for (const a of data.agents) {
    if (!a.windows.length) continue;
    agentCount++;
    box.appendChild(el('div', `acct${a.ok && !a.stale ? '' : ' stale'}`, a.label));
    for (const w of a.windows) {
      const credit = w.win.startsWith('credit ');
      const pct = Math.max(0, Math.min(100, Number(w.pct) || 0));
      const even = credit ? null : evenPoint(w.win, Number(w.reset) || 0, now);
      const row = el('div', 'win');
      const track = el('div', 'trk');
      const fill = el('div', 'fil');
      fill.style.width = `${pct}%`;
      fill.style.background = `hsl(${paceHue(pct, even).toFixed(1)},78%,48%)`;
      track.appendChild(fill);
      if (even !== null) { const mark = el('div', 'pc'); mark.style.left = `${even}%`; track.appendChild(mark); }
      row.append(el('span', 'l', credit ? 'credit' : WIN_LABELS[w.win] || w.win), track, el('span', 'v', `${Math.round(pct)}%`),
        el('span', 'r', credit ? w.win.slice(7) : untilText(Number(w.reset) || 0, now)));
      box.appendChild(row);
      if (agentCount === 3) thirdLastRow = row;
    }
  }
  if (thirdLastRow) {
    const h = thirdLastRow.offsetTop + thirdLastRow.offsetHeight + 2;
    if (h > 60) {
      box.style.setProperty('--usage-default-h', `${h}px`);
      const saved = Number(store.get('usageHeight', 0));
      box.style.height = `${saved >= 36 ? saved : h}px`;
    }
  }
}

function renderLoad(d) {
  deck.load = d;
  const box = document.getElementById('load');
  box.textContent = '';
  if (!d) return;
  const pc = el('div', 'mrow');
  const values = el('span', 'row');
  const item = (name, value, warn) => {
    const it = el('span', warn ? 'item warn' : 'item');
    it.append(el('span', '', name), el('b', '', value));
    values.appendChild(it);
  };
  item('CPU', d.cpu === null ? '—' : `${d.cpu}%`, d.cpu !== null && d.cpu >= 90);
  item('Memory', d.memory === null ? '—' : `${d.memory}%`, d.memory !== null && d.memory >= 85);
  item('Disk', d.diskFreeGb === null ? '—' : `${d.diskFreeGb}GB`, d.diskFreeGb !== null && d.diskFreeGb < 20);
  pc.append(el('b', '', 'HOST'), values);
  box.appendChild(pc);
}

document.addEventListener('keydown', e => {
  if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 'c') return;
  const sel = window.getSelection();
  const pane = deck.panes.find(p => !sel.isCollapsed && p.screen.contains(sel.anchorNode));
  if (!pane) return;
  e.preventDefault();
  pane.copySelection();
});

const deck = {
  root: null,
  panes: [],
  active: null,
  rooms: [],
  commands: [],
  buildId: null,
  pendingReload: false,
  lastInputAt: 0,
  clients: [],
  home: '',
  source: null,
  sourceRooms: '',
  claims: new Set(),

  init() {
    this.restore();
    this.bindSideResizer();
    const markInput = () => { this.lastInputAt = Date.now(); };
    for (const ev of ['keydown', 'beforeinput', 'input', 'compositionstart', 'pointerdown', 'touchstart']) {
      window.addEventListener(ev, markInput, { capture: true, passive: true });
    }
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) this.disconnect();
      else this.resubscribe();
    });
    this.refresh().then(() => {
      const names = new Set(this.rooms.map(r => r.name));
      if (FORCE_EMBED) {
        const target = EMBED_ROOM && names.has(EMBED_ROOM) ? EMBED_ROOM : null;
        this.panes[0].show(target, false);
        return;
      }
      for (const p of this.panes) {
        if (p.wantedMenu) p.showMenu();
        else p.show(p.wanted && names.has(p.wanted) ? p.wanted : null, false);
      }
      if (this.panes.length === 1 && !this.panes[0].isMenuPane && !this.panes[0].room && names.has('main')) this.panes[0].show('main', false);
    });
    window.addEventListener('focus', () => {
      if (this.active) this.active.refit();
    });
    setInterval(() => this.refresh(), 3000);
    this.poll('api/usage', renderUsage, 60000, () => { document.getElementById('usage').textContent = ''; });
    this.poll('api/load', renderLoad, 5000);
    this.bindView();
  },

  restore() {
    if (FORCE_EMBED) {
      const pane = new Pane(this);
      pane.wanted = EMBED_ROOM || null;
      this.root = { pane };
      this.layout();
      this.setActive(this.panes[0]);
      return;
    }
    const build = node => {
      if (node && node.dir && node.a && node.b) return { dir: node.dir, a: build(node.a), b: build(node.b) };
      const pane = new Pane(this);
      pane.wanted = node && node.room;
      pane.wantedMenu = Boolean(node && node.menu);
      return { pane };
    };
    const saved = store.get(`win:${slot}`, null);
    this.root = build(saved && saved.tree);
    this.layout();
    this.setActive(this.panes[0]);
  },

  serialize(node) {
    if (node.pane) {
      if (node.pane.isMenuPane || node.pane.wantedMenu) return { menu: true };
      return { room: node.pane.room };
    }
    return { dir: node.dir, a: this.serialize(node.a), b: this.serialize(node.b) };
  },

  leaves(node, out = []) {
    if (node.pane) out.push(node.pane); else { this.leaves(node.a, out); this.leaves(node.b, out); }
    return out;
  },

  count(node, dir) { return node.dir === dir ? this.count(node.a, dir) + this.count(node.b, dir) : 1; },

  layout() {
    const host = document.getElementById('panes');
    const render = node => {
      if (node.pane) { node.el = node.pane.node; node.el.style.flex = ''; return node.el; }
      const box = el('div', `split ${node.dir}`);
      const a = render(node.a), b = render(node.b);
      const bar = el('div', `divider ${node.dir}`);
      a.style.flex = `${this.count(node.a, node.dir)} 1 0px`;
      b.style.flex = `${this.count(node.b, node.dir)} 1 0px`;
      box.append(a, bar, b);
      this.bindDivider(bar, box, a, b, node.dir);
      node.el = box;
      return box;
    };
    const top = render(this.root);
    top.style.flex = '';
    host.replaceChildren(top);
    this.panes = this.leaves(this.root);
  },

  bindDivider(bar, box, a, b, dir) {
    bindPointerDrag(bar, e => {
      e.preventDefault();
      const row = dir === 'row';
      const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
      const start = row ? ra.left : ra.top;
      const total = row ? rb.right - ra.left : rb.bottom - ra.top;
      const size = row ? bar.offsetWidth : bar.offsetHeight;
      return {
        move: ev => {
          const first = Math.max(60, Math.min(total - size - 60, (row ? ev.clientX : ev.clientY) - start));
          a.style.flex = `${first} 1 0px`;
          b.style.flex = `${total - size - first} 1 0px`;
        },
      };
    });
  },

  findParent(target, node = this.root, parent = null) {
    if (node === target) return { parent };
    if (node.pane) return null;
    return this.findParent(target, node.a, node) || this.findParent(target, node.b, node);
  },

  leafOf(pane, node = this.root) {
    if (node.pane) return node.pane === pane ? node : null;
    return this.leafOf(pane, node.a) || this.leafOf(pane, node.b);
  },

  replaceNode(oldNode, newNode) {
    const { parent } = this.findParent(oldNode);
    if (!parent) this.root = newNode;
    else if (parent.a === oldNode) parent.a = newNode;
    else parent.b = newNode;
  },

  split(pane, side) {
    const leaf = this.leafOf(pane);
    const fresh = { pane: new Pane(this) };
    const dir = side === 'left' || side === 'right' ? 'row' : 'col';
    const first = side === 'left' || side === 'up';
    this.replaceNode(leaf, { dir, a: first ? fresh : leaf, b: first ? leaf : fresh });
    this.layout();
    fresh.pane.show(null);
    this.setActive(fresh.pane);
    return fresh.pane;
  },

  targetPane(pane) {
    if (pane) return pane;
    if (isMobile() || FORCE_EMBED) return this.active;
    const isEmpty = p => !p.room && !p.isMenuPane;
    if (this.active && isEmpty(this.active)) return this.active;
    const empty = this.panes.find(isEmpty);
    if (empty) return empty;
    const base = this.active || this.panes[this.panes.length - 1];
    const side = base.node.clientWidth >= Math.max(520, base.node.clientHeight) ? 'right' : 'down';
    return this.split(base, side);
  },

  menuTargetPane() {
    if (!isMobile() && this.active && this.active.isMenuPane && this.panes.length > 1) {
      return this.panes.find(p => !p.isMenuPane) || this.active;
    }
    return this.active;
  },

  removePane(pane) {
    pane.dropMenu();
    if (this.panes.length === 1) { pane.show(null); return; }
    const leaf = this.leafOf(pane);
    const { parent } = this.findParent(leaf);
    this.replaceNode(parent, parent.a === leaf ? parent.b : parent.a);
    this.layout();
    if (this.active === pane) this.setActive(this.panes[0]);
    this.changed();
  },

  setActive(pane) {
    this.active = pane;
    for (const p of this.panes) p.node.classList.toggle('inactive', p !== pane && this.panes.length > 1);
    pane.refit();
  },

  changed() {
    if (!FORCE_EMBED) store.set(`win:${slot}`, { tree: this.serialize(this.root) });
    this.renderRooms();
    this.resubscribe();
  },

  resubscribe() {
    clearTimeout(this.subTimer);
    this.subTimer = setTimeout(() => this.connect(), 30);
  },

  connect() {
    if (document.hidden) return;
    const rooms = [...new Set(this.panes.map(p => p.room).filter(Boolean))].sort().join(',');
    if (this.source && rooms === this.sourceRooms) return;
    this.disconnect();
    this.sourceRooms = rooms;
    if (!rooms) return;
    const claim = [...this.claims].filter(r => this.panes.some(p => p.room === r)).join(',');
    this.claims.clear();
    const source = new EventSource(`api/stream?rooms=${encodeURIComponent(rooms)}&win=${winId}&claim=${encodeURIComponent(claim)}`);
    const paneOf = room => this.panes.find(p => p.room === room);
    source.addEventListener('moved', e => {
      const p = paneOf(JSON.parse(e.data).room);
      if (p) this.removePane(p);
    });
    source.onmessage = e => { const f = JSON.parse(e.data); const p = paneOf(f.room); if (p) p.frame(f); };
    source.addEventListener('failure', e => {
      const f = JSON.parse(e.data);
      const p = paneOf(f.room);
      if (p) p.fail(`Stream error: ${f.error}`);
    });
    source.onerror = () => {
      if (claim) { this.disconnect(); setTimeout(() => this.resubscribe(), 1000); return; }
      for (const p of this.panes) if (p.room) p.fail('Stream disconnected');
    };
    this.source = source;
  },

  disconnect() {
    if (this.source) { this.source.close(); this.source = null; }
    this.sourceRooms = '';
  },

  poll(path, render, every, onFail) {
    const run = async () => {
      try {
        const res = await fetch(path);
        if (!res.ok) throw new Error(res.status);
        render(await res.json());
      } catch {
        if (onFail) onFail();
      }
    };
    run();
    setInterval(run, every);
  },

  async refresh() {
    try {
      const res = await fetch('api/rooms');
      const data = await res.json();
      if (data.buildId) {
        if (this.buildId && this.buildId !== data.buildId) this.pendingReload = true;
        this.buildId = data.buildId;
      }
      if (this.pendingReload && (document.hidden || Date.now() - this.lastInputAt >= 10000)) {
        this.pendingReload = false;
        this.reloadPage();
        return;
      }
      this.rooms = data.rooms || [];
      this.clients = data.clients || [];
      this.home = data.home || '';
      const nextCmds = Array.isArray(data.commands) ? data.commands : [];
      if (JSON.stringify(nextCmds) !== JSON.stringify(this.commands)) {
        this.commands = nextCmds;
        for (const p of this.panes) p.syncCommands();
      }
      this.checkAttentionSound();
      this.renderRooms();
    } catch { /* keep the last list */ }
  },

  playChime() {
    if (!store.get('sound', true)) return;
    const now = Date.now();
    if (this._lastChimeAt && now - this._lastChimeAt < 5000) return;
    this._lastChimeAt = now;
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      if (!this._audioCtx) this._audioCtx = new Ctx();
      const ctx = this._audioCtx;
      if (ctx.state === 'suspended') ctx.resume().catch(() => {});
      const t = ctx.currentTime;
      for (const [freq, dt, dur] of [[587.33, 0, 0.14], [880, 0.11, 0.18]]) {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(freq, t + dt);
        gain.gain.setValueAtTime(0.0001, t + dt);
        gain.gain.exponentialRampToValueAtTime(0.08, t + dt + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t + dt + dur);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(t + dt);
        osc.stop(t + dt + dur + 0.02);
      }
    } catch { /* audio unavailable */ }
  },

  checkAttentionSound() {
    const states = new Map(this.rooms.map(r => [r.name, r.state]));
    if (this._prevRoomStates) {
      let chime = false;
      for (const [name, st] of states) {
        const prev = this._prevRoomStates.get(name);
        if (st === 'approval' && prev !== 'approval') chime = true;
        if (name === 'main' && prev === 'working' && st === 'input') chime = true;
      }
      if (chime) this.playChime();
    }
    this._prevRoomStates = states;
  },

  reloadPage() {
    location.reload();
  },

  openMenu(pane) {
    const target = pane || this.active;
    if (!target) return;
    target.showMenu();
    this.setActive(target);
  },

  openRoom(name, pane) {
    document.getElementById('app').classList.remove('drawer');
    const holder = this.panes.find(p => p.room === name);
    if (holder) { this.setActive(holder); holder.focus(); return; }
    const target = pane || this.active;
    target.show(name);
    this.setActive(target);
    target.focus();
  },

  dotClassForState(state) {
    if (state === 'working') return 'd g';
    if (state === 'input') return 'd r';
    if (state === 'approval') return 'd y';
    return 'd';
  },

  renderRoomView(shown) {
    const view = document.getElementById('v-room');
    if (!view) return;
    const scrolled = view.scrollTop;
    view.textContent = '';
    const byName = Object.fromEntries(this.rooms.map(r => [r.name, r]));
    const ordered = [
      byName.main,
      byName.watch,
      ...this.rooms.filter(r => r.room && r.name !== 'main' && r.name !== 'watch'),
      ...this.rooms.filter(r => !r.room),
    ].filter(Boolean);
    for (const r of ordered) {
      const item = el('div', 'item' + (shown.has(r.name) ? ' shown' : ''));
      const dot = el('span', this.dotClassForState(r.state));
      dot.title = STATE_LABELS[r.state] || r.state || '';
      const labelText = r.label ? `${r.name}  ${r.label}` : r.name;
      item.append(dot, el('span', 'n', labelText), el('span', 's', r.client || ''));
      item.onclick = () => this.openRoom(r.name, this.menuTargetPane());
      view.appendChild(item);
    }
    const addBtn = el('button', 'add-room', '＋ New room');
    addBtn.onclick = () => this.newRoom(true);
    view.appendChild(addBtn);
    view.scrollTop = scrolled;
  },

  renderRooms() {
    const shown = new Set(this.panes.map(p => p.room));
    const byName = Object.fromEntries(this.rooms.map(r => [r.name, r]));
    this.renderRoomView(shown);
    for (const p of this.panes) {
      p.select.textContent = '';
      if (!p.room && !p.isMenuPane) { const o = el('option', '', '—'); o.value = ''; p.select.appendChild(o); }
      const menuOpt = el('option', '', 'Menu');
      menuOpt.value = MENU_OPTION;
      p.select.appendChild(menuOpt);
      for (const r of this.rooms) {
        const o = el('option', '', `${r.name}${r.label ? ' ' + r.label : ''}`);
        o.value = r.name;
        p.select.appendChild(o);
      }
      if (p.room) { const o = el('option', '', 'Rename…'); o.value = RENAME; p.select.appendChild(o); }
      p.select.value = p.isMenuPane ? MENU_OPTION : (p.room || '');
      const state = p.room ? byName[p.room]?.state : '';
      p.stateDot.className = state ? `dot state-dot on state-${state}` : 'dot state-dot';
      if (!p.room && !p.isMenuPane) p.renderChooser();
    }
  },

  newRoom(splitIfFull = false, role = null) {
    const dialog = document.getElementById('new-dialog');
    const form = document.getElementById('new-form');
    const clientSel = form.elements.client;
    const dirSel = form.elements.dir;
    const browser = document.getElementById('dir-browser');
    document.getElementById('new-error').textContent = '';
    clientSel.textContent = '';
    for (const c of this.clients) { const o = el('option', '', CLIENT_LABELS[c] || c); o.value = c; clientSel.appendChild(o); }
    const clientKey = role ? `lastClient-${role}` : 'lastClient';
    clientSel.value = store.get(clientKey, this.clients[0] || 'claude');
    if (!clientSel.value && this.clients.length) clientSel.value = this.clients[0];
    dirSel.closest('label').hidden = Boolean(role);
    form.elements.name.closest('label').hidden = Boolean(role);
    const recent = store.get('recentDirs', []);
    dirSel.textContent = '';
    for (const d of [this.home, ...recent.filter(d => d !== this.home)]) { const o = el('option', '', d); o.value = d; dirSel.appendChild(o); }
    const other = el('option', '', 'Browse…');
    other.value = '';
    dirSel.appendChild(other);
    dirSel.value = this.home;
    browser.hidden = true;
    dirSel.onchange = () => { if (!dirSel.value) this.browseDirs(this.home); };
    form.elements.name.value = '';
    form.onsubmit = async e => {
      if (e.submitter && e.submitter.value === 'cancel') return;
      e.preventDefault();
      const dir = dirSel.value || this.home;
      try {
        const data = role
          ? await post('api/open', { client: clientSel.value, role })
          : await post('api/open', { client: clientSel.value, dir, name: form.elements.name.value });
        store.set(clientKey, clientSel.value);
        if (!role) store.set('recentDirs', [dir, ...recent.filter(d => d !== dir)].slice(0, 5));
        dialog.close();
        await this.refresh();
        this.openRoom(data.room, splitIfFull ? this.targetPane() : null);
      } catch (err) {
        document.getElementById('new-error').textContent = err.message;
      }
    };
    dialog.showModal();
  },

  async browseDirs(path) {
    const browser = document.getElementById('dir-browser');
    const dirSel = document.getElementById('new-form').elements.dir;
    const res = await fetch(`api/dirs?path=${encodeURIComponent(path)}`);
    const data = await res.json();
    if (!res.ok) return;
    browser.hidden = false;
    document.getElementById('dir-path').textContent = data.path;
    let opt = [...dirSel.options].find(o => o.dataset.browsed);
    if (!opt) { opt = el('option'); opt.dataset.browsed = '1'; dirSel.insertBefore(opt, dirSel.lastChild); }
    opt.value = data.path;
    opt.textContent = data.path;
    dirSel.value = data.path;
    const list = document.getElementById('dir-list');
    list.textContent = '';
    if (data.parent) { const up = el('button', '', '← Up'); up.type = 'button'; up.onclick = () => this.browseDirs(data.parent); list.appendChild(up); }
    for (const name of data.dirs) {
      const b = el('button', '', `${name}/`);
      b.type = 'button';
      b.onclick = () => this.browseDirs(`${data.path}/${name}`);
      list.appendChild(b);
    }
  },

  bindView() {
    const show = () => { document.getElementById('fs-base').textContent = baseFs(); };
    const step = d => {
      store.set('fsBase', clampFs(baseFs() + d));
      try {
        for (const name of Object.keys(localStorage).filter(k => k.startsWith('fs:') && !k.startsWith('fs:m:'))) localStorage.removeItem(name);
      } catch { /* storage unavailable */ }
      show();
      for (const p of this.panes) { if (p.room) p.applyFont(); }
    };
    document.getElementById('fs-down').onclick = () => step(-1);
    document.getElementById('fs-up').onclick = () => step(1);
    narrowQuery.addEventListener('change', () => {
      document.documentElement.classList.toggle('mobile-mode', isMobile());
      show();
      for (const p of this.panes) { if (p.room) p.applyFont(); }
    });
    const soundBtn = document.getElementById('sound-toggle');
    if (soundBtn) {
      const syncSound = () => {
        const on = store.get('sound', true);
        soundBtn.textContent = on ? '🔔' : '🔕';
        soundBtn.title = on ? 'Attention sound ON' : 'Attention sound OFF';
      };
      syncSound();
      soundBtn.onclick = () => {
        const next = !store.get('sound', true);
        store.set('sound', next);
        syncSound();
        if (next) { this._lastChimeAt = 0; this.playChime(); }
      };
    }
    const pick = document.getElementById('theme-select');
    for (const [name, t] of Object.entries(THEMES)) { const o = el('option', '', t.label); o.value = name; pick.appendChild(o); }
    pick.value = currentTheme();
    pick.onchange = () => {
      try { localStorage.setItem('theme', pick.value); } catch { /* storage unavailable */ }
      applyTheme(pick.value);
    };
    addEventListener('storage', ev => {
      if (ev.key !== 'theme') return;
      pick.value = currentTheme();
    });
    show();
  },

  bindSideResizer() {
    const app = document.getElementById('app');
    const width = store.get('sideWidth', 260);
    app.style.setProperty('--side-w', `${width}px`);
    const bar = document.getElementById('side-resizer');
    bindPointerDrag(bar, () => ({
      move: ev => app.style.setProperty('--side-w', `${Math.max(180, ev.clientX)}px`),
      up: ev => store.set('sideWidth', Math.max(180, ev.clientX)),
    }));
    const bindRowResizer = (barId, targetId, key, minH, maxH) => {
      const hBar = document.getElementById(barId);
      const target = document.getElementById(targetId);
      if (!hBar || !target) return;
      const saved = Number(store.get(key, 0));
      if (saved >= minH) target.style.height = `${Math.min(maxH, saved)}px`;
      bindPointerDrag(hBar, e => {
        e.preventDefault();
        const startY = e.clientY;
        const startH = target.getBoundingClientRect().height;
        const apply = ev => {
          const nextH = Math.max(minH, Math.min(maxH, Math.round(startH + (ev.clientY - startY))));
          target.style.height = `${nextH}px`;
          return nextH;
        };
        return {
          move: ev => { apply(ev); },
          up: ev => { store.set(key, apply(ev)); },
        };
      });
    };
    bindRowResizer('usage-resizer', 'usage', 'usageHeight', 36, 420);
  },
};

deck.init();
