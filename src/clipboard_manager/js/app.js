// Clipboard Manager — React App
// Requires: bridge.js
/* global React, ReactDOM, window */

const { useState, useEffect, useCallback, useRef, memo } = React;
const { bridge, getBridge, showToast } = window;

// ── Tailwind config ────────────────────────────────────────────────────────
tailwind.config = {
    theme: {
        extend: {
            colors: {
                bg: 'var(--bg-base)', bg1: 'var(--bg-elevated)', bg2: 'var(--bg-overlay)',
                acc: 'var(--accent)', t1: 'var(--text-primary)', t2: 'var(--text-secondary)', t3: 'var(--text-disabled)',
            }
        }
    }
};

// ── Utilities ──────────────────────────────────────────────────────────────
function fmtTime(ts) {
    const diff = (Date.now() / 1000) - ts;
    if (diff < 60) return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return new Date(ts * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function fmtAbsTime(ts) {
    return new Date(ts * 1000).toLocaleString(undefined, {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
}

function guessTextType(content) {
    if (/^https?:\/\//i.test(content.trim())) return 'url';
    if (/\n/.test(content) || content.length > 120) return 'code';
    return 'text';
}

function textTypeIcon(t) {
    if (t === 'url') return '🔗';
    if (t === 'code') return '📄';
    return '📋';
}

// ── Image thumbnail cache (id → data-url | 'loading' | '') ────────────────
const _imgCache = {};
const IMAGE_TYPES = new Set(['image', 'image_path']);

function useImageSrc(clip) {
    const isImg = IMAGE_TYPES.has(clip.type);
    const [src, setSrc] = useState(() => {
        if (!isImg) return null;
        const c = _imgCache[clip.id];
        return (c && c !== 'loading') ? c : null;
    });

    useEffect(() => {
        if (!isImg) return;
        const cached = _imgCache[clip.id];
        if (cached && cached !== 'loading') { setSrc(cached); return; }
        if (cached === 'loading') return;
        _imgCache[clip.id] = 'loading';
        getBridge(async b => {
            const b64 = await b.get_image_data(clip.id);
            // Detect format from b64 header: PNG, JPEG, GIF, BMP, WEBP
            let mime = 'image/png';
            if (b64) {
                const sig = atob(b64.slice(0, 12));
                if (sig.charCodeAt(0) === 0xFF && sig.charCodeAt(1) === 0xD8) mime = 'image/jpeg';
                else if (sig.slice(0, 4) === 'GIF8') mime = 'image/gif';
                else if (sig.slice(0, 2) === 'BM') mime = 'image/bmp';
                else if (sig.slice(0, 4) === 'RIFF') mime = 'image/webp';
            }
            const url = b64 ? `data:${mime};base64,${b64}` : '';
            _imgCache[clip.id] = url;
            setSrc(url || null);
        });
    }, [clip.id, clip.type]);

    return src;
}

// ── Context Menu ──────────────────────────────────────────────────────────
const CtxMenu = memo(({ items, pos, onClose }) => {
    useEffect(() => {
        const h = e => { if (!e.target.closest('.ctx-menu')) onClose(); };
        const t = setTimeout(() => document.addEventListener('mousedown', h), 0);
        return () => { clearTimeout(t); document.removeEventListener('mousedown', h); };
    }, [onClose]);

    const top = Math.min(pos.y, window.innerHeight - items.length * 34 - 20);
    const left = Math.min(pos.x, window.innerWidth - 200);

    return (
        <div className="ctx-menu" style={{ top, left }}>
            {items.map((it, i) =>
                it === 'sep'
                    ? <div key={i} className="ctx-sep" />
                    : <div key={i} className={`ctx-item ${it.danger ? 'danger' : ''}`}
                        onClick={() => { it.action(); onClose(); }}>
                        <em className="ctx-icon">{it.icon}</em>
                        {it.label}
                    </div>
            )}
        </div>
    );
});

// ── Drag-resize handle ─────────────────────────────────────────────────────
function ResizeHandle({ cssVar, defaultW, min, max }) {
    const dragging = useRef(false);
    const startX = useRef(0);
    const startW = useRef(defaultW);

    function onMouseDown(e) {
        dragging.current = true;
        startX.current = e.clientX;
        startW.current = parseInt(getComputedStyle(document.documentElement).getPropertyValue(cssVar)) || defaultW;
        e.currentTarget.classList.add('dragging');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
    }

    useEffect(() => {
        function onMove(e) {
            if (!dragging.current) return;
            const w = Math.max(min, Math.min(max, startW.current + (e.clientX - startX.current)));
            document.documentElement.style.setProperty(cssVar, w + 'px');
        }
        function onUp() {
            if (!dragging.current) return;
            dragging.current = false;
            document.querySelectorAll('.resize-handle').forEach(el => el.classList.remove('dragging'));
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        }
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
        return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
    }, []);

    return <div className="resize-handle" onMouseDown={onMouseDown} />;
}

// ── Clip Item ──────────────────────────────────────────────────────────────
const ClipItem = memo(({ clip, selected, onSelect, onCopy, onTogglePin, onDelete, onCtx }) => {
    const imgSrc = useImageSrc(clip);
    const isImage = IMAGE_TYPES.has(clip.type);
    const textType = isImage ? 'image' : guessTextType(clip.content);
    const preview = clip.content.replace(/\s+/g, ' ').trim();
    const short = preview.length > 100 ? preview.slice(0, 100) + '…' : preview;

    return (
        <div
            className={`clip-item fade-in ${selected ? 'selected' : ''} ${clip.pinned ? 'pinned' : ''}`}
            onClick={() => onSelect(clip)}
            onDoubleClick={() => onCopy(clip)}
            onContextMenu={e => { e.preventDefault(); onCtx(e, clip); }}
        >
            {/* Left icon / thumbnail */}
            {isImage && imgSrc
                ? <img src={imgSrc} className="clip-thumb" alt="img" />
                : <span className="clip-type-icon">
                    {clip.pinned ? '📌' : isImage ? '🖼️' : textTypeIcon(textType)}
                </span>
            }

            {/* Body */}
            <div className="clip-body">
                <div className="clip-preview">
                    {isImage ? <em style={{ color: 'var(--text-disabled)', fontStyle: 'normal' }}>Image</em> : short}
                </div>
                <div className="clip-meta">
                    <span>{fmtTime(clip.ts)}</span>
                    {!isImage && <>
                        <span>·</span>
                        <span>{clip.content.length.toLocaleString()} chars</span>
                        {clip.content.includes('\n') && <>
                            <span>·</span>
                            <span>{(clip.content.match(/\n/g) || []).length + 1} lines</span>
                        </>}
                    </>}
                </div>
            </div>

            <div className="clip-pin-dot" />
            <div className="clip-actions" onClick={e => e.stopPropagation()}>
                <button className="btn-icon" title="Copy" onClick={() => onCopy(clip)}>⎘</button>
                <button className="btn-icon" title={clip.pinned ? 'Unpin' : 'Pin'} onClick={() => onTogglePin(clip)}>
                    {clip.pinned ? '📌' : '📍'}
                </button>
                <button className="btn-icon" style={{ color: 'var(--error,#ef4444)' }} title="Delete" onClick={() => onDelete(clip)}>✕</button>
            </div>
        </div>
    );
});

// ── Image Preview ──────────────────────────────────────────────────────────
const ImagePreview = memo(({ clip }) => {
    const src = useImageSrc(clip);
    if (!src) return (
        <div className="preview-empty">
            <div className="preview-empty-icon">🖼️</div>
            <div className="preview-empty-title">Loading image…</div>
        </div>
    );
    return (
        <div className="img-preview-wrap">
            <img src={src} className="img-preview" alt="clipboard image" />
        </div>
    );
});

// ── App ────────────────────────────────────────────────────────────────────
function App() {
    const [clips, setClips] = useState([]);
    const [total, setTotal] = useState(0);
    const [query, setQuery] = useState('');
    const [filter, setFilter] = useState('all'); // all | pinned
    const [selected, setSelected] = useState(null);
    const [status, setStatus] = useState('Loading…');
    const [ctx, setCtx] = useState(null);
    const searchRef = useRef(null);
    const pollRef = useRef(null);
    const bridgeRef = useRef(null);

    // ── Load ──────────────────────────────────────────────────────────────
    const refresh = useCallback(async (q = query, f = filter) => {
        if (!bridgeRef.current) return;
        const b = bridgeRef.current;
        try {
            const raw = await b.get_clips(q);
            let rows = JSON.parse(raw);
            if (f === 'pinned') rows = rows.filter(c => c.pinned);
            setClips(rows);
            const t = await b.get_total();
            const n = typeof t === 'number' ? t : parseInt(t) || rows.length;
            setTotal(n);
            setStatus(`${n} entries · watching clipboard`);
        } catch (e) {
            console.error('refresh error', e);
        }
    }, [query, filter]);

    useEffect(() => {
        bridge().then(b => {
            bridgeRef.current = b;
            refresh();
        });
    }, []);

    useEffect(() => {
        refresh();
        const i = setInterval(refresh, 800);
        return () => clearInterval(i);
    }, [refresh]);

    // ── Keyboard ─────────────────────────────────────────────────────────
    useEffect(() => {
        function onKey(e) {
            if (e.key === 'Escape') { setQuery(''); searchRef.current?.blur(); }
            if ((e.ctrlKey || e.metaKey) && e.key === 'f') { e.preventDefault(); searchRef.current?.focus(); }
            if (e.key === 'ArrowDown' && !e.target.matches('input')) {
                e.preventDefault();
                setSelected(sel => {
                    const idx = clips.findIndex(c => c.id === sel?.id);
                    return clips[Math.min(clips.length - 1, idx + 1)] || sel;
                });
            }
            if (e.key === 'ArrowUp' && !e.target.matches('input')) {
                e.preventDefault();
                setSelected(sel => {
                    const idx = clips.findIndex(c => c.id === sel?.id);
                    return clips[Math.max(0, idx - 1)] || sel;
                });
            }
            if (e.key === 'Enter' && selected && !e.target.matches('input')) copyClip(selected);
            if (e.key === 'Delete' && selected && !e.target.matches('input')) deleteClip(selected);
        }
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [clips, selected]);

    // ── Actions ───────────────────────────────────────────────────────────
    async function copyClip(clip) {
        const b = bridgeRef.current; if (!b) return;
        await b.copy_clip(clip.id);
        showToast('Copied to clipboard');
    }

    async function togglePin(clip) {
        const b = bridgeRef.current; if (!b) return;
        await b.toggle_pin(clip.id);
        setSelected(sel => sel?.id === clip.id ? { ...sel, pinned: sel.pinned ? 0 : 1 } : sel);
        refresh();
    }

    async function deleteClip(clip) {
        const b = bridgeRef.current; if (!b) return;
        await b.delete_clip(clip.id);
        if (selected?.id === clip.id) setSelected(null);
        refresh();
    }

    async function clearUnpinned() {
        const b = bridgeRef.current; if (!b) return;
        await b.clear_unpinned();
        setSelected(null);
        refresh();
        showToast('Cleared unpinned history');
    }

    // ── Context menu ──────────────────────────────────────────────────────
    function openCtx(e, clip) {
        setSelected(clip);
        setCtx({ pos: { x: e.clientX, y: e.clientY }, clip });
    }

    const ctxItems = ctx ? [
        { icon: '⎘', label: 'Copy', action: () => copyClip(ctx.clip) },
        {
            icon: ctx.clip.pinned ? '📌' : '📍',
            label: ctx.clip.pinned ? 'Unpin' : 'Pin', action: () => togglePin(ctx.clip)
        },
        'sep',
        { icon: '✕', label: 'Delete', danger: true, action: () => deleteClip(ctx.clip) },
    ] : [];

    // ── Preview header meta ───────────────────────────────────────────────
    const isSelImage = selected ? IMAGE_TYPES.has(selected.type) : false;
    const charCount = selected && !isSelImage ? selected.content.length : 0;
    const lineCount = selected && !isSelImage ? selected.content.split('\n').length : 0;

    return (
        <div className="shell">
            {/* ── Toolbar ── */}
            <div className="toolbar">
                <div className="brand">CLIP<span>BOARD</span></div>
                <div className="toolbar-sep" />
                <div className="search-wrap">
                    <span className="icon">🔍</span>
                    <input
                        ref={searchRef}
                        className="search-input"
                        placeholder="Search clipboard history…"
                        value={query}
                        onChange={e => setQuery(e.target.value)}
                    />
                    {query && <button className="search-clear" onClick={() => setQuery('')}>✕</button>}
                </div>
                <div className="entry-count">{total} entries</div>
            </div>

            {/* ── Body ── */}
            <div className="app-body">
                {/* List panel */}
                <div className="list-panel">
                    <div className="filter-row">
                        <button className={`chip ${filter === 'all' ? 'active' : ''}`} onClick={() => setFilter('all')}>All</button>
                        <button className={`chip ${filter === 'pinned' ? 'active' : ''}`} onClick={() => setFilter('pinned')}>📌 Pinned</button>
                    </div>

                    <div className="clip-list">
                        {clips.length === 0
                            ? <div className="empty-state">
                                <div className="empty-icon">{query ? '🔍' : '📋'}</div>
                                <div className="empty-title">{query ? 'No results' : 'No history yet'}</div>
                                <div className="empty-sub">{query ? `Nothing matched "${query}"` : 'Copy something to start tracking your clipboard.'}</div>
                            </div>
                            : clips.map(clip => (
                                <ClipItem
                                    key={clip.id}
                                    clip={clip}
                                    selected={selected?.id === clip.id}
                                    onSelect={setSelected}
                                    onCopy={copyClip}
                                    onTogglePin={togglePin}
                                    onDelete={deleteClip}
                                    onCtx={openCtx}
                                />
                            ))
                        }
                    </div>

                    <div className="list-actions">
                        <button className="btn btn-primary" disabled={!selected} onClick={() => selected && copyClip(selected)}>⎘ Copy</button>
                        <button className="btn btn-secondary" disabled={!selected} onClick={() => selected && togglePin(selected)}>
                            {selected?.pinned ? '📌 Unpin' : '📍 Pin'}
                        </button>
                        <div style={{ flex: 1 }} />
                        <button className="btn btn-danger" disabled={!selected} onClick={() => selected && deleteClip(selected)}>✕ Delete</button>
                        <button className="btn btn-danger" onClick={clearUnpinned}>🗑 Clear All</button>
                    </div>
                </div>

                <ResizeHandle cssVar="--list-w" defaultW={380} min={240} max={600} />

                {/* Preview panel */}
                <div className="preview-panel">
                    <div className="preview-header">
                        <span className="preview-title">Preview</span>
                        {selected && (
                            <span className="preview-meta-inline">
                                {isSelImage
                                    ? `Image · ${fmtAbsTime(selected.ts)}`
                                    : `${charCount.toLocaleString()} chars · ${lineCount} ${lineCount === 1 ? 'line' : 'lines'} · ${fmtAbsTime(selected.ts)}`
                                }
                            </span>
                        )}
                    </div>

                    <div className="preview-body">
                        {!selected
                            ? <div className="preview-empty">
                                <div className="preview-empty-icon">📋</div>
                                <div className="preview-empty-title">Nothing selected</div>
                                <div className="preview-empty-sub">Select an item from the list to preview its full content.</div>
                            </div>
                            : isSelImage
                                ? <ImagePreview clip={selected} />
                                : <pre className="preview-text">{selected.content}</pre>
                        }
                    </div>

                    {selected && (
                        <div className="preview-footer">
                            <button className="btn btn-primary" onClick={() => copyClip(selected)}>
                                {isSelImage ? '🖼️ Copy image' : '⎘ Copy to clipboard'}
                            </button>
                            <button className="btn btn-secondary" onClick={() => togglePin(selected)}>
                                {selected.pinned ? '📌 Unpin' : '📍 Pin'}
                            </button>
                        </div>
                    )}
                </div>
            </div>

            {/* ── Status bar ── */}
            <div className="statusbar">
                <div className="status-dot" />
                <span className="status-msg">{status}</span>
            </div>

            {ctx && <CtxMenu items={ctxItems} pos={ctx.pos} onClose={() => setCtx(null)} />}
        </div>
    );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
