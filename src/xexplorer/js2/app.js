// XExplorer — Main React App
// Requires: bridge.js
/* global React, ReactDOM, window */

const { useState, useEffect, useCallback, useRef, useMemo, memo } = React;
const { motion, AnimatePresence } = window.Motion;
const { bridge, getBridge, fileEmoji, showToast } = window;

// ── Tailwind config ───────────────────────────────────────────────────────────
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

// ── Context Menu ─────────────────────────────────────────────────────────────
const CtxMenu = memo(({ items, pos, onClose }) => {
    useEffect(() => {
        const h = e => { if (!e.target.closest('.ctx-menu')) onClose(); };
        const t = setTimeout(() => document.addEventListener('mousedown', h), 0);
        return () => { clearTimeout(t); document.removeEventListener('mousedown', h); };
    }, [onClose]);

    const top = Math.min(pos.y, window.innerHeight - items.length * 34 - 20);
    const left = Math.min(pos.x, window.innerWidth - 220);

    return (
        <div className="ctx-menu" style={{ top, left }}>
            {items.map((it, i) =>
                it === 'sep'
                    ? <div key={i} className="ctx-sep" />
                    : <div key={i} className={`ctx-item ${it.danger ? 'danger' : ''}`}
                        onClick={() => { it.action(); onClose(); }}>
                        <em className="ctx-icon">{it.icon}</em>
                        {it.label}
                        {it.kbd && <span className="kbd">{it.kbd}</span>}
                    </div>
            )}
        </div>
    );
});

// ── Toggle ────────────────────────────────────────────────────────────────────
const Tog = ({ on, onChange }) => (
    <div className={`tog ${on ? 'on' : ''}`} onClick={() => onChange(!on)}>
        <div className="tog-thumb" />
    </div>
);

// ── Command Palette ───────────────────────────────────────────────────────────
const CmdPalette = ({ results, onClose, onSelect }) => {
    const [q, setQ] = useState('');
    const [active, setActive] = useState(0);
    const ref = useRef(null);
    useEffect(() => { ref.current?.focus(); }, []);

    const filtered = useMemo(() =>
        (!q.trim() ? results : results.filter(r =>
            r.name.toLowerCase().includes(q.toLowerCase()) ||
            r.path.toLowerCase().includes(q.toLowerCase())
        )).slice(0, 12)
        , [q, results]);

    useEffect(() => setActive(0), [filtered]);

    function onKey(e) {
        if (e.key === 'Escape') { onClose(); return; }
        if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.min(a + 1, filtered.length - 1)); return; }
        if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(a - 1, 0)); return; }
        if (e.key === 'Enter' && filtered[active]) { onSelect(filtered[active]); onClose(); }
    }

    return (
        <div className="palette-wrap" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
            <div className="palette">
                <input ref={ref} className="palette-input" placeholder="Go to file…" value={q} onChange={e => setQ(e.target.value)} onKeyDown={onKey} />
                <div style={{ maxHeight: 360, overflowY: 'auto' }}>
                    {filtered.length === 0
                        ? <div style={{ padding: '18px 14px', color: 'var(--text-disabled)', fontSize: 13 }}>No results</div>
                        : filtered.map((r, i) => (
                            <div key={r.path} className={`palette-result ${i === active ? 'active' : ''}`}
                                onClick={() => { onSelect(r); onClose(); }}>
                                <FileIcon name={r.name} path={r.path} is_dir={r.is_dir} size={16} className="p-icon" />
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ fontSize: 13, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</div>
                                    <div className="p-path">{r.path}</div>
                                </div>
                            </div>
                        ))
                    }
                </div>
            </div>
        </div>
    );
};

// ── File Icon (native OS icon, emoji fallback) ──────────────────────────────
const _iconExtCache = {}; // ext → data-url | '' | 'pending'

const FileIcon = memo(({ name, path, is_dir, size = 16, style: xs, className }) => {
    const ext = is_dir ? '__dir__' : ((name || '').split('.').pop().toLowerCase() || '__file__');
    const cached = _iconExtCache[ext];
    const [src, setSrc] = useState(
        typeof cached === 'string' && cached !== 'pending' ? (cached || null) : null
    );
    useEffect(() => {
        if (!path) return;
        const cur = _iconExtCache[ext];
        if (typeof cur === 'string' && cur !== 'pending') { if (cur && src !== cur) setSrc(cur); return; }
        if (cur === 'pending') {
            const t = setInterval(() => {
                const v = _iconExtCache[ext];
                if (typeof v === 'string' && v !== 'pending') { setSrc(v || null); clearInterval(t); }
            }, 60);
            return () => clearInterval(t);
        }
        _iconExtCache[ext] = 'pending';
        getBridge(async br => {
            const b64 = await br.get_file_icon_b64(path);
            const url = b64 ? `data:image/png;base64,${b64}` : '';
            _iconExtCache[ext] = url;
            setSrc(url || null);
        });
    }, [ext, path]);
    const base = { width: size, height: size, objectFit: 'contain', display: 'inline-block', verticalAlign: 'middle', flexShrink: 0, ...xs };
    if (src) return <img src={src} style={base} className={className} />;
    return <em className={className} style={{ fontSize: size * 0.9, lineHeight: 1, ...xs }}>{fileEmoji(name, is_dir)}</em>;
});

// ── Drag-resize handle ────────────────────────────────────────────────────────
const Resizer = ({ onDrag }) => {
    const latest = useRef(onDrag);
    useEffect(() => { latest.current = onDrag; }, [onDrag]);

    const handleMouseDown = useCallback(e => {
        e.preventDefault();
        let lastX = e.clientX;
        const handle = e.currentTarget;
        handle.classList.add('dragging');
        const onMove = ev => { const dx = ev.clientX - lastX; lastX = ev.clientX; latest.current(dx); };
        const onUp = () => { handle.classList.remove('dragging'); document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    }, []);

    return <div className="resize-handle" onMouseDown={handleMouseDown} />;
};

// ── Tab helpers ───────────────────────────────────────────────────────────────
let _tabIdSeed = 1;
const INIT_TAB = (id, browsePath = null) => ({
    id,
    title: browsePath
        ? (browsePath.split(/[/\\]/).filter(Boolean).pop() || browsePath)
        : 'New Tab',
    browsePath,
    browseStack: [],
    query: '',
    results: [],
    loading: false,
    selected: new Set(),
    selectionAnchor: null,
    previewFile: null,
});

const TabBar = ({ tabs, activeTabId, onSelect, onClose, onNew, onTearOff, onReorder }) => {
    const barRef = useRef(null);
    const [drag, setDrag] = useState(null);
    // drag = { tabId, startX, startY, curX, curY, isTearOff, insertIdx }

    function startDrag(e, tabId) {
        if (e.button !== 0) return;
        e.preventDefault();
        onSelect(tabId);
        const state = {
            tabId, startX: e.clientX, startY: e.clientY,
            curX: e.clientX, curY: e.clientY,
            isTearOff: false, insertIdx: null, moved: false
        };
        setDrag(state);

        const onMove = ev => {
            setDrag(prev => {
                if (!prev) return null;
                const bar = barRef.current?.getBoundingClientRect();
                const dy = bar ? ev.clientY - bar.bottom : 0;
                const dx = Math.abs(ev.clientX - prev.startX);
                const moved = dx > 4 || Math.abs(ev.clientY - prev.startY) > 4;
                const outOfViewport = (
                    ev.clientX < -20 ||
                    ev.clientY < -20 ||
                    ev.clientX > window.innerWidth + 20 ||
                    ev.clientY > window.innerHeight + 20
                );
                const isTearOff = dy > 52 || (bar && ev.clientY < bar.top - 36) || outOfViewport;

                let insertIdx = null;
                if (!isTearOff && barRef.current) {
                    const tabEls = [...barRef.current.querySelectorAll('.tab')];
                    insertIdx = tabEls.length;
                    for (let i = 0; i < tabEls.length; i++) {
                        const r = tabEls[i].getBoundingClientRect();
                        if (ev.clientX < r.left + r.width / 2) { insertIdx = i; break; }
                    }
                }
                return { ...prev, curX: ev.clientX, curY: ev.clientY, isTearOff, insertIdx, moved };
            });
        };

        const onUp = ev => {
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
            setDrag(prev => {
                if (!prev) return null;
                const bar = barRef.current?.getBoundingClientRect();
                const dy = bar ? ev.clientY - bar.bottom : 0;
                const outOfViewport = (
                    ev.clientX < -20 ||
                    ev.clientY < -20 ||
                    ev.clientX > window.innerWidth + 20 ||
                    ev.clientY > window.innerHeight + 20
                );
                const isTearOff = dy > 52 || (bar && ev.clientY < bar.top - 36) || outOfViewport;
                if (prev.moved && isTearOff) {
                    onTearOff(prev.tabId);
                } else if (prev.moved && prev.insertIdx !== null) {
                    onReorder(prev.tabId, prev.insertIdx);
                }
                return null;
            });
        };

        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    }

    const draggingTab = drag ? tabs.find(t => t.id === drag.tabId) : null;

    // compute reorder-preview order
    let displayTabs = tabs;
    if (drag && !drag.isTearOff && drag.insertIdx !== null && drag.moved) {
        const idx = tabs.findIndex(t => t.id === drag.tabId);
        if (idx !== -1) {
            const reordered = [...tabs];
            const [moved] = reordered.splice(idx, 1);
            const target = drag.insertIdx > idx ? drag.insertIdx - 1 : drag.insertIdx;
            reordered.splice(Math.max(0, target), 0, moved);
            displayTabs = reordered;
        }
    }

    return (
        <>
            <div className="tabs-bar" ref={barRef}>
                {displayTabs.map(tab => (
                    <div key={tab.id}
                        className={[
                            'tab',
                            tab.id === activeTabId ? 'active' : '',
                            drag?.tabId === tab.id && drag.isTearOff ? 'tab-tearing' : '',
                            drag?.tabId === tab.id && drag.moved && !drag.isTearOff ? 'tab-dragging' : '',
                        ].join(' ')}
                        onMouseDown={e => startDrag(e, tab.id)}
                        onAuxClick={e => { if (e.button === 1) { e.preventDefault(); onClose(tab.id); } }}>
                        <span className="tab-icon">{tab.browsePath ? '📂' : '🔍'}</span>
                        <span className="tab-label">{tab.title}</span>
                        {tabs.length > 1 && (
                            <button className="tab-close"
                                onMouseDown={e => e.stopPropagation()}
                                onClick={e => { e.stopPropagation(); onClose(tab.id); }}>✕</button>
                        )}
                    </div>
                ))}
                <button className="tab-new" title="New tab (Ctrl+T)" onClick={onNew}>＋</button>
            </div>
            {/* Floating ghost when tearing off */}
            {drag?.isTearOff && draggingTab && (
                <div className="tab-ghost" style={{ left: drag.curX - 70, top: drag.curY - 18 }}>
                    <span className="tab-icon">{draggingTab.browsePath ? '📂' : '🔍'}</span>
                    <span className="tab-label">{draggingTab.title}</span>
                    <span style={{ fontSize: 10, opacity: .6, marginLeft: 6, flexShrink: 0 }}>drop on window to merge · release to detach</span>
                </div>
            )}
        </>
    );
};

// ── Sidebar context-menu hook ─────────────────────────────────────────────────
function useSidebarCtx() {
    const [menu, setMenu] = useState(null);
    useEffect(() => {
        if (!menu) return;
        const h = e => { if (!e.target.closest('.ctx-menu')) setMenu(null); };
        const t = setTimeout(() => document.addEventListener('mousedown', h), 0);
        return () => { clearTimeout(t); document.removeEventListener('mousedown', h); };
    }, [menu]);
    const open = (e, items) => {
        e.preventDefault(); e.stopPropagation();
        setMenu({ pos: { x: e.clientX, y: e.clientY }, items });
    };
    const close = () => setMenu(null);
    return { menu, open, close };
}

// ── Drive Card (sidebar) ───────────────────────────────────────────────────────
const DRIVE_PALETTE = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#3b82f6', '#8b5cf6', '#ec4899', '#06b6d4'];

const DriveCard = memo(({ folder, isSelected, onToggle, onIndex, onRemove, onBrowse, onBrowseDirect, onScopeOnly }) => {
    const [info, setInfo] = useState(null);
    const isDrive = /^[A-Za-z]:\\$/.test(folder.path);
    const letter = folder.path.match(/^([A-Za-z]):/)?.[1]?.toUpperCase() || '?';
    const label = folder.label || folder.path.split(/[/\\]/).filter(Boolean).pop() || folder.path;
    const accent = isDrive ? DRIVE_PALETTE[(letter.charCodeAt(0) - 65) % DRIVE_PALETTE.length] : 'var(--accent)';

    useEffect(() => {
        getBridge(async b => {
            const raw = await b.get_drive_info(folder.path);
            setInfo(JSON.parse(raw));
        });
    }, [folder.path]);

    const volName = info?.label || (isDrive ? `Drive ${letter}:` : label);
    const pct = info?.total_gb ? Math.round((1 - info.free_gb / info.total_gb) * 100) : 0;
    const used = info?.total_gb ? (info.total_gb - info.free_gb).toFixed(1) : null;

    return (
        <div className={`drive-card ${isSelected ? 'selected' : ''}`}
            style={{ '--dc-accent': accent }}
            onClick={() => onBrowseDirect ? onBrowseDirect(folder.path) : onToggle(folder.path)}
            onContextMenu={e => {
                e.preventDefault(); e.stopPropagation();
                onBrowse && onBrowse(folder.path, e);
            }}>
            <div className="dc-badge">{isDrive ? letter : '📁'}</div>
            <div className="dc-body">
                <div className="dc-name">{volName}</div>
                {isDrive && info ? (
                    <>
                        <div className="dc-track"><div className="dc-fill" style={{ width: `${pct}%` }} /></div>
                        <div className="dc-stats">{used} GB used of {info.total_gb} GB</div>
                    </>
                ) : (
                    <div className="dc-stats">{folder.path}</div>
                )}
            </div>
            <div className="dc-actions">
                <button className="btn-icon"
                    title={isSelected ? 'In search scope' : 'Not in search scope'}
                    style={{ fontSize: 12, padding: '2px 4px', color: isSelected ? 'var(--accent)' : 'var(--text-disabled)' }}
                    onClick={e => { e.stopPropagation(); onToggle(folder.path); }}>
                    {isSelected ? '◉' : '○'}
                </button>
                <button className="btn-icon" title="Index" style={{ fontSize: 12, padding: '2px 4px' }}
                    onClick={e => { e.stopPropagation(); onIndex(folder.path); }}>⚡</button>
                <button className="btn-icon" title="Remove" style={{ fontSize: 12, padding: '2px 4px', color: 'var(--error,#ef4444)' }}
                    onClick={e => { e.stopPropagation(); onRemove(folder.path); }}>✕</button>
            </div>
        </div>
    );
});

// ── Breadcrumb ─────────────────────────────────────────────────────────────────
const Breadcrumb = ({ path, onBack, onHome, onNavigate }) => {
    if (!path) return null;
    const parts = path.replace(/\//g, '\\').split('\\').filter(Boolean);

    function buildSegmentPath(idx) {
        let p = parts.slice(0, idx + 1).join('\\');
        if (/^[A-Za-z]:$/.test(p)) p += '\\';
        return p;
    }

    return (
        <div className="breadcrumb">
            <button className="bc-btn" title="Exit to search" onClick={onHome}>🔍 Search</button>
            <button className="bc-btn" title="Up one level" onClick={onBack}>↑ Up</button>
            <button className="bc-btn" title="Copy current path" onClick={() => getBridge(br => { br.copy_to_clipboard(path); showToast('Path copied'); })}>📋 Copy</button>
            {parts.map((part, i) => (
                <React.Fragment key={i}>
                    <span className="bc-sep">›</span>
                    {i === parts.length - 1
                        ? <span className="bc-part active">{part}</span>
                        : <span className="bc-part bc-nav"
                            title={buildSegmentPath(i)}
                            onClick={() => onNavigate && onNavigate(buildSegmentPath(i))}>{part}</span>
                    }
                </React.Fragment>
            ))}
        </div>
    );
};

// ── Sidebar ───────────────────────────────────────────────────────────────────
const Sidebar = ({ folders, ignore, selectedFolders, onFolderToggle, onAddFolder,
    onRemoveFolder, onIndexFolder, onToggleIgnore, onRemoveIgnore, onAddIgnore,
    onScanDrives, onBrowseFolder, onScopeOnly,
    favorites, onFavClick, onFavRemove, onFavShowInExplorer, onFavNewTab }) => {
    const [bottomTab, setBottomTab] = useState('favs'); // 'favs' | 'ignore'
    const [ignoreQ, setIgnoreQ] = useState('');
    const filteredIgnore = !ignoreQ.trim() ? ignore
        : ignore.filter(r => r.rule.toLowerCase().includes(ignoreQ.toLowerCase()));
    const driveCtx = useSidebarCtx();
    const ignoreCtx = useSidebarCtx();
    const favCtx = useSidebarCtx();

    return (
        <aside className="sidebar">
            {/* Indexed folders */}
            <div className="sidebar-section">Indexed Folders</div>
            <div style={{ flex: '0 0 auto', maxHeight: 220, overflowY: 'auto', padding: '0 6px 4px' }}>
                {folders.length === 0
                    ? <div style={{ padding: '10px 6px', fontSize: 11.5, color: 'var(--text-disabled)' }}>No folders yet</div>
                    : folders.map(f => (
                        <DriveCard key={f.path} folder={f}
                            isSelected={selectedFolders.includes(f.path)}
                            onToggle={onFolderToggle}
                            onIndex={onIndexFolder}
                            onRemove={onRemoveFolder}
                            onBrowseDirect={onBrowseFolder}
                            onScopeOnly={onScopeOnly}
                            onBrowse={(path, e) => {
                                const inScope = selectedFolders.includes(path);
                                driveCtx.open(e, [
                                    { icon: '📂', label: 'Browse folder', action: () => { onBrowseFolder(path); driveCtx.close(); } },
                                    { icon: '🎯', label: 'Search only here', action: () => { onScopeOnly && onScopeOnly(path); driveCtx.close(); } },
                                    {
                                        icon: inScope ? '○' : '◉', label: inScope ? 'Exclude from search' : 'Include in search',
                                        action: () => { onFolderToggle(path); driveCtx.close(); }
                                    },
                                    { icon: '⚡', label: 'Index this folder', action: () => { onIndexFolder(path); driveCtx.close(); } },
                                    'sep',
                                    { icon: '✕', label: 'Remove from list', danger: true, action: () => { onRemoveFolder(path); driveCtx.close(); } },
                                ]);
                            }} />
                    ))
                }
            </div>
            <div style={{ display: 'flex', gap: 4, padding: '2px 8px 8px' }}>
                <button className="sidebar-btn accent" onClick={onAddFolder}>+ Folder</button>
                <button className="sidebar-btn secondary" onClick={onScanDrives}>⟳ Drives</button>
            </div>

            <div className="sidebar-divider" />

            {/* ── Bottom tabs: Favorites / Ignore ── */}
            <div className="sb-tab-bar">
                <button className={`sb-tab ${bottomTab === 'favs' ? 'active' : ''}`}
                    onClick={() => setBottomTab('favs')}>
                    ⭐ Favs {favorites.length > 0 && <span className="sb-tab-badge">{favorites.length}</span>}
                </button>
                <button className={`sb-tab ${bottomTab === 'ignore' ? 'active' : ''}`}
                    onClick={() => setBottomTab('ignore')}>
                    🚫 Ignore {ignore.length > 0 && <span className="sb-tab-badge">{ignore.length}</span>}
                </button>
            </div>

            {bottomTab === 'favs' && (
                <div style={{ flex: 1, overflowY: 'auto', padding: '2px 6px 4px' }}>
                    {favorites.length === 0
                        ? <div style={{ padding: '14px 8px', fontSize: 11.5, color: 'var(--text-disabled)', textAlign: 'center' }}>Right-click a file and choose<br />⭐ Add to Favorites</div>
                        : favorites.map(fav => {
                            const isDir = fav.is_dir !== false;
                            const openCtx = e => {
                                e.preventDefault(); e.stopPropagation();
                                const items = [
                                    isDir
                                        ? { icon: '📂', label: 'Browse folder', action: () => { onFavClick(fav); favCtx.close(); } }
                                        : { icon: '📄', label: 'Open file', action: () => { onFavClick(fav); favCtx.close(); } },
                                    isDir && { icon: '🎯', label: 'Search only here', action: () => { onScopeOnly && onScopeOnly(fav.path); favCtx.close(); } },
                                    isDir && { icon: '➕', label: 'Open in new tab', action: () => { onFavNewTab && onFavNewTab(fav.path); favCtx.close(); } },
                                    { icon: '📁', label: 'Show in Explorer', action: () => { onFavShowInExplorer && onFavShowInExplorer(fav.path); favCtx.close(); } },
                                    'sep',
                                    { icon: '✕', label: 'Remove from favorites', danger: true, action: () => { onFavRemove(fav.path); favCtx.close(); } },
                                ].filter(Boolean);
                                favCtx.open(e, items);
                            };
                            return (
                                <div key={fav.path} className="fav-item"
                                    onClick={() => onFavClick(fav)}
                                    onContextMenu={openCtx}
                                    title={fav.path}>
                                    <FileIcon name={fav.label} path={fav.path} is_dir={isDir} size={14} className="fav-icon" />
                                    <span className="fav-label">{fav.label}</span>
                                    <button className="fav-remove"
                                        onMouseDown={e => e.stopPropagation()}
                                        onClick={e => { e.stopPropagation(); onFavRemove(fav.path); }}>✕</button>
                                </div>
                            );
                        })
                    }
                </div>
            )}

            {bottomTab === 'ignore' && (
                <>
                    <div style={{ padding: '4px 8px 4px' }}>
                        <div className="ignore-filter-wrap">
                            <span style={{ fontSize: 13, color: 'var(--text-disabled)' }}>⌖</span>
                            <input className="ignore-filter" placeholder="Filter rules…"
                                value={ignoreQ} onChange={e => setIgnoreQ(e.target.value)} />
                            {ignoreQ && <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-disabled)', fontSize: 13 }} onClick={() => setIgnoreQ('')}>×</button>}
                        </div>
                    </div>
                    <div style={{ flex: 1, overflowY: 'auto', padding: '0 6px 4px' }}>
                        {filteredIgnore.map(r => (
                            <div key={r.rule} className="ignore-item"
                                onContextMenu={e => ignoreCtx.open(e, [
                                    { icon: r.enabled ? '🔕' : '✔️', label: r.enabled ? 'Disable rule' : 'Enable rule', action: () => { onToggleIgnore(r.rule); ignoreCtx.close(); } },
                                    'sep',
                                    { icon: '🗑️', label: 'Delete rule', danger: true, action: () => { onRemoveIgnore(r.rule); ignoreCtx.close(); } },
                                ])}>
                                <Tog on={r.enabled} onChange={() => onToggleIgnore(r.rule)} />
                                <span className="rule-text" title={r.rule}>{r.rule}</span>
                                <button className="remove-btn" onClick={() => onRemoveIgnore(r.rule)}>×</button>
                            </div>
                        ))}
                    </div>
                    <div style={{ padding: '2px 8px 8px' }}>
                        <button className="sidebar-btn" style={{ width: '100%' }} onClick={onAddIgnore}>+ Add Rule</button>
                    </div>
                </>
            )}

            {/* Sidebar context menus */}
            {driveCtx.menu && <CtxMenu items={driveCtx.menu.items} pos={driveCtx.menu.pos} onClose={driveCtx.close} />}
            {ignoreCtx.menu && <CtxMenu items={ignoreCtx.menu.items} pos={ignoreCtx.menu.pos} onClose={ignoreCtx.close} />}
            {favCtx.menu && <CtxMenu items={favCtx.menu.items} pos={favCtx.menu.pos} onClose={favCtx.close} />}
        </aside>
    );
};

// ── Preview Pane ──────────────────────────────────────────────────────────────
const PreviewPane = ({ file, onClose }) => {
    const [preview, setPreview] = useState(null);
    const [page, setPage] = useState(0);

    function fetchPage(path, pageNum) {
        setPreview(null);
        getBridge(async b => {
            const raw = pageNum === 0
                ? await b.get_preview(path)
                : await b.get_preview_page(path, pageNum);
            setPreview(JSON.parse(raw));
        });
    }

    useEffect(() => {
        if (!file) return;
        setPage(0);
        fetchPage(file.path, 0);
    }, [file?.path]);

    function goPage(delta) {
        if (!preview?.page_count) return;
        const next = Math.max(0, Math.min(preview.page_count - 1, page + delta));
        if (next === page) return;
        setPage(next);
        fetchPage(file.path, next);
    }

    if (!file) return null;
    const canPage = preview?.page_count > 1;

    return (
        <aside className="preview-pane">
            <div className="preview-header">
                <FileIcon name={file.name} path={file.path} is_dir={file.is_dir} size={18} />
                <span className="preview-filename">{file.name}</span>
                <button className="btn-icon" onClick={onClose}>✕</button>
            </div>
            <div className="preview-body" style={{ flex: 1, overflow: 'auto', padding: preview?.type === 'sheet' ? 0 : 14 }}>
                {!preview && (
                    <div style={{ color: 'var(--text-disabled)', fontSize: 12, padding: 14 }}>Loading preview…</div>
                )}
                {preview?.type === 'pdf' && (
                    <div style={{ textAlign: 'center' }}>
                        <img src={preview.content} alt={`Page ${page + 1}`}
                            style={{ maxWidth: '100%', borderRadius: 6, boxShadow: '0 4px 20px rgba(0,0,0,.3)' }} />
                    </div>
                )}
                {preview?.type === 'slide_image' && (
                    <div style={{ textAlign: 'center' }}>
                        <img src={preview.content} alt={`Slide ${page + 1}`}
                            style={{ maxWidth: '100%', borderRadius: 6, boxShadow: '0 4px 20px rgba(0,0,0,.3)' }} />
                    </div>
                )}
                {preview?.type === 'slide' && (
                    <div className="slide-content"
                        dangerouslySetInnerHTML={{ __html: preview.content }} />
                )}
                {preview?.type === 'docx' && (
                    <div className="slide-content"
                        dangerouslySetInnerHTML={{ __html: preview.content }} />
                )}
                {preview?.type === 'sheet' && (
                    <div style={{ overflow: 'auto', height: '100%', padding: 8 }}
                        dangerouslySetInnerHTML={{ __html: preview.content }} />
                )}
                {preview?.type === 'image' && (
                    <div style={{ textAlign: 'center' }}>
                        <img src={preview.content} alt={file.name} style={{ maxWidth: '100%' }} />
                    </div>
                )}
                {preview?.type === 'text' && (
                    <>
                        <div className="preview-meta">{file.path}</div>
                        <pre className="preview-code">{preview.content}</pre>
                    </>
                )}
                {preview?.type === 'error' && (
                    <div style={{ color: 'var(--error,#ef4444)', fontSize: 12 }}>Error: {preview.content}</div>
                )}
                {preview?.type === 'unsupported' && (
                    <div className="empty-state" style={{ height: 'auto', paddingTop: 40 }}>
                        <span className="empty-icon">👁️</span>
                        <span style={{ fontSize: 12, color: 'var(--text-disabled)' }}>{preview.content || 'No preview available'}</span>
                    </div>
                )}
            </div>
            {canPage && (
                <div className="preview-pages">
                    <button className="page-btn" onClick={() => goPage(-1)} disabled={page === 0}>‹</button>
                    <span className="page-label">{preview.label || `${page + 1} / ${preview.page_count}`}</span>
                    <button className="page-btn" onClick={() => goPage(1)} disabled={page >= preview.page_count - 1}>›</button>
                </div>
            )}
        </aside>
    );
};

// ── Details View ──────────────────────────────────────────────────────────────
const SORT_KEYS = { Name: 'name', Type: 'ext', Size: 'size', Modified: 'mtime' };

const DetailsView = ({ files, selected, onSelect, onDouble, onCtxMenu, sortKey, sortDir, onSort }) => {
    const cols = [
        { label: 'Name', key: 'name', width: '42%' },
        { label: 'Type', key: 'ext', width: '10%' },
        { label: 'Size', key: 'size', width: '10%' },
        { label: 'Modified', key: 'mtime', width: '38%' },
    ];
    return (
        <div style={{ flex: 1, overflowY: 'auto' }}>
            <table className="details-table">
                <thead>
                    <tr className="details-head">
                        {cols.map(col => (
                            <th key={col.key} style={{ width: col.width }}
                                className={sortKey === col.key ? 'sorted' : ''}
                                onClick={() => onSort(col.key)}>
                                {col.label} {sortKey === col.key ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {files.map(f => {
                        const isSel = selected.has(f.path);
                        return (
                            <tr key={f.path} className={`file-row ${isSel ? 'selected' : ''}`}
                                onClick={e => (f.is_dir && !e.ctrlKey && !e.shiftKey && !selected.has(f.path)) ? onDouble(f) : onSelect(f, e)}
                                onDoubleClick={e => !f.is_dir && onDouble(f)}
                                onContextMenu={e => { e.preventDefault(); onCtxMenu(e, f); }}>
                                <td>
                                    <FileIcon name={f.name} path={f.path} is_dir={f.is_dir} size={15} className="file-icon" />
                                    <span className="file-name">{f.name}</span>
                                    {f.ext && !f.is_dir && <span className="ext-badge">.{f.ext}</span>}
                                </td>
                                <td style={{ color: 'var(--text-disabled)', fontSize: 11 }}>
                                    {f.is_dir ? 'Folder' : (f.ext ? f.ext.toUpperCase() : 'File')}
                                </td>
                                <td style={{ color: 'var(--text-disabled)', fontVariantNumeric: 'tabular-nums' }}>{f.size}</td>
                                <td style={{ color: 'var(--text-disabled)', fontVariantNumeric: 'tabular-nums' }}>{f.mtime}</td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
};

// ── Icons View ────────────────────────────────────────────────────────────────
const IconsView = ({ files, selected, onSelect, onDouble, onCtxMenu }) => (
    <div style={{ flex: 1, overflowY: 'auto' }}>
        <div className="icons-grid">
            {files.slice(0, 800).map(f => {
                const isSel = selected.has(f.path);
                const short = f.name.length > 15 ? f.name.slice(0, 14) + '…' : f.name;
                return (
                    <div key={f.path} className={`icon-item ${isSel ? 'selected' : ''}`}
                        onClick={e => (f.is_dir && !e.ctrlKey && !e.shiftKey && !selected.has(f.path)) ? onDouble(f) : onSelect(f, e)}
                        onDoubleClick={e => !f.is_dir && onDouble(f)}
                        onContextMenu={e => { e.preventDefault(); onCtxMenu(e, f); }}
                        title={f.path}>
                        <FileIcon name={f.name} path={f.path} is_dir={f.is_dir} size={38} className="big-icon" />
                        <span className="icon-name">{short}</span>
                    </div>
                );
            })}
        </div>
    </div>
);

// ── Tree View ─────────────────────────────────────────────────────────────────
function buildTree(files) {
    const nodes = {};
    const roots = [];
    for (const f of files.slice(0, 1500)) {
        const parts = f.path.replace(/\//g, '\\').split('\\').filter(Boolean);
        let path_acc = '';
        for (let i = 0; i < parts.length; i++) {
            path_acc = i === 0 ? parts[0] : path_acc + '\\' + parts[i];
            if (!nodes[path_acc]) {
                const isLast = i === parts.length - 1;
                nodes[path_acc] = {
                    path: path_acc, name: parts[i],
                    is_dir: isLast ? f.is_dir : true,
                    ext: isLast ? f.ext : '',
                    children: [],
                };
                if (i === 0) roots.push(nodes[path_acc]);
                else {
                    const parentPath = parts.slice(0, i).join('\\');
                    if (nodes[parentPath]) nodes[parentPath].children.push(nodes[path_acc]);
                }
            }
        }
    }
    return roots;
}

const TreeNode = ({ node, depth, selected, onSelect, onDouble, onCtxMenu, expanded, onToggle }) => {
    const hasKids = node.children.length > 0;
    const isExp = expanded.has(node.path);
    const isSel = selected.has(node.path);
    return (
        <div className="tree-node">
            <div className={`tree-row ${isSel ? 'selected' : ''}`}
                style={{ paddingLeft: 8 + depth * 16 }}
                onClick={e => { onSelect(node, e); if (hasKids) onToggle(node.path); }}
                onDoubleClick={() => onDouble(node)}
                onContextMenu={e => { e.preventDefault(); onCtxMenu(e, node); }}>
                <span className="tree-expander">
                    {hasKids ? (isExp ? '▾' : '▸') : ''}
                </span>
                <FileIcon name={node.name} path={node.path} is_dir={node.is_dir} size={14} style={{ marginRight: 5 }} />
                <span className="tree-label">{node.name}</span>
            </div>
            {isExp && hasKids && node.children.map(child => (
                <TreeNode key={child.path} node={child} depth={depth + 1}
                    selected={selected} onSelect={onSelect} onDouble={onDouble}
                    onCtxMenu={onCtxMenu} expanded={expanded} onToggle={onToggle} />
            ))}
        </div>
    );
};

const TreeView = ({ files, selected, onSelect, onDouble, onCtxMenu }) => {
    const [expanded, setExpanded] = useState(new Set());
    const roots = useMemo(() => buildTree(files), [files]);
    const toggle = path => setExpanded(prev => {
        const next = new Set(prev);
        if (next.has(path)) next.delete(path); else next.add(path);
        return next;
    });
    return (
        <div style={{ flex: 1, overflowY: 'auto', padding: '4px 4px' }} className="tree-root">
            {roots.map(n => <TreeNode key={n.path} node={n} depth={0}
                selected={selected} onSelect={onSelect} onDouble={onDouble}
                onCtxMenu={onCtxMenu} expanded={expanded} onToggle={toggle} />)}
        </div>
    );
};

// ── Main App ──────────────────────────────────────────────────────────────────
const App = () => {
    // Config
    const [folders, setFolders] = useState([]);
    const [ignore, setIgnore] = useState([]);

    // UI state (global, persists across tabs)
    const [viewMode, setViewMode] = useState('details'); // details | icons | tree
    const [filter, setFilter] = useState('all');     // all | files | folders | recent
    const [sortKey, setSortKey] = useState('name');
    const [sortDir, setSortDir] = useState('asc');

    // Sidebar folder filter
    const [selectedFolders, setSelectedFolders] = useState([]);

    // Panel widths (resizable)
    const [sidebarWidth, setSidebarWidth] = useState(220);
    const [previewWidth, setPreviewWidth] = useState(350);

    // Context menu
    const [ctxMenu, setCtxMenu] = useState(null); // {pos, files}

    // Stats / status
    const [stats, setStats] = useState({ count: 0, last_indexed: 'Never', db_mb: 0 });
    const [statusMsg, setStatusMsg] = useState('Ready');
    const [indexing, setIndexing] = useState(false);
    const [indexProgress, setIndexProgress] = useState('');
    const [liveOn, setLiveOn] = useState(false);
    const liveTickRef = useRef(null); // debounce timer for watcher refreshes
    const [liveRefreshTick, setLiveRefreshTick] = useState(0);

    // Command palette
    const [palette, setPalette] = useState(false);

    // ── Tabs ──────────────────────────────────────────────────────────────────
    const tabIdRef = useRef(2);
    const [tabs, setTabs] = useState([INIT_TAB(1)]);
    const [activeTabId, setActiveTabId] = useState(1);

    const activeTab = useMemo(
        () => tabs.find(t => t.id === activeTabId) ?? tabs[0],
        [tabs, activeTabId]
    );

    function patchTab(id, patch) {
        setTabs(prev => prev.map(t => t.id === id ? { ...t, ...patch } : t));
    }
    function patchActive(patch) {
        setTabs(prev => prev.map(t => t.id === activeTabId ? { ...t, ...patch } : t));
    }

    function addTab(initialPath = null) {
        const id = tabIdRef.current++;
        setTabs(prev => [...prev, INIT_TAB(id, initialPath)]);
        setActiveTabId(id);
    }

    function closeTab(id) {
        setTabs(prev => {
            if (prev.length === 1) return prev;
            const idx = prev.findIndex(t => t.id === id);
            const next = prev.filter(t => t.id !== id);
            if (activeTabId === id) {
                const newActive = next[Math.min(idx, next.length - 1)];
                setActiveTabId(newActive.id);
            }
            return next;
        });
    }

    // ── Favorites ─────────────────────────────────────────────────────────────
    const [favorites, setFavorites] = useState([]);

    function handleAddFavorite(file) {
        if (favorites.some(f => f.path === file.path)) { showToast('Already in favorites'); return; }
        const label = file.name || file.path.split(/[/\\]/).filter(Boolean).pop() || file.path;
        const newFavs = [...favorites, { path: file.path, label, is_dir: !!file.is_dir }];
        setFavorites(newFavs);
        getBridge(br => br.save_favorites(JSON.stringify(newFavs)));
        showToast(`⭐ Added: ${label}`);
    }

    function handleRemoveFavorite(path) {
        const newFavs = favorites.filter(f => f.path !== path);
        setFavorites(newFavs);
        getBridge(br => br.save_favorites(JSON.stringify(newFavs)));
    }

    function handleFavShowInExplorer(path) {
        getBridge(br => br.show_in_explorer(path));
    }

    function handleFavNewTab(path) {
        addTab(path);
    }

    function handleFavClick(fav) {
        if (fav.is_dir === false) {
            // it's a file — open it
            getBridge(br => br.open_path(fav.path));
        } else {
            // it's a folder — navigate the active tab
            setTabs(prev => prev.map(t => t.id === activeTabId
                ? {
                    ...t, browsePath: fav.path, browseStack: [], query: '',
                    title: fav.label, results: [], loading: false
                }
                : t));
        }
    }

    function handleTearOff(tabId) {
        const tab = tabs.find(t => t.id === tabId);
        if (!tab) return;
        const isLastTab = tabs.length <= 1;
        // drop_tab checks if another xexplorer window is at the drop point;
        // if so it routes the tab there, otherwise it spawns a new window.
        getBridge(br => {
            br.drop_tab(tab.browsePath || '', tab.title || '');
            // If it was the last tab, close the whole window (like browsers)
            if (isLastTab) br.close_window();
        });
        if (!isLastTab) closeTab(tabId);
    }

    function handleReorder(tabId, insertIdx) {
        setTabs(prev => {
            const idx = prev.findIndex(t => t.id === tabId);
            if (idx === -1) return prev;
            const next = [...prev];
            const [tab] = next.splice(idx, 1);
            const target = insertIdx > idx ? insertIdx - 1 : insertIdx;
            next.splice(Math.max(0, target), 0, tab);
            return next;
        });
    }

    function handleBrowseFolder(path) {
        const title = path.split(/[/\\]/).filter(Boolean).pop() || path;
        setTabs(prev => prev.map(t => t.id === activeTabId
            ? { ...t, browsePath: path, browseStack: [], query: '', title }
            : t));
    }

    const searchTimer = useRef(null);
    const b = useRef(null);


    // ── Bridge init ───────────────────────────────────────────────────────────
    useEffect(() => {
        getBridge(async br => {
            b.current = br;

            // Signals
            if (br.indexing_progress?.connect) {
                br.indexing_progress.connect((count, msg) => {
                    setIndexProgress(`${count.toLocaleString()} items — ${msg.slice(0, 55)}`);
                    setIndexing(true);
                });
            }
            if (br.indexing_done?.connect) {
                br.indexing_done.connect((count, dur) => {
                    setIndexing(false);
                    setIndexProgress('');
                    setStatusMsg(`✅ Indexed ${count.toLocaleString()} items in ${dur.toFixed(1)}s`);
                    reloadStats(br);
                    showToast(`Indexed ${count.toLocaleString()} items in ${dur.toFixed(1)}s`);
                });
            }
            if (br.stats_updated?.connect) {
                br.stats_updated.connect(raw => { setStats(JSON.parse(raw)); });
            }
            if (br.live_changed?.connect) {
                br.live_changed.connect(() => {
                    setLiveOn(true);
                    // Debounce: wait 1.5s after the last event before refreshing
                    // (avoids hammering on bulk copies / renames)
                    clearTimeout(liveTickRef.current);
                    liveTickRef.current = setTimeout(() => setLiveRefreshTick(t => t + 1), 1500);
                });
            }
            // Receive a tab dragged in from another xexplorer window
            if (br.tab_incoming?.connect) {
                br.tab_incoming.connect(json => {
                    const { path, title } = JSON.parse(json);
                    const id = Date.now();
                    const newTab = {
                        ...INIT_TAB(id, path || null),
                        title: title || (path ? path.split(/[/\\]/).filter(Boolean).pop() : 'New Tab'),
                    };
                    setTabs(prev => [...prev, newTab]);
                    setActiveTabId(id);
                });
            }

            const watchdog = await br.is_watchdog_available();
            setLiveOn(!!watchdog);

            await loadConfig(br);
            await reloadStats(br);
            const rawFavs = await br.get_favorites();
            setFavorites(JSON.parse(rawFavs));

            // Navigate to initial path if this window was spawned by a tearoff
            const initPath = await br.get_initial_path();
            if (initPath) {
                const title = initPath.split(/[/\\]/).filter(Boolean).pop() || initPath;
                setTabs(prev => prev.map((t, i) => i === 0
                    ? { ...t, browsePath: initPath, browseStack: [], title }
                    : t));
            }
        });
    }, []);

    async function loadConfig(br) {
        const raw = await br.get_config();
        const cfg = JSON.parse(raw);
        setFolders(cfg.folders || []);
        setIgnore(cfg.ignore || []);
        setSelectedFolders((cfg.folders || []).map(f => f.path));
    }

    async function reloadStats(br) {
        const raw = await br.get_stats();
        setStats(JSON.parse(raw));
    }

    // ── Browse effect ─────────────────────────────────────────────
    useEffect(() => {
        if (activeTab.browsePath === null) return;
        const tabId = activeTabId;
        const path = activeTab.browsePath;
        patchTab(tabId, { loading: true, selected: new Set() });
        getBridge(async br => {
            const raw = await br.list_folder(path);
            const list = JSON.parse(raw);
            patchTab(tabId, { results: list, loading: false });
            setStatusMsg(`📁 ${list.length} items`);
            // Tell the bridge which folder to poll for live updates
            if (br.set_active_browse_path) br.set_active_browse_path(path);
        });
    }, [activeTabId, activeTab.browsePath, liveRefreshTick]);

    async function handleNavUp() {
        const { browseStack, browsePath } = activeTab;
        if (browseStack.length > 0) {
            const prev = browseStack[browseStack.length - 1];
            const title = prev.split(/[/\\]/).filter(Boolean).pop() || prev;
            patchActive({ browseStack: browseStack.slice(0, -1), browsePath: prev, title });
        } else {
            patchActive({ browsePath: null, browseStack: [], results: [], title: 'New Tab' });
            setStatusMsg('Ready');
        }
    }

    function handleBrowseHome() {
        patchActive({ browsePath: null, browseStack: [], results: [], title: 'New Tab' });
        setStatusMsg('Ready');
    }

    async function persistConfig(newFolders, newIgnore) {
        const br = b.current;
        if (!br) return;
        await br.save_config(JSON.stringify({ folders: newFolders, ignore: newIgnore }));
    }

    // ── Search ────────────────────────────────────────────────────────────────
    useEffect(() => {
        if (activeTab.query.trim()) {
            // user is typing → exit browse mode in active tab
            patchActive({ browsePath: null, browseStack: [] });
        }
        clearTimeout(searchTimer.current);
        searchTimer.current = setTimeout(() => doSearch(), 130);
        return () => clearTimeout(searchTimer.current);
    }, [activeTab.query, filter, selectedFolders, activeTabId, liveRefreshTick]);

    async function doSearch() {
        if (activeTab.browsePath !== null) return; // skip when in browse mode
        const br = b.current;
        if (!br) return;
        const tabId = activeTabId;
        const q = activeTab.query.trim();
        patchTab(tabId, { selected: new Set() });
        if (q.length < 2 && filter !== 'recent') {
            patchTab(tabId, { results: [] });
            setStatusMsg(stats.count ? `${stats.count.toLocaleString()} items indexed · type to search` : 'Add folders and index to start');
            return;
        }
        patchTab(tabId, { loading: true });
        const t0 = performance.now();
        try {
            const activeFolders = selectedFolders.length ? selectedFolders : folders.map(f => f.path);
            const raw = await br.search(q, filter, JSON.stringify(activeFolders));
            const list = JSON.parse(raw);
            patchTab(tabId, { results: list, loading: false });
            const ms = (performance.now() - t0).toFixed(1);
            setStatusMsg(`⚡ ${list.length.toLocaleString()} results in ${ms}ms`);
        } catch (e) {
            console.error('search error', e);
            patchTab(tabId, { loading: false });
        }
    }

    // ── Sorted results ────────────────────────────────────────────────────────
    const sortedResults = useMemo(() => {
        const arr = [...activeTab.results];
        arr.sort((a, b) => {
            // Dirs always first
            if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
            let av = a[sortKey] ?? '', bv = b[sortKey] ?? '';
            if (typeof av === 'string') av = av.toLowerCase();
            if (typeof bv === 'string') bv = bv.toLowerCase();
            return sortDir === 'asc' ? (av < bv ? -1 : av > bv ? 1 : 0)
                : (av > bv ? -1 : av < bv ? 1 : 0);
        });
        return arr;
    }, [activeTab.results, sortKey, sortDir]);

    function handleSort(key) {
        if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
        else { setSortKey(key); setSortDir('asc'); }
    }

    // ── Selection ─────────────────────────────────────────────────────────────
    function handleSelect(file, e) {
        if (e.shiftKey) {
            const anchorPath = activeTab.selectionAnchor || file.path;
            const anchorIdx = sortedResults.findIndex(x => x.path === anchorPath);
            const currentIdx = sortedResults.findIndex(x => x.path === file.path);
            if (anchorIdx >= 0 && currentIdx >= 0) {
                const lo = Math.min(anchorIdx, currentIdx);
                const hi = Math.max(anchorIdx, currentIdx);
                const range = new Set(sortedResults.slice(lo, hi + 1).map(x => x.path));
                patchActive({ selected: range, previewFile: file, selectionAnchor: anchorPath });
                return;
            }
        }

        if (e.ctrlKey) {
            const next = new Set(activeTab.selected);
            if (next.has(file.path)) next.delete(file.path);
            else next.add(file.path);
            patchActive({ selected: next, previewFile: activeTab.previewFile, selectionAnchor: file.path });
            return;
        }

        // Plain click on already-selected item → deselect / clear
        if (activeTab.selected.has(file.path)) {
            patchActive({ selected: new Set(), previewFile: null, selectionAnchor: null });
            return;
        }
        patchActive({
            selected: new Set([file.path]),
            previewFile: file,
            selectionAnchor: file.path,
        });
    }

    function handleDouble(file) {
        if (file.is_dir) {
            const title = file.name;
            setTabs(prev => prev.map(t => t.id === activeTabId ? {
                ...t,
                browseStack: t.browsePath !== null ? [...t.browseStack, t.browsePath] : t.browseStack,
                browsePath: file.path,
                query: '',
                title,
            } : t));
        } else {
            getBridge(br => br.open_path(file.path));
        }
        patchActive({ previewFile: null });
    }

    // ── Context menu ──────────────────────────────────────────────────────────
    function handleCtxMenu(e, file) {
        const paths = activeTab.selected.has(file.path)
            ? sortedResults.filter(f => activeTab.selected.has(f.path))
            : [file];
        if (!activeTab.selected.has(file.path)) patchActive({ selected: new Set([file.path]) });
        const pathStrs = paths.map(p => p.path);
        const isFav = favorites.some(f => f.path === file.path);

        const items = [
            { icon: '📂', label: 'Open', action: () => getBridge(b => pathStrs.forEach(p => b.open_path(p))) },
            { icon: '🔍', label: 'Show in Explorer', action: () => getBridge(b => b.show_in_explorer(pathStrs[0])) },
            { icon: '📋', label: 'Copy Path', action: () => { getBridge(b => b.copy_to_clipboard(pathStrs.join('\n'))); showToast('Path copied'); } },
            'sep',
            { icon: '👁️', label: 'Preview', action: () => patchActive({ previewFile: file }) },
            ...(file.is_dir ? [{ icon: '🗂️', label: 'Open in new tab', action: () => addTab(file.path) }] : []),
            {
                icon: isFav ? '💔' : '⭐', label: isFav ? 'Remove from Favorites' : 'Add to Favorites',
                action: () => isFav ? handleRemoveFavorite(file.path) : handleAddFavorite(file)
            },
            'sep',
            { icon: '📄', label: 'Open in File Ops', action: () => getBridge(b => b.open_in_file_ops(JSON.stringify(pathStrs))) },
            { icon: '🗜️', label: 'Compress / Extract…', action: () => getBridge(b => b.open_in_archiver(JSON.stringify(pathStrs))) },
            'sep',
            { icon: '🔗', label: `${paths.length} item${paths.length > 1 ? 's' : ''} selected`, action: () => { } },
        ];
        setCtxMenu({ pos: { x: e.clientX, y: e.clientY }, files: paths, items });
    }

    // ── Folder management ──────────────────────────────────────────────────────
    async function handleAddFolder() {
        const br = b.current;
        if (!br) return;
        const path = await br.pick_folder();
        if (!path) return;
        const label = path.split(/[/\\]/).filter(Boolean).pop() || path;
        const newFolders = [...folders, { path, label }];
        setFolders(newFolders);
        setSelectedFolders(prev => [...prev, path]);
        await persistConfig(newFolders, ignore);
        showToast(`Added: ${label}`);
    }

    function handleRemoveFolder(path) {
        const newFolders = folders.filter(f => f.path !== path);
        setFolders(newFolders);
        setSelectedFolders(prev => prev.filter(p => p !== path));
        persistConfig(newFolders, ignore);
    }

    async function handleScanDrives() {
        const br = b.current;
        if (!br) return;
        const raw = await br.get_drives();
        const drives = JSON.parse(raw);
        const existing = new Set(folders.map(f => f.path));
        const newOnes = drives.filter(d => !existing.has(d)).map(d => ({ path: d, label: d }));
        if (!newOnes.length) { showToast('No new drives found'); return; }
        const newFolders = [...folders, ...newOnes];
        setFolders(newFolders);
        await persistConfig(newFolders, ignore);
        showToast(`Added ${newOnes.length} drive(s)`);
    }

    function handleFolderToggle(path) {
        setSelectedFolders(prev =>
            prev.includes(path) ? prev.filter(p => p !== path) : [...prev, path]
        );
    }

    function handleScopeOnly(path) {
        setSelectedFolders([path]);
        showToast(`🎯 Searching only in: ${path.split(/[/\\]/).filter(Boolean).pop() || path}`);
    }

    function handleResetScope() {
        setSelectedFolders(folders.map(f => f.path));
    }

    async function handleIndexFolder(path) {
        const br = b.current;
        if (!br) return;
        setIndexing(true);
        setStatusMsg('Starting indexing…');
        await br.start_indexing(JSON.stringify([path]));
    }

    async function handleIndexAll() {
        const br = b.current;
        if (!br) return;
        const paths = (selectedFolders.length ? selectedFolders : folders.map(f => f.path));
        if (!paths.length) { showToast('Add at least one folder first', true); return; }
        setIndexing(true);
        setStatusMsg('Starting indexing…');
        await br.start_indexing(JSON.stringify(paths));
    }

    async function handleClearIndex() {
        const br = b.current;
        if (!br) return;
        if (!confirm(`Clear the entire index (${stats.db_mb} MB)? You'll need to re-index.`)) return;
        await br.clear_index();
        setTabs(prev => prev.map(t => ({ ...t, results: [] })));
        setStatusMsg('Index cleared');
        showToast('Index cleared');
    }

    // ── Ignore ─────────────────────────────────────────────────────────────────
    async function handleAddIgnore() {
        const br = b.current;
        if (!br) return;
        const rule = await br.prompt_ignore_rule();
        if (!rule) return;
        const newIgnore = [...ignore, { rule, enabled: true }];
        setIgnore(newIgnore);
        await persistConfig(folders, newIgnore);
    }

    function handleToggleIgnore(rule) {
        const newIgnore = ignore.map(r => r.rule === rule ? { ...r, enabled: !r.enabled } : r);
        setIgnore(newIgnore);
        persistConfig(folders, newIgnore);
    }

    function handleRemoveIgnore(rule) {
        const newIgnore = ignore.filter(r => r.rule !== rule);
        setIgnore(newIgnore);
        persistConfig(folders, newIgnore);
    }

    // ── Keyboard shortcuts ────────────────────────────────────────────────────
    useEffect(() => {
        function onKey(e) {
            if ((e.ctrlKey || e.metaKey) && e.key === 'p') { e.preventDefault(); setPalette(true); return; }
            if ((e.ctrlKey || e.metaKey) && e.key === 't') { e.preventDefault(); addTab(); return; }
            if ((e.ctrlKey || e.metaKey) && e.key === 'w') { e.preventDefault(); closeTab(activeTabId); return; }
            if (e.ctrlKey && e.key === 'Tab') {
                e.preventDefault();
                const idx = tabs.findIndex(t => t.id === activeTabId);
                setActiveTabId(tabs[(idx + 1) % tabs.length].id);
                return;
            }
            if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'f')) {
                e.preventDefault();
                document.querySelector('.search-input')?.focus();
            }
            // Alt+Left or Backspace (outside input) = navigate up in browse mode
            if ((e.altKey && e.key === 'ArrowLeft') || (e.key === 'Backspace' && !e.target.matches('input,textarea') && activeTab.browsePath)) {
                e.preventDefault();
                handleNavUp();
                return;
            }
            if (e.key === 'Escape') { setCtxMenu(null); setPalette(false); patchActive({ previewFile: null }); }
            if (e.key === 'Enter' && !e.target.matches('input,textarea')) {
                const first = [...activeTab.selected][0];
                if (first) {
                    const f = sortedResults.find(r => r.path === first);
                    if (f?.is_dir) handleDouble(f); else getBridge(b => b.open_path(first));
                }
            }
        }
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [activeTab.selected, activeTab.browsePath, activeTabId, tabs]);

    // ── Common view props ─────────────────────────────────────────────────────
    const viewProps = {
        files: sortedResults,
        selected: activeTab.selected,
        onSelect: handleSelect,
        onDouble: handleDouble,
        onCtxMenu: handleCtxMenu,
    };

    const hasPreview = !!activeTab.previewFile;

    // ── Render ────────────────────────────────────────────────────────────────
    return (
        <div className="shell" style={{ '--sidebar-w': sidebarWidth + 'px', '--preview-w': previewWidth + 'px' }}>

            {/* ── Toolbar ──────────────────────────────────────────────────── */}
            <header className="toolbar">
                <div className="brand">X<span>_</span>EXPLORER</div>

                {/* View buttons */}
                <div className="view-btns">
                    {[['details', '☰ List'], ['icons', '⊞ Icons'], ['tree', '⎇ Tree']].map(([v, lbl]) => (
                        <button key={v} className={`view-btn ${viewMode === v ? 'active' : ''}`} onClick={() => setViewMode(v)}>{lbl}</button>
                    ))}
                </div>

                <div className="toolbar-sep" />

                {/* Search */}
                <div className="search-wrap">
                    <span className="icon">🔍</span>
                    <input className="search-input" placeholder="Search files…"
                        value={activeTab.query} onChange={e => patchActive({ query: e.target.value })} />
                    {activeTab.query
                        ? <button className="search-clear" onClick={() => patchActive({ query: '' })}>×</button>
                        : <span className="search-kbd">Ctrl+F</span>
                    }
                </div>

                <div className="toolbar-sep" />

                {/* Actions */}
                {indexing
                    ? <button className="btn btn-secondary" onClick={() => b.current?.stop_indexing()}>■ Stop</button>
                    : <button className="btn btn-primary" onClick={handleIndexAll}>⚡ Index</button>
                }
                <button className="btn btn-ghost" onClick={handleClearIndex}>○ Clear DB</button>
                <button className="btn btn-ghost" title="Command Palette (Ctrl+P)" onClick={() => setPalette(true)}>⌘ Palette</button>
            </header>

            {/* ── Tabs bar ─────────────────────────────────────────────────── */}
            <TabBar
                tabs={tabs}
                activeTabId={activeTabId}
                onSelect={setActiveTabId}
                onClose={closeTab}
                onNew={() => addTab()}
                onTearOff={handleTearOff}
                onReorder={handleReorder}
            />

            {/* ── Filter row ────────────────────────────────────────────────── */}
            <div className="filter-row">
                {[['all', 'All'], ['files', 'Files'], ['folders', 'Folders'], ['recent', 'Recent']].map(([v, lbl]) => (
                    <button key={v} className={`chip ${filter === v ? 'active' : ''}`} onClick={() => setFilter(v)}>{lbl}</button>
                ))}
                <div className="filter-sep" />
                <div className="sort-pills">
                    {Object.entries(SORT_KEYS).map(([lbl, key]) => (
                        <button key={key}
                            className={`sort-pill ${sortKey === key ? 'active' : ''}`}
                            onClick={() => {
                                if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
                                else { setSortKey(key); setSortDir('asc'); }
                            }}>
                            {lbl}{sortKey === key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
                        </button>
                    ))}
                </div>
                <div style={{ flex: 1 }} />
                <span style={{ fontSize: 11, color: 'var(--text-disabled)' }}>
                    {stats.count.toLocaleString()} indexed
                </span>
            </div>
            {/* ── Scope bar — visible when not all folders are in scope ─── */}
            {folders.length > 0 && selectedFolders.length < folders.length && (
                <div className="scope-bar">
                    <span className="scope-label">🔍 Scope:</span>
                    {selectedFolders.length === 0
                        ? <span className="scope-empty">No folders selected — nothing will be searched</span>
                        : selectedFolders.map(p => {
                            const name = p.replace(/\\$/, '').split(/[/\\]/).filter(Boolean).pop() || p;
                            return (
                                <span key={p} className="scope-pill">
                                    {name}
                                    <button className="scope-pill-x" title={`Remove ${p} from scope`}
                                        onClick={() => handleFolderToggle(p)}>✕</button>
                                </span>
                            );
                        })
                    }
                    <button className="scope-reset" onClick={handleResetScope}>Reset scope</button>
                </div>
            )}

            {/* ── Sidebar ──────────────────────────────────────────────────── */}
            {/* app-body flex row */}
            <div className="app-body">

                <Sidebar
                    folders={folders} ignore={ignore}
                    selectedFolders={selectedFolders}
                    onFolderToggle={handleFolderToggle}
                    onAddFolder={handleAddFolder}
                    onRemoveFolder={handleRemoveFolder}
                    onIndexFolder={handleIndexFolder}
                    onToggleIgnore={handleToggleIgnore}
                    onRemoveIgnore={handleRemoveIgnore}
                    onAddIgnore={handleAddIgnore}
                    onScanDrives={handleScanDrives}
                    onBrowseFolder={handleBrowseFolder}
                    onScopeOnly={handleScopeOnly}
                    favorites={favorites}
                    onFavClick={handleFavClick}
                    onFavRemove={handleRemoveFavorite}
                    onFavShowInExplorer={handleFavShowInExplorer}
                    onFavNewTab={handleFavNewTab}
                />
                <Resizer onDrag={dx => setSidebarWidth(w => Math.max(150, Math.min(520, w + dx)))} />
                <div className="main-panel">

                    {/* Breadcrumb — shown when navigating a folder */}
                    {activeTab.browsePath && (
                        <Breadcrumb path={activeTab.browsePath} onBack={handleNavUp} onHome={handleBrowseHome}
                            onNavigate={path => {
                                const title = path.replace(/\\$/, '').split(/[/\\]/).filter(Boolean).pop() || path;
                                setTabs(prev => prev.map(t => t.id === activeTabId
                                    ? { ...t, browsePath: path, browseStack: [], query: '', title }
                                    : t));
                            }} />
                    )}

                    {/* Selection bar */}
                    {activeTab.selected.size > 0 && (
                        <div className="sel-bar">
                            <span>{activeTab.selected.size} selected</span>
                            <button className="btn btn-ghost" style={{ padding: '2px 8px', fontSize: 11 }}
                                onClick={() => { getBridge(b => b.copy_to_clipboard([...activeTab.selected].join('\n'))); showToast('Paths copied'); }}>
                                📋 Copy paths
                            </button>
                            <button className="btn btn-ghost" style={{ padding: '2px 8px', fontSize: 11 }}
                                onClick={() => patchActive({ selected: new Set() })}>
                                ✕ Deselect
                            </button>
                        </div>
                    )}

                    {/* Views */}
                    {activeTab.loading && (
                        <div style={{ padding: '6px 14px', fontSize: 11, color: 'var(--text-disabled)' }}>Searching…</div>
                    )}

                    {!activeTab.loading && activeTab.results.length === 0 && activeTab.browsePath !== null ? (
                        <div className="empty-state" style={{ flex: 1 }}>
                            <span className="empty-icon" style={{ fontSize: 52 }}>📂</span>
                            <span className="empty-title">Folder is empty</span>
                            <span className="empty-sub" style={{ fontFamily: 'monospace', fontSize: 11 }}>{activeTab.browsePath}</span>
                        </div>
                    ) : !activeTab.loading && activeTab.results.length === 0 && activeTab.query.length < 2 ? (
                        <div className="empty-state" style={{ flex: 1 }}>
                            <div style={{ fontSize: 56, marginBottom: 8, lineHeight: 1, filter: 'drop-shadow(0 4px 18px color-mix(in srgb,var(--accent) 40%,transparent))' }}>🔍</div>
                            <span className="empty-title">Search your files</span>
                            <span className="empty-sub">
                                {folders.length === 0
                                    ? 'Add a folder in the sidebar, then click ⚡ Index to get started.'
                                    : `${stats.count.toLocaleString()} items indexed · type at least 2 characters`
                                }
                            </span>
                            {folders.length > 0 && stats.count === 0 && (
                                <button className="btn btn-primary" style={{ marginTop: 14, padding: '8px 20px' }} onClick={handleIndexAll}>⚡ Index Now</button>
                            )}
                            {folders.length === 0 && (
                                <button className="btn btn-primary" style={{ marginTop: 14, padding: '8px 20px' }} onClick={handleAddFolder}>+ Add Folder</button>
                            )}
                        </div>
                    ) : !activeTab.loading && activeTab.results.length === 0 ? (
                        <div className="empty-state" style={{ flex: 1 }}>
                            <span className="empty-icon">🕳️</span>
                            <span className="empty-title">No results</span>
                            <span className="empty-sub">Try different search terms or check your folder selection.</span>
                        </div>
                    ) : viewMode === 'details' ? (
                        <DetailsView {...viewProps} sortKey={sortKey} sortDir={sortDir} onSort={handleSort} />
                    ) : viewMode === 'icons' ? (
                        <IconsView {...viewProps} />
                    ) : (
                        <TreeView {...viewProps} />
                    )}
                </div>{/* main-panel */}
                {hasPreview && (
                    <>
                        <Resizer onDrag={dx => setPreviewWidth(w => Math.max(200, Math.min(700, w - dx)))} />
                        <PreviewPane file={activeTab.previewFile} onClose={() => patchActive({ previewFile: null })} />
                    </>
                )}
            </div>{/* app-body */}

            {/* statusbar */}
            <footer className="statusbar">
                {indexing ? (
                    <div className="indexing-bar">
                        <div className="progress-track"><div className="progress-fill" style={{ width: '40%' }} /></div>
                        <span>Indexing… {indexProgress}</span>
                    </div>
                ) : (
                    <span className="status-msg">{statusMsg}</span>
                )}
                <div className="live-dot" style={{ background: liveOn ? '#22c55e' : 'var(--text-disabled)' }} title={liveOn ? 'Live sync active' : 'No live sync'} />
                <span style={{ fontSize: 11 }}>{liveOn ? 'Live' : 'No live sync'}</span>
                <span style={{ fontSize: 11, color: 'var(--text-disabled)' }}>DB: {stats.db_mb} MB</span>
                <span style={{ fontSize: 11, color: 'var(--text-disabled)', marginLeft: 'auto' }}>Last indexed: {stats.last_indexed}</span>
            </footer>

            {/* ── Context menu ──────────────────────────────────────────────── */}
            {ctxMenu && <CtxMenu items={ctxMenu.items} pos={ctxMenu.pos} onClose={() => setCtxMenu(null)} />}

            {/* ── Command palette ───────────────────────────────────────────── */}
            {palette && (
                <CmdPalette
                    results={activeTab.results}
                    onClose={() => setPalette(false)}
                    onSelect={f => { handleDouble(f); }}
                />
            )}
        </div>
    );
};

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
