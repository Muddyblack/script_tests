// Clipboard Manager — QWebChannel bridge + dev mock

let _bridge = null;
let _bridgeReady = false;
const _bridgeQueue = [];

function getBridge(cb) {
    if (_bridgeReady) { cb(_bridge); return; }
    _bridgeQueue.push(cb);
}

function bridge() {
    return new Promise(resolve => getBridge(resolve));
}

// ── Mock data for browser dev ──────────────────────────────────────────────
const MOCK_CLIPS = [
    { id: 6, content: '', pinned: 1, ts: Date.now()/1000 - 10,  type: 'image' },
    { id: 5, content: 'https://github.com/anthropics/claude-code', pinned: 1, ts: Date.now()/1000 - 30,   type: 'text' },
    { id: 4, content: 'npm install @anthropic-ai/sdk', pinned: 0, ts: Date.now()/1000 - 120,  type: 'text' },
    { id: 3, content: `const { useState, useEffect } = React;\n\nfunction App() {\n  const [count, setCount] = useState(0);\n  return <button onClick={() => setCount(c => c+1)}>{count}</button>;\n}`, pinned: 0, ts: Date.now()/1000 - 600, type: 'text' },
    { id: 2, content: 'SELECT id, content, pinned, ts FROM clips ORDER BY pinned DESC, ts DESC LIMIT 300', pinned: 0, ts: Date.now()/1000 - 3600, type: 'text' },
    { id: 1, content: 'Hello, world!', pinned: 0, ts: Date.now()/1000 - 7200, type: 'text' },
];

if (typeof QWebChannel !== 'undefined') {
    new QWebChannel(qt.webChannelTransport, ch => {
        _bridge = ch.objects.pyBridge;
        _bridgeReady = true;
        _bridgeQueue.forEach(fn => fn(_bridge));
        _bridgeQueue.length = 0;
    });
} else {
    // Dev-mode mock
    let _clips = [...MOCK_CLIPS];
    let _nextId = 6;

    // Tiny 1x1 red PNG for mock image preview
    const MOCK_IMG_B64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg==';

    setTimeout(() => {
        _bridge = {
            get_clips: (query) => {
                const q = (query || '').toLowerCase();
                let rows = q
                    ? _clips.filter(c => c.type === 'image' || c.content.toLowerCase().includes(q))
                    : [..._clips];
                rows.sort((a, b) => b.pinned - a.pinned || b.ts - a.ts);
                return JSON.stringify(rows.slice(0, 300));
            },
            get_total: () => _clips.length,
            get_image_data: (id) => {
                const c = _clips.find(c => c.id === id && c.type === 'image');
                return c ? MOCK_IMG_B64 : '';
            },
            copy_clip: (id) => {
                const c = _clips.find(c => c.id === id);
                if (c) console.log('[mock] copy:', c.type === 'image' ? '[image]' : c.content.slice(0, 60));
                return true;
            },
            toggle_pin: (id) => {
                const c = _clips.find(c => c.id === id);
                if (c) c.pinned = c.pinned ? 0 : 1;
                return true;
            },
            delete_clip: (id) => {
                _clips = _clips.filter(c => c.id !== id);
                return true;
            },
            clear_unpinned: () => {
                _clips = _clips.filter(c => c.pinned);
                return true;
            },
            // Signals (mocked)
            clip_added: { connect: () => {} },
        };
        _bridgeReady = true;
        _bridgeQueue.forEach(fn => fn(_bridge));
        _bridgeQueue.length = 0;
    }, 80);
}

// ── Toast ──────────────────────────────────────────────────────────────────
function showToast(msg, isError = false) {
    const el = document.createElement('div');
    el.style.cssText = `position:fixed;bottom:36px;left:50%;transform:translateX(-50%);padding:7px 16px;border-radius:8px;font-size:12px;font-weight:700;z-index:9999;background:${isError ? 'var(--error,#ef4444)' : 'var(--accent)'};color:#fff;box-shadow:0 4px 16px rgba(0,0,0,.35);pointer-events:none;white-space:nowrap;letter-spacing:.03em;`;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .3s'; setTimeout(() => el.remove(), 300); }, 2000);
}

Object.assign(window, { getBridge, bridge, showToast });
