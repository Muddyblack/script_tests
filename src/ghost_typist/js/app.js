// Ghost Typist — single-file React app
// Communicates with Python via QWebChannel (pyBridge)

const { useState, useEffect, useRef, useMemo } = React;
const { motion, AnimatePresence } = window.Motion;

// ── Bridge (QWebChannel) ─────────────────────────────────────────────────────
let _bridge = null;
let _bridgeReady = false;
const _bridgeCbs = [];

function getBridge(cb) {
    if (_bridgeReady) { cb(_bridge); return; }
    _bridgeCbs.push(cb);
}

new QWebChannel(qt.webChannelTransport, ch => {
    _bridge = ch.objects.pyBridge;
    _bridgeReady = true;
    _bridgeCbs.forEach(fn => fn(_bridge));
    _bridgeCbs.length = 0;
});

// ── Helpers ──────────────────────────────────────────────────────────────────
const CATEGORY_COLORS = {
    Personal: '#a78bfa',
    Email: '#60a5fa',
    Dev: '#34d399',
    Utilities: '#fbbf24',
    Work: '#f87171',
    Other: '#94a3b8',
};

function categoryColor(cat) {
    return CATEGORY_COLORS[cat] || '#94a3b8';
}

function isMagicExpansion(exp) {
    return exp.includes('__DATE__') || exp.includes('__TIME__') || exp.includes('__CLIP__');
}

function previewExpansion(exp) {
    const now = new Date();
    return exp
        .replace(/__DATE__/g, now.toISOString().slice(0, 10))
        .replace(/__TIME__/g, now.toTimeString().slice(0, 5))
        .replace(/__CLIP__/g, '‹clipboard›');
}

// ── Toggle ───────────────────────────────────────────────────────────────────
const Toggle = ({ on, onChange, label }) => (
    <label className="toggle-wrap" onClick={() => onChange(!on)}>
        <div className={`toggle-track ${on ? 'on' : ''}`}>
            <div className="toggle-thumb" />
        </div>
        {label && <span style={{ fontSize: 13, color: 'var(--text-secondary)', userSelect: 'none' }}>{label}</span>}
    </label>
);

// ── Edit / Add Modal ─────────────────────────────────────────────────────────
const CATEGORIES = ['Personal', 'Email', 'Dev', 'Utilities', 'Work', 'Other'];
const MAGIC_TOKENS = [
    { token: '__DATE__', desc: "Today's date  (YYYY-MM-DD)" },
    { token: '__TIME__', desc: 'Current time  (HH:MM)' },
    { token: '__CLIP__', desc: 'Clipboard text' },
];

const SnippetModal = ({ snippet, onSave, onClose }) => {
    const isEdit = !!snippet;
    const [trigger, setTrigger] = useState(snippet?.trigger ?? ';;');
    const [expansion, setExpansion] = useState(snippet?.expansion ?? '');
    const [label, setLabel] = useState(snippet?.label ?? '');
    const [category, setCategory] = useState(snippet?.category ?? 'Personal');
    const [error, setError] = useState('');
    const trigRef = useRef(null);

    useEffect(() => { trigRef.current?.focus(); }, []);

    function handleSave() {
        if (!trigger.trim()) { setError('Trigger cannot be empty.'); return; }
        if (!expansion.trim()) { setError('Expansion cannot be empty.'); return; }
        if (!trigger.startsWith(';;')) { setError('Trigger should start with ";;".'); return; }
        onSave({ trigger: trigger.trim(), expansion, label: label.trim(), category });
    }

    function insertToken(tok) {
        setExpansion(prev => prev + tok);
    }

    return (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
            <motion.div
                className="card p-6 w-full"
                style={{ maxWidth: 520, boxShadow: 'var(--shadow-lg)' }}
                initial={{ y: 16, opacity: 0, scale: 0.97 }}
                animate={{ y: 0, opacity: 1, scale: 1 }}
                transition={{ duration: 0.18 }}>

                {/* Header */}
                <div className="flex items-center justify-between mb-5">
                    <h2 style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>
                        {isEdit ? 'Edit Snippet' : 'New Snippet'}
                    </h2>
                    <button className="btn-icon" onClick={onClose}>✕</button>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                    {/* Trigger */}
                    <div>
                        <label className="section-label" style={{ display: 'block', marginBottom: 5 }}>Trigger</label>
                        <input
                            ref={trigRef}
                            className="input-field mono"
                            value={trigger}
                            onChange={e => { setTrigger(e.target.value); setError(''); }}
                            placeholder=";;shortcut"
                            spellCheck={false}
                            onKeyDown={e => { if (e.key === 'Enter') handleSave(); }}
                        />
                        <p style={{ fontSize: 11, color: 'var(--text-disabled)', marginTop: 4 }}>
                            Type this anywhere → it gets replaced. Prefix with <span className="kbd">;;</span>
                        </p>
                    </div>

                    {/* Expansion */}
                    <div>
                        <label className="section-label" style={{ display: 'block', marginBottom: 5 }}>Expansion</label>
                        <textarea
                            className="input-field mono"
                            value={expansion}
                            onChange={e => { setExpansion(e.target.value); setError(''); }}
                            placeholder="The text to type…"
                            rows={4}
                        />
                        {/* Magic token buttons */}
                        <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
                            {MAGIC_TOKENS.map(m => (
                                <button key={m.token}
                                    className="btn btn-ghost"
                                    style={{ fontSize: 10, padding: '3px 9px', textTransform: 'none' }}
                                    title={m.desc}
                                    onClick={() => insertToken(m.token)}>
                                    + {m.token}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Label + Category row */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                        <div>
                            <label className="section-label" style={{ display: 'block', marginBottom: 5 }}>Label (optional)</label>
                            <input className="input-field" value={label} onChange={e => setLabel(e.target.value)} placeholder="My Email" />
                        </div>
                        <div>
                            <label className="section-label" style={{ display: 'block', marginBottom: 5 }}>Category</label>
                            <select className="input-field" style={{ cursor: 'pointer' }} value={category} onChange={e => setCategory(e.target.value)}>
                                {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                            </select>
                        </div>
                    </div>

                    {/* Preview */}
                    {expansion.trim() && (
                        <div className="card-inset" style={{ padding: '10px 13px' }}>
                            <p className="section-label" style={{ marginBottom: 4 }}>Preview</p>
                            <p style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                                {previewExpansion(expansion)}
                            </p>
                        </div>
                    )}

                    {error && (
                        <p style={{ fontSize: 12, color: 'var(--error, #ef4444)', padding: '6px 10px', background: 'color-mix(in srgb, var(--error,#ef4444) 10%, transparent)', borderRadius: 8 }}>
                            {error}
                        </p>
                    )}

                    {/* Actions */}
                    <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
                        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
                        <button className="btn btn-primary" onClick={handleSave}>{isEdit ? 'Save' : 'Add Snippet'}</button>
                    </div>
                </div>
            </motion.div>
        </div>
    );
};

// ── Delete Confirm ────────────────────────────────────────────────────────────
const DeleteConfirm = ({ snippet, onConfirm, onClose }) => (
    <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
        <motion.div
            className="card p-6 w-full"
            style={{ maxWidth: 360, boxShadow: 'var(--shadow-lg)' }}
            initial={{ y: 12, opacity: 0, scale: 0.97 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            transition={{ duration: 0.16 }}>
            <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 8, color: 'var(--text-primary)' }}>Delete Snippet?</h2>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 18 }}>
                Remove <span className="kbd">{snippet.trigger}</span> — this cannot be undone.
            </p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
                <button className="btn btn-danger" onClick={onConfirm}>Delete</button>
            </div>
        </motion.div>
    </div>
);

// ── Snippet Row ───────────────────────────────────────────────────────────────
const SnippetRow = ({ snippet, onEdit, onDelete }) => {
    const col = categoryColor(snippet.category);
    return (
        <div className="snippet-item float-in">
            {/* Left accent bar */}
            <div style={{ width: 3, borderRadius: 3, background: col, alignSelf: 'stretch', flexShrink: 0 }} />

            {/* Content */}
            <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
                    <span className="kbd" style={{ fontSize: 12 }}>{snippet.trigger}</span>
                    {snippet.label && (
                        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>{snippet.label}</span>
                    )}
                    <span className="category-badge" style={{ color: col, background: `color-mix(in srgb, ${col} 12%, transparent)`, borderColor: `color-mix(in srgb, ${col} 25%, transparent)` }}>
                        {snippet.category}
                    </span>
                    {snippet.use_count > 0 && (
                        <span style={{ fontSize: 10, color: 'var(--text-disabled)', marginLeft: 'auto' }}>
                            used {snippet.use_count}×
                        </span>
                    )}
                </div>
                <p className="snippet-expansion">
                    {isMagicExpansion(snippet.expansion)
                        ? <span style={{ color: 'var(--accent)', fontStyle: 'italic', fontFamily: 'monospace', fontSize: 11 }}>{snippet.expansion}</span>
                        : previewExpansion(snippet.expansion)
                    }
                </p>
            </div>

            {/* Actions */}
            <div style={{ display: 'flex', gap: 4, flexShrink: 0, alignSelf: 'flex-start' }}>
                <button className="btn-icon" title="Edit" onClick={() => onEdit(snippet)}>
                    ✏️
                </button>
                <button className="btn-icon" title="Delete" onClick={() => onDelete(snippet)} style={{ color: 'var(--error, #ef4444)' }}>
                    🗑️
                </button>
            </div>
        </div>
    );
};

// ── Main App ──────────────────────────────────────────────────────────────────
const App = () => {
    const [snippets, setSnippets] = useState([]);
    const [search, setSearch] = useState('');
    const [activeCategory, setActiveCategory] = useState('All');
    const [watcherOn, setWatcherOn] = useState(true);
    const [editTarget, setEditTarget] = useState(null);   // null | false | {snippet}
    const [deleteTarget, setDeleteTarget] = useState(null);
    const [ready, setReady] = useState(false);

    // ── Bridge init ──────────────────────────────────────────────────────────
    useEffect(() => {
        let pollId = null;
        getBridge(async (bridge) => {
            await loadSnippets(bridge);
            try {
                const st = await bridge.get_watcher_status();
                setWatcherOn(!!st);
            } catch (e) { /* ignore */ }
            // Live updates from Python
            if (bridge.snippets_changed?.connect) {
                bridge.snippets_changed.connect(() => loadSnippets(bridge));
            }
            setReady(true);

            // Poll watcher status every 2 s so tray / external changes
            pollId = setInterval(async () => {
                try {
                    const st = await bridge.get_watcher_status();
                    setWatcherOn(prev => (!!st === prev ? prev : !!st));
                } catch (e) { /* ignore */ }
            }, 2000);
        });
        return () => { if (pollId !== null) clearInterval(pollId); };
    }, []);

    async function loadSnippets(bridge) {
        try {
            const raw = await bridge.load_snippets();
            if (raw) setSnippets(JSON.parse(raw));
        } catch (e) { console.error('load_snippets', e); }
    }

    // ── Derived data ─────────────────────────────────────────────────────────
    const categories = useMemo(() => {
        const cats = [...new Set(snippets.map(s => s.category))].sort();
        return ['All', ...cats];
    }, [snippets]);

    const filtered = useMemo(() => {
        let list = snippets;
        if (activeCategory !== 'All') list = list.filter(s => s.category === activeCategory);
        if (search.trim()) {
            const q = search.toLowerCase();
            list = list.filter(s =>
                s.trigger.toLowerCase().includes(q) ||
                s.expansion.toLowerCase().includes(q) ||
                s.label.toLowerCase().includes(q)
            );
        }
        return list;
    }, [snippets, activeCategory, search]);

    const stats = useMemo(() => ({
        total: snippets.length,
        totalFires: snippets.reduce((n, s) => n + (s.use_count || 0), 0),
    }), [snippets]);

    // ── Handlers ─────────────────────────────────────────────────────────────
    function handleToggleWatcher(val) {
        setWatcherOn(val);
        getBridge(b => b.set_watcher_enabled(val));
    }

    function handleSave({ trigger, expansion, label, category }) {
        getBridge(b => {
            b.upsert_snippet(trigger, expansion, label, category);
            loadSnippets(b);
        });
        setEditTarget(null);
    }

    function handleDelete() {
        if (!deleteTarget) return;
        getBridge(b => {
            b.delete_snippet(deleteTarget.trigger);
            loadSnippets(b);
        });
        setDeleteTarget(null);
    }

    // ── Render ────────────────────────────────────────────────────────────────
    return (
        <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

            {/* ── Top bar ──────────────────────────────────────────────────── */}
            <header style={{
                padding: '14px 20px',
                borderBottom: '1px solid var(--border)',
                display: 'flex',
                alignItems: 'center',
                gap: 14,
                background: 'var(--bg-base)',
                flexShrink: 0,
            }}>
                {/* Brand */}
                <div style={{ marginRight: 4 }}>
                    <div style={{ fontSize: 15, fontWeight: 800, letterSpacing: '-0.02em', color: 'var(--text-primary)', lineHeight: 1 }}>
                        GHOST<span style={{ color: 'var(--accent)' }}>_</span>TYPIST
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-disabled)', marginTop: 2 }}>Text Expander</div>
                </div>

                {/* Status */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div className={`status-dot ${watcherOn ? 'active' : 'paused'}`} />
                    <span style={{ fontSize: 11, color: 'var(--text-disabled)' }}>
                        {watcherOn ? 'Watching' : 'Paused'}
                    </span>
                </div>

                <div style={{ flex: 1 }} />

                {/* Stats */}
                <div style={{ display: 'flex', gap: 18, marginRight: 8 }}>
                    <div style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1 }}>{stats.total}</div>
                        <div style={{ fontSize: 10, color: 'var(--text-disabled)' }}>snippets</div>
                    </div>
                    <div style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--accent)', lineHeight: 1 }}>{stats.totalFires}</div>
                        <div style={{ fontSize: 10, color: 'var(--text-disabled)' }}>expansions</div>
                    </div>
                </div>

                {/* Toggle */}
                <Toggle on={watcherOn} onChange={handleToggleWatcher} label="" />

                {/* Add button */}
                <button className="btn btn-primary" onClick={() => setEditTarget(false)} style={{ gap: 5 }}>
                    <span style={{ fontSize: 16, lineHeight: 1 }}>+</span> New
                </button>
            </header>

            {/* ── Body ─────────────────────────────────────────────────────── */}
            <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

                {/* Sidebar */}
                <aside style={{
                    width: 160,
                    borderRight: '1px solid var(--border)',
                    padding: '14px 10px',
                    overflowY: 'auto',
                    background: 'var(--bg-base)',
                    flexShrink: 0,
                }}>
                    <p className="section-label" style={{ paddingLeft: 6, marginBottom: 8 }}>Categories</p>
                    {categories.map(cat => {
                        const active = cat === activeCategory;
                        const col = cat === 'All' ? 'var(--text-secondary)' : categoryColor(cat);
                        const count = cat === 'All' ? snippets.length : snippets.filter(s => s.category === cat).length;
                        return (
                            <button key={cat}
                                onClick={() => setActiveCategory(cat)}
                                style={{
                                    width: '100%',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'space-between',
                                    padding: '7px 9px',
                                    borderRadius: 9,
                                    border: 'none',
                                    cursor: 'pointer',
                                    background: active ? `color-mix(in srgb, ${col} 14%, transparent)` : 'transparent',
                                    color: active ? col : 'var(--text-secondary)',
                                    fontWeight: active ? 700 : 500,
                                    fontSize: 12,
                                    transition: 'all 0.15s',
                                    marginBottom: 2,
                                }}>
                                <span>{cat}</span>
                                <span style={{ fontSize: 10, opacity: 0.7 }}>{count}</span>
                            </button>
                        );
                    })}
                </aside>

                {/* Main panel */}
                <main style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

                    {/* Search */}
                    <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
                        <div className="search-bar">
                            <span className="search-icon" style={{ fontSize: 14 }}>🔍</span>
                            <input
                                className="input-field"
                                style={{ paddingLeft: 34, fontSize: 13 }}
                                placeholder="Search snippets…"
                                value={search}
                                onChange={e => setSearch(e.target.value)}
                            />
                        </div>
                    </div>

                    {/* List */}
                    <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                        {!ready ? (
                            <div className="empty-state" style={{ flex: 1 }}>
                                <div style={{ fontSize: 28 }}>⌨️</div>
                                <p style={{ fontSize: 13 }}>Loading…</p>
                            </div>
                        ) : filtered.length === 0 ? (
                            <div className="empty-state" style={{ flex: 1 }}>
                                <div style={{ fontSize: 32 }}>🔤</div>
                                <p style={{ fontSize: 13 }}>
                                    {search || activeCategory !== 'All' ? 'No snippets match.' : 'No snippets yet.'}
                                </p>
                                {!search && activeCategory === 'All' && (
                                    <button className="btn btn-primary" style={{ marginTop: 6 }} onClick={() => setEditTarget(false)}>
                                        + Add your first snippet
                                    </button>
                                )}
                            </div>
                        ) : (
                            filtered.map(s => (
                                <SnippetRow key={s.trigger} snippet={s}
                                    onEdit={sn => setEditTarget(sn)}
                                    onDelete={sn => setDeleteTarget(sn)} />
                            ))
                        )}
                    </div>

                    {/* Footer hint */}
                    <div style={{
                        padding: '8px 16px',
                        borderTop: '1px solid var(--border)',
                        display: 'flex',
                        gap: 14,
                        alignItems: 'center',
                        flexShrink: 0,
                        background: 'var(--bg-base)',
                    }}>
                        <span style={{ fontSize: 11, color: 'var(--text-disabled)' }}>
                            Type a trigger in <em>any</em> app → expands automatically.
                        </span>
                        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-disabled)' }}>
                            Magic: <span className="kbd">__DATE__</span> <span className="kbd">__TIME__</span> <span className="kbd">__CLIP__</span>
                        </span>
                    </div>
                </main>
            </div>

            {/* ── Modals ───────────────────────────────────────────────────── */}
            <AnimatePresence>
                {editTarget !== null && (
                    <SnippetModal
                        snippet={editTarget || null}
                        onSave={handleSave}
                        onClose={() => setEditTarget(null)}
                    />
                )}
                {deleteTarget && (
                    <DeleteConfirm
                        snippet={deleteTarget}
                        onConfirm={handleDelete}
                        onClose={() => setDeleteTarget(null)}
                    />
                )}
            </AnimatePresence>
        </div>
    );
};

// Bootstrap
ReactDOM.createRoot(document.getElementById('root')).render(<App />);
