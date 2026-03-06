// Per-file cache for .exe/.lnk/.url (each has unique icon), extension-based for the rest.
const _iconCache = {}; // cacheKey → data-url | '' | 'pending'
const _PER_FILE_EXTS = new Set(['exe', 'lnk', 'url']);

function _iconCacheKey(name, path, is_dir) {
    if (is_dir) return '__dir__';
    const ext = (name || '').split('.').pop().toLowerCase() || '__file__';
    return _PER_FILE_EXTS.has(ext) ? path : ext;
}

// Throttled icon fetch queue — max 3 concurrent requests to avoid freezing
const _iconQueue = [];
let _iconActive = 0;
const _ICON_MAX_CONCURRENT = 3;
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

const FileIcon = memo(({ name, path, is_dir, size = 16, style: xs, className }) => {
    const cacheKey = _iconCacheKey(name, path, is_dir);
    const cached = _iconCache[cacheKey];
    const [src, setSrc] = useState(
        typeof cached === 'string' && cached !== 'pending' ? (cached || null) : null
    );
    useEffect(() => {
        if (!path) return;
        const cur = _iconCache[cacheKey];
        if (typeof cur === 'string' && cur !== 'pending') { if (cur && src !== cur) setSrc(cur); return; }
        let alive = true;
        _requestIcon(cacheKey, path, url => { if (alive) setSrc(url || null); });
        return () => { alive = false; };
    }, [cacheKey, path]);
    const base = { width: size, height: size, objectFit: 'contain', display: 'inline-block', verticalAlign: 'middle', flexShrink: 0, ...xs };
    if (src) return <img src={src} style={base} className={className} />;
    return <em className={className} style={{ fontSize: size * 0.9, lineHeight: 1, ...xs }}>{fileEmoji(name, is_dir)}</em>;
});
