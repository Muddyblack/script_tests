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

new QWebChannel(qt.webChannelTransport, ch => {
    _bridge = ch.objects.pyBridge;
    _bridgeReady = true;
    _bridgeQueue.forEach(fn => fn(_bridge));
    _bridgeQueue.length = 0;
});

// ── Toast ──────────────────────────────────────────────────────────────────
function showToast(msg, isError = false) {
    const el = document.createElement('div');
    el.style.cssText = `position:fixed;bottom:36px;left:50%;transform:translateX(-50%);padding:7px 16px;border-radius:8px;font-size:12px;font-weight:700;z-index:9999;background:${isError ? 'var(--error,#ef4444)' : 'var(--accent)'};color:#fff;box-shadow:0 4px 16px rgba(0,0,0,.35);pointer-events:none;white-space:nowrap;letter-spacing:.03em;`;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .3s'; setTimeout(() => el.remove(), 300); }, 2000);
}

Object.assign(window, { getBridge, bridge, showToast });
