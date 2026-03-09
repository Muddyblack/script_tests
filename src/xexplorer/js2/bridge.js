// XExplorer — QWebChannel bridge helper + shared utilities
// All symbols are placed on window so app.js can access them.

// ── QWebChannel setup ────────────────────────────────────────────────────────
let _bridge = null;
let _bridgeReady = false;
const _bridgeQueue = [];

function getBridge(cb) {
    if (_bridgeReady) { cb(_bridge); return; }
    _bridgeQueue.push(cb);
}

// Async version — returns a promise
function bridge() {
    return new Promise(resolve => getBridge(resolve));
}

if (typeof QWebChannel !== 'undefined') {
    new QWebChannel(qt.webChannelTransport, ch => {
        _bridge = ch.objects.pyBridge;
        _bridgeReady = true;
        _bridgeQueue.forEach(fn => fn(_bridge));
        _bridgeQueue.length = 0;
    });
}

// ── File icon emoji fallback ──────────────────────────────────────────────────
const EXT_EMOJI = {
    py: '🐍', js: '📜', ts: '📘', jsx: '⚛️', tsx: '⚛️', vue: '💚',
    html: '🌐', css: '🎨', json: '📋', yaml: '📋', yml: '📋', toml: '📋',
    md: '📝', txt: '📄', log: '📋', csv: '📊', xml: '📋',
    png: '🖼️', jpg: '🖼️', jpeg: '🖼️', gif: '🖼️', svg: '🎨', webp: '🖼️', ico: '🖼️',
    mp4: '🎬', avi: '🎬', mov: '🎬', mkv: '🎬', mp3: '🎵', wav: '🎵', flac: '🎵',
    zip: '📦', rar: '📦', '7z': '📦', tar: '📦', gz: '📦',
    pdf: '📕', docx: '📘', xlsx: '📗', pptx: '📙',
    exe: '⚙️', dll: '⚙️', sys: '⚙️', bat: '⚙️', ps1: '⚙️',
    rs: '🦀', go: '🐹', java: '☕', c: '🔧', cpp: '🔧', h: '🔧',
    sh: '🖥️', env: '🔐', gitignore: '🔧',
};

function fileEmoji(name, is_dir) {
    if (is_dir) return '📁';
    const ext = name.split('.').pop().toLowerCase();
    return EXT_EMOJI[ext] || '📄';
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function showToast(msg, isError = false) {
    const el = document.createElement('div');
    el.style.cssText = `position:fixed;bottom:46px;left:50%;transform:translateX(-50%);padding:8px 16px;border-radius:8px;font-size:13px;font-weight:600;z-index:9999;background:${isError ? 'var(--error,#ef4444)' : 'var(--accent)'};color:#fff;box-shadow:0 4px 16px rgba(0,0,0,.3);pointer-events:none;white-space:nowrap;`;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .3s'; setTimeout(() => el.remove(), 300); }, 2200);
}

// ── Exports ───────────────────────────────────────────────────────────────────
Object.assign(window, { getBridge, bridge, fileEmoji, showToast });
