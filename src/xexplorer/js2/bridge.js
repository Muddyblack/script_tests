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
} else {
    // Dev-mode mock
    setTimeout(() => {
        const MOCK_FILES = [
            { path: 'C:\\Users\\dev\\projects\\app\\src\\main.py',  name: 'main.py',      is_dir: false, size: '4 KB',  mtime: '2026-02-28 10:14', ext: 'py'  },
            { path: 'C:\\Users\\dev\\projects\\app\\README.md',      name: 'README.md',    is_dir: false, size: '2 KB',  mtime: '2026-02-25 09:00', ext: 'md'  },
            { path: 'C:\\Users\\dev\\projects\\app\\src',            name: 'src',          is_dir: true,  size: '',      mtime: '2026-02-28 10:00', ext: ''    },
            { path: 'C:\\Users\\dev\\projects\\app\\package.json',   name: 'package.json', is_dir: false, size: '1 KB',  mtime: '2026-02-20 15:30', ext: 'json'},
            { path: 'C:\\Users\\dev\\projects\\app\\dist\\bundle.js',name: 'bundle.js',    is_dir: false, size: '128 KB',mtime: '2026-02-28 11:00', ext: 'js'  },
        ];
        _bridge = {
            get_config:         ()   => JSON.stringify({ folders: [{ path: 'C:\\Users\\dev', label: 'Developer' }], ignore: [{ rule: 'node_modules', enabled: true }] }),
            save_config:        ()   => {},
            search:             (q)  => JSON.stringify(MOCK_FILES.filter(f => f.name.toLowerCase().includes(q.toLowerCase()))),
            start_indexing:     ()   => {},
            stop_indexing:      ()   => {},
            get_stats:          ()   => JSON.stringify({ count: 128453, last_indexed: '2026-02-28 11:00', db_mb: 14.2 }),
            clear_index:        ()   => {},
            open_path:          ()   => {},
            show_in_explorer:   ()   => {},
            copy_to_clipboard:  ()   => {},
            pick_folder:        ()   => 'C:\\Users\\dev\\new-folder',
            get_drives:         ()   => JSON.stringify(['C:\\', 'D:\\']),
            add_ignore_rule:    ()   => {},
            prompt_ignore_rule: ()   => 'node_modules',
            get_file_icon_b64:  ()   => '',
            get_preview:        ()   => JSON.stringify({ type: 'text', content: '# Hello World\n\nThis is a preview.', ext: 'md' }),
            is_watchdog_available: () => true,
            // Signals (mocked)
            indexing_progress: { connect: () => {} },
            indexing_done:     { connect: () => {} },
            stats_updated:     { connect: () => {} },
            live_changed:      { connect: () => {} },
            tab_incoming:      { connect: () => {} },
            close_window:      () => {},
            drop_tab:          () => {},
            get_initial_path:  () => '',
            get_favorites:     () => '[]',
        };
        _bridgeReady = true;
        _bridgeQueue.forEach(fn => fn(_bridge));
        _bridgeQueue.length = 0;
    }, 100);
}

// ── File icon emoji fallback ──────────────────────────────────────────────────
const EXT_EMOJI = {
    py:'🐍', js:'📜', ts:'📘', jsx:'⚛️', tsx:'⚛️', vue:'💚',
    html:'🌐', css:'🎨', json:'📋', yaml:'📋', yml:'📋', toml:'📋',
    md:'📝', txt:'📄', log:'📋', csv:'📊', xml:'📋',
    png:'🖼️', jpg:'🖼️', jpeg:'🖼️', gif:'🖼️', svg:'🎨', webp:'🖼️', ico:'🖼️',
    mp4:'🎬', avi:'🎬', mov:'🎬', mkv:'🎬', mp3:'🎵', wav:'🎵', flac:'🎵',
    zip:'📦', rar:'📦', '7z':'📦', tar:'📦', gz:'📦',
    pdf:'📕', docx:'📘', xlsx:'📗', pptx:'📙',
    exe:'⚙️', dll:'⚙️', sys:'⚙️', bat:'⚙️', ps1:'⚙️',
    rs:'🦀', go:'🐹', java:'☕', c:'🔧', cpp:'🔧', h:'🔧',
    sh:'🖥️', env:'🔐', gitignore:'🔧',
};

function fileEmoji(name, is_dir) {
    if (is_dir) return '📁';
    const ext = name.split('.').pop().toLowerCase();
    return EXT_EMOJI[ext] || '📄';
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function showToast(msg, isError = false) {
    const el = document.createElement('div');
    el.style.cssText = `position:fixed;bottom:46px;left:50%;transform:translateX(-50%);padding:8px 16px;border-radius:8px;font-size:13px;font-weight:600;z-index:9999;background:${isError?'var(--error,#ef4444)':'var(--accent)'};color:#fff;box-shadow:0 4px 16px rgba(0,0,0,.3);pointer-events:none;white-space:nowrap;`;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => { el.style.opacity='0'; el.style.transition='opacity .3s'; setTimeout(() => el.remove(), 300); }, 2200);
}

// ── Exports ───────────────────────────────────────────────────────────────────
Object.assign(window, { getBridge, bridge, fileEmoji, showToast });
