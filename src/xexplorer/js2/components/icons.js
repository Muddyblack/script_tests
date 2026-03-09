// Per-file cache for .exe/.lnk/.url (each has unique icon), extension-based for the rest.
const _iconCache = {}; // cacheKey → data-url | '' | 'pending'
const _PER_FILE_EXTS = new Set(['lnk', 'url']);

function _iconCacheKey(name, path, is_dir) {
    if (is_dir) {
        // Only give unique cache keys to drive roots (C:\, etc)
        // All other folders share the generic folder icon.
        if (path && (path.length <= 3 && path.endsWith(':\\'))) return path.toUpperCase();
        return '__FOLDER__';
    }
    const ext = (name || '').split('.').pop().toLowerCase() || '__file__';
    return _PER_FILE_EXTS.has(ext) ? path : ext;
}

// Throttled icon fetch queue — max 3 concurrent requests to avoid freezing
const _iconQueue = [];
let _iconActive = 0;
const _ICON_MAX_CONCURRENT = 3;

// Debounced lucide icon refresh — batches all concurrent mount calls into one DOM scan
let _lucideTimer = null;
function _scheduleLucideRefresh() {
    if (typeof lucide === 'undefined') return;
    clearTimeout(_lucideTimer);
    _lucideTimer = setTimeout(() => lucide.createIcons(), 50);
}
const _iconListeners = {}; // cacheKey → Set of callbacks

function _iconFlush() {
    while (_iconActive < _ICON_MAX_CONCURRENT && _iconQueue.length) {
        const { cacheKey, path } = _iconQueue.shift();
        if (typeof _iconCache[cacheKey] === 'string' && _iconCache[cacheKey] !== 'pending') {
            const cbs = _iconListeners[cacheKey]; delete _iconListeners[cacheKey];
            if (cbs) cbs.forEach(fn => fn(_iconCache[cacheKey]));
            _iconFlush(); return;
        }
        _iconActive++;
        getBridge(async br => {
            let url = '';
            try {
                const b64 = await br.get_file_icon_b64(path);
                url = b64 ? `data:image/png;base64,${b64}` : '';
            } catch (err) {
                console.warn('[icon] error', cacheKey, err);
            }
            _iconCache[cacheKey] = url;
            const cbs = _iconListeners[cacheKey]; delete _iconListeners[cacheKey];
            if (cbs) cbs.forEach(fn => fn(url));
            _iconActive--;
            _iconFlush();
        });
    }
}

function _requestIcon(cacheKey, path, cb) {
    if (!_iconListeners[cacheKey]) _iconListeners[cacheKey] = new Set();
    _iconListeners[cacheKey].add(cb);
    if (_iconCache[cacheKey] !== 'pending') {
        _iconCache[cacheKey] = 'pending';
        _iconQueue.push({ cacheKey, path });
    }
    _iconFlush();
}

const LUCIDE_EXTS = {
    // Video
    mp4: 'film', avi: 'film', mov: 'film', mkv: 'film', webm: 'film', flv: 'film', m4v: 'film', wmv: 'film',
    // Audio 
    mp3: 'music', wav: 'music', flac: 'music', m4a: 'music', ogg: 'music',
    // Photos
    jpg: 'image', jpeg: 'image', png: 'image', gif: 'image', svg: 'palette', webp: 'image', ico: 'image',
    // Docs
    pdf: 'file-text', docx: 'file-text', doc: 'file-text', xlsx: 'file-spreadsheet', xls: 'file-spreadsheet', pptx: 'monitor-play',
    // Archives
    zip: 'package', rar: 'package', '7z': 'package', tar: 'package', gz: 'package',
    // Code
    js: 'code', ts: 'code', py: 'terminal', html: 'globe', css: 'palette', json: 'braces', yaml: 'list',
    exe: 'settings', bat: 'terminal', sh: 'terminal'
};

const FileIcon = memo(({ name, path, is_dir, size = 16, style: xs, className }) => {
    const cacheKey = _iconCacheKey(name, path, is_dir);
    const cached = _iconCache[cacheKey];
    const [src, setSrc] = useState(
        typeof cached === 'string' && cached !== 'pending' ? (cached || null) : null
    );
    useEffect(() => {
        if (!path) return;
        // Skip system icon fetch for mp4 (Windows shell returns generic icon)
        if (ext === 'mp4') return;
        const cur = _iconCache[cacheKey];
        if (typeof cur === 'string' && cur !== 'pending') { if (cur && src !== cur) setSrc(cur); return; }
        let alive = true;
        _requestIcon(cacheKey, path, url => { if (alive) setSrc(url || null); });
        return () => { alive = false; };
    }, [cacheKey, path]);

    const base = { width: size, height: size, objectFit: 'contain', display: 'inline-block', verticalAlign: 'middle', flexShrink: 0, ...xs };

    // 2. Lucide Fallback vars (computed unconditionally for hooks ordering)
    const ext = (name || '').split('.').pop().toLowerCase();
    const lucideName = is_dir ? 'folder' : (LUCIDE_EXTS[ext] || 'file');

    const colorMap = {
        film: '#60a5fa',
        music: '#c084fc',
        image: '#f472b6',
        'file-text': '#fbbf24',
        'file-spreadsheet': '#34d399',
        package: '#94a3b8',
        code: '#818cf8',
        terminal: '#a78bfa',
        settings: '#94a3b8',
        globe: '#60a5fa',
        palette: '#f472b6',
        folder: 'var(--accent)',
        file: 'var(--text-disabled)'
    };
    const iconColor = colorMap[lucideName] || 'var(--text-disabled)';

    useEffect(() => {
        _scheduleLucideRefresh();
    });

    // 1. System Icon (after all hooks)
    if (src) return <img src={src} style={base} className={className} />;

    if (typeof lucide === 'undefined') {
        return <em className={className} style={{ fontSize: size * 0.9, lineHeight: 1, color: iconColor, ...xs }}>{fileEmoji(name, is_dir)}</em>;
    }

    return (
        <span className={className} style={{ ...base, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
            <i data-lucide={lucideName} style={{ width: '100%', height: '100%', stroke: iconColor, strokeWidth: 2.2 }}></i>
        </span>
    );
});
