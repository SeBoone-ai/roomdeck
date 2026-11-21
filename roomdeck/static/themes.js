'use strict';

const THEMES = {
  navy: {
    label: 'Navy',
    background: '#0e1524', foreground: '#c8d0dc', cursor: '#c8d0dc', cursorText: '#0e1524',
    selectionBackground: '#3a4a66', selectionForeground: '#ffffff',
    palette: ['#1c2433', '#e5534b', '#57ab5a', '#c69026', '#539bf5', '#b083f0', '#39c5cf', '#c8d0dc',
      '#636e7b', '#ff938a', '#6bc46d', '#daaa3f', '#6cb6ff', '#dcbdfb', '#56d4dd', '#f0f3f6'],
  },
  light: {
    label: 'Light',
    muted: '78%', dim: '.78',
    frame: '#e0e0df', line: '#c9cacb', c8bg: '#e3e3e2', inactiveBg: '#f0f0ee', inactiveFilter: 'none',
    accent: '#0969da', ok: '#187733', warn: '#a94a00', danger: '#c21f2b', approval: '#8f6c00',
    background: '#f8f8f6', foreground: '#24292f', cursor: '#24292f', cursorText: '#f8f8f6',
    selectionBackground: '#b6d3f5', selectionForeground: '#000000',
    palette: ['#24292f', '#cf222e', '#116329', '#7d4e00', '#0550ae', '#7a45d8', '#17747b', '#2f363d',
      '#57606a', '#a40e26', '#187733', '#8f5f00', '#0969da', '#6639ba', '#17747b', '#0d1117'],
  },
  black: {
    label: 'Black',
    background: '#000000', foreground: '#d4d4d4', cursor: '#d4d4d4', cursorText: '#000000',
    selectionBackground: '#3a3d41', selectionForeground: '#ffffff',
    palette: ['#000000', '#cd3131', '#0dbc79', '#e5e510', '#2472c8', '#bc3fbc', '#11a8cd', '#e5e5e5',
      '#666666', '#f14c4c', '#23d18b', '#f5f543', '#3b8eea', '#d670d6', '#29b8db', '#ffffff'],
  },
  tokyo: {
    label: 'Tokyo Night',
    frame: '#16161e', line: '#2f3549',
    accent: '#7aa2f7', accentFg: '#15161e', ok: '#9ece6a', warn: '#e0af68', danger: '#f7768e',
    background: '#1a1b26', foreground: '#c0caf5', cursor: '#c0caf5', cursorText: '#1a1b26',
    selectionBackground: '#283457', selectionForeground: '#ffffff',
    palette: ['#15161e', '#f7768e', '#9ece6a', '#e0af68', '#7aa2f7', '#bb9af7', '#7dcfff', '#a9b1d6',
      '#565f89', '#ff7a93', '#b9f27c', '#ff9e64', '#7da6ff', '#bb9af7', '#0db9d7', '#c0caf5'],
  },
  mocha: {
    label: 'Catppuccin Mocha',
    frame: '#181825', line: '#313244',
    accent: '#89b4fa', accentFg: '#11111b', ok: '#a6e3a1', warn: '#f9e2af', danger: '#f38ba8',
    background: '#1e1e2e', foreground: '#cdd6f4', cursor: '#cdd6f4', cursorText: '#1e1e2e',
    selectionBackground: '#313244', selectionForeground: '#cdd6f4',
    palette: ['#45475a', '#f38ba8', '#a6e3a1', '#f9e2af', '#89b4fa', '#cba6f7', '#94e2d5', '#bac2de',
      '#6c7086', '#f38ba8', '#a6e3a1', '#f9e2af', '#89b4fa', '#f5c2e7', '#94e2d5', '#cdd6f4'],
  },
  nord: {
    label: 'Nord',
    frame: '#272c36', line: '#434c5e',
    accent: '#88c0d0', accentFg: '#2e3440', ok: '#a3be8c', warn: '#ebcb8b', danger: '#bf616a',
    background: '#2e3440', foreground: '#eceff4', cursor: '#eceff4', cursorText: '#2e3440',
    selectionBackground: '#434c5e', selectionForeground: '#eceff4',
    palette: ['#3b4252', '#bf616a', '#a3be8c', '#ebcb8b', '#81a1c1', '#b48ead', '#88c0d0', '#e5e9f0',
      '#7b88a1', '#bf616a', '#a3be8c', '#ebcb8b', '#81a1c1', '#b48ead', '#8fbcbb', '#eceff4'],
  },
  solarized: {
    label: 'Solarized Dark',
    frame: '#073642', line: '#1f4d59',
    accent: '#268bd2', ok: '#859900', warn: '#b58900', danger: '#dc322f',
    background: '#002b36', foreground: '#93a1a1', cursor: '#93a1a1', cursorText: '#002b36',
    selectionBackground: '#0b4452', selectionForeground: '#fdf6e3',
    palette: ['#073642', '#dc322f', '#859900', '#b58900', '#268bd2', '#6c71c4', '#2aa198', '#eee8d5',
      '#657b83', '#cb4b16', '#586e75', '#657b83', '#839496', '#6c71c4', '#93a1a1', '#fdf6e3'],
  },
  paper: {
    label: 'Warm Paper',
    colorScheme: 'light',
    muted: '78%', dim: '.78',
    frame: '#eee6d8', line: '#d4c9b6', c8bg: '#e5dccb', inactiveBg: '#f2ebdd', inactiveFilter: 'none',
    accent: '#1d5fa7', ok: '#2a7239', warn: '#9a5b00', danger: '#b83227', approval: '#8f6c00',
    background: '#fbf7ef', foreground: '#2c2721', cursor: '#2c2721', cursorText: '#fbf7ef',
    selectionBackground: '#dce6f2', selectionForeground: '#1a1714',
    palette: ['#2c2721', '#b83227', '#2a7239', '#9a5b00', '#1d5fa7', '#7448a8', '#176e75', '#3a332b',
      '#766a5b', '#9c251c', '#215c2d', '#7d4900', '#174f8c', '#5e378c', '#12595f', '#1a1714'],
  },
};

function currentTheme() {
  try { return THEMES[localStorage.getItem('theme')] ? localStorage.getItem('theme') : 'navy'; } catch { return 'navy'; }
}

function applyTheme(name, target = document.documentElement) {
  const t = THEMES[name] || THEMES.navy;
  const vars = {
    '--bg': t.background, '--fg': t.foreground, '--cursor': t.cursor, '--cursor-text': t.cursorText,
    '--sel-bg': t.selectionBackground, '--sel-fg': t.selectionForeground,
    '--muted-mix': t.muted || '55%', '--dim': t.dim || '.6',
    '--accent': t.accent || '#5b8def', '--accent-fg': t.accentFg || '#ffffff', '--ok': t.ok || '#57ab5a', '--warn': t.warn || '#e5a23a', '--danger': t.danger || '#e5534b',
    '--approval': t.approval || '#e3b341',
  };
  const optional = { '--frame-x': t.frame, '--line-x': t.line, '--c8bg': t.c8bg, '--inactive-bg': t.inactiveBg, '--inactive-filter': t.inactiveFilter };
  for (const [k, v] of Object.entries(optional)) { if (v) vars[k] = v; else target.style.removeProperty(k); }
  t.palette.forEach((c, i) => { vars[`--c${i}`] = c; });
  for (const [k, v] of Object.entries(vars)) target.style.setProperty(k, v);
  if (target === document.documentElement) {
    const scheme = t.colorScheme === 'light' || name === 'light' ? 'light' : 'dark';
    document.documentElement.style.colorScheme = scheme;
  }
}

applyTheme(currentTheme());
addEventListener('storage', e => { if (e.key === 'theme') applyTheme(currentTheme()); });
