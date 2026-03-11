'use strict';

// ── State ──────────────────────────────────────────────────────────────────
let bridge = null;
let algorithms = [];
let currentKeywords = [];
let highlightOn = false;
let rawSummary = '';
let isRunning = false;
let searchTimeout = null;
let lastSearch = '';

// ── Init WebChannel ────────────────────────────────────────────────────────
new QWebChannel(qt.webChannelTransport, function (channel) {
  bridge = channel.objects.bridge;

  // Load algorithm list
  bridge.getAlgorithms(function (json) {
    algorithms = JSON.parse(json);
    const sel = document.getElementById('algo-select');
    sel.innerHTML = '';
    algorithms.forEach(a => {
      const opt = document.createElement('option');
      opt.value = a.id;
      opt.textContent = a.id;
      sel.appendChild(opt);
    });
    sel.value = 'Hybrid';
    updateAlgoCard('Hybrid');
  });

  // Listen for summary results
  bridge.summaryReady.connect(function (json) {
    const data = JSON.parse(json);
    setRunning(false);
    rawSummary = data.summary;
    currentKeywords = data.keywords;
    renderSummary();
    renderKeywords();
    updateStats(data);
  });
});

// ── Algorithm card ─────────────────────────────────────────────────────────
function updateAlgoCard(id) {
  const a = algorithms.find(x => x.id === id);
  if (!a) return;
  document.getElementById('algo-card-name').textContent = id;
  document.getElementById('algo-card-short').textContent = a.desc;
  document.getElementById('algo-card-tip').textContent = a.tip;
}

function onAlgoChange() {
  const id = document.getElementById('algo-select').value;
  updateAlgoCard(id);
}

// ── Input stats ────────────────────────────────────────────────────────────
function onInputChange() {
  const text = document.getElementById('input-area').value;
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  document.getElementById('in-stat').textContent = words > 0 ? `${words.toLocaleString()} words` : '';
}

// ── Summarize ──────────────────────────────────────────────────────────────
function runSummarize() {
  if (!bridge || isRunning) return;
  const text = document.getElementById('input-area').value.trim();
  if (!text) return;

  setRunning(true);
  const ratio = parseInt(document.getElementById('ratio-slider').value) / 100;
  const algo = document.getElementById('algo-select').value;
  bridge.runSummarize(text, ratio, algo);
}

function setRunning(state) {
  isRunning = state;
  const btn = document.getElementById('run-btn');
  const prog = document.getElementById('progress-wrap');
  btn.disabled = state;
  btn.textContent = state ? 'Running…' : 'Summarize';
  prog.className = state ? 'active running' : '';
}

// ── Render summary with optional highlights ────────────────────────────────
function renderSummary() {
  const out = document.getElementById('output-area');
  if (!rawSummary) {
    out.innerHTML = '';
    out.classList.add('empty');
    return;
  }
  out.classList.remove('empty');

  if (!highlightOn || !currentKeywords.length) {
    out.textContent = rawSummary;
    return;
  }

  // Build highlight spans
  const sorted = [...currentKeywords].sort((a, b) => b[1] - a[1]);
  let html = rawSummary;

  // Escape HTML
  html = html
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  const replacements = [];
  sorted.slice(0, 18).forEach(([word, score], i) => {
    const cls = score >= 0.65 ? 'hi-strong' : score >= 0.35 ? 'hi-mid' : 'hi-low';
    const placeholder = `\x01${i}\x01`;
    const re = new RegExp('\\b' + word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b', 'gi');
    html = html.replace(re, placeholder);
    replacements.push({ placeholder, mark: `<mark class="${cls}">${word}</mark>` });
  });

  replacements.forEach(({ placeholder, mark }) => {
    html = html.split(placeholder).join(mark);
  });

  html = html.replace(/\x01\d+\x01/g, '');
  out.innerHTML = html;
}

// ── Highlight toggle ───────────────────────────────────────────────────────
function onHighlightToggle() {
  highlightOn = document.getElementById('hi-toggle').checked;
  renderSummary();
}

// ── Keywords ───────────────────────────────────────────────────────────────
function renderKeywords() {
  const container = document.getElementById('kw-chips');
  container.innerHTML = '';
  currentKeywords.slice(0, 20).forEach(([word, score]) => {
    const chip = document.createElement('span');
    chip.className = 'chip fade-in' + (score >= 0.55 ? ' hi' : '');
    chip.textContent = word;
    container.appendChild(chip);
  });
}

// ── Stats ──────────────────────────────────────────────────────────────────
function updateStats(data) {
  const inText = document.getElementById('input-area').value;
  const inWords = inText.trim() ? inText.trim().split(/\s+/).length : 0;
  const outWords = data.summary.trim() ? data.summary.trim().split(/\s+/).length : 0;
  const reduction = inWords ? Math.round((1 - outWords / inWords) * 100) : 0;
  const inSents = (inText.match(/[.!?]\s+[A-Z]/g) || []).length + 1;
  const outSents = data.indices.length;

  document.getElementById('s-words').textContent = `${outWords.toLocaleString()} / ${inWords.toLocaleString()}`;
  document.getElementById('s-sents').textContent = `${outSents} / ${inSents}`;
  document.getElementById('s-ratio').textContent = `\u2212${reduction}%`;
  document.getElementById('s-algo').textContent = document.getElementById('algo-select').value;
  document.getElementById('out-stat').textContent = `${outWords.toLocaleString()} words`;
}

// ── Clipboard ──────────────────────────────────────────────────────────────
function pasteClipboard() {
  if (!bridge) return;
  bridge.getClipboard(function (text) {
    if (text) {
      document.getElementById('input-area').value = text;
      onInputChange();
    }
  });
}

function copySummary() {
  if (!bridge || !rawSummary) return;
  bridge.copyText(rawSummary);
}

function clearAll() {
  document.getElementById('input-area').value = '';
  document.getElementById('output-area').innerHTML = '';
  document.getElementById('output-area').classList.add('empty');
  document.getElementById('kw-chips').innerHTML = '';
  document.getElementById('in-stat').textContent = '';
  document.getElementById('out-stat').textContent = '';
  document.getElementById('s-words').textContent = '\u2014';
  document.getElementById('s-sents').textContent = '\u2014';
  document.getElementById('s-ratio').textContent = '\u2014';
  document.getElementById('s-algo').textContent = '\u2014';
  rawSummary = '';
  currentKeywords = [];
}

// ── Resizable split ────────────────────────────────────────────────────────
(function () {
  const handle = document.getElementById('resize-handle');
  const split = document.getElementById('split');
  let dragging = false, startX = 0, startCols = null;

  handle.addEventListener('mousedown', e => {
    dragging = true;
    startX = e.clientX;
    const cols = getComputedStyle(split).gridTemplateColumns.split(' ');
    startCols = [parseFloat(cols[0]), parseFloat(cols[2])];
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  });

  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const dx = e.clientX - startX;
    const total = startCols[0] + startCols[2];
    const newLeft = Math.max(200, Math.min(total - 200, startCols[0] + dx));
    const newRight = total - newLeft;
    split.style.gridTemplateColumns = `${newLeft}px 6px ${newRight}px`;
  });

  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });
})();

// ── Search (Ctrl+F) ────────────────────────────────────────────────────────
function openSearch() {
  const bar = document.getElementById('search-bar');
  const inp = document.getElementById('search-input');
  bar.classList.remove('hidden');
  inp.focus();
  inp.select();
}

function closeSearch() {
  const bar = document.getElementById('search-bar');
  bar.classList.add('hidden');
  document.getElementById('search-count').textContent = '';
  if (bridge) bridge.findText('', true); // Clear highlights
}

function onSearchInput(e) {
  const val = e.target.value;
  if (val === lastSearch) return;
  
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => {
    if (!bridge) return;
    lastSearch = val;
    performSearch(val, true);
  }, 120); // Slightly faster debounce
}

function performSearch(text, forward) {
  if (!bridge) return;
  bridge.findText(text, forward);
  
  // Combat focus theft from selection. We check several times to ensure 
  // we catch the focus change which might happen asynchronously in Chromium.
  const inp = document.getElementById('search-input');
  const ensureFocus = () => {
    if (document.activeElement !== inp && !document.getElementById('search-bar').classList.contains('hidden')) {
      inp.focus();
    }
  };
  
  // Refocus almost immediately and again slightly later
  setTimeout(ensureFocus, 1);
  setTimeout(ensureFocus, 40);
  setTimeout(ensureFocus, 100);
}

function onSearchKeyDown(e) {
  if (e.key === 'Escape') closeSearch();
  if (e.key === 'Enter') {
    performSearch(document.getElementById('search-input').value, !e.shiftKey);
  }
}

function nextSearch() {
  performSearch(document.getElementById('search-input').value, true);
}

function prevSearch() {
  performSearch(document.getElementById('search-input').value, false);
}

// ── Keyboard shortcuts ─────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
    e.preventDefault();
    openSearch();
  }
  if (e.key === 'Escape') {
    closeSearch();
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') runSummarize();
});
