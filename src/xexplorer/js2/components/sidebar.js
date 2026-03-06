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
    favorites, onFavClick, onFavRemove, onFavShowInExplorer, onFavNewTab, onFavMove }) => {
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
                        : favorites.map((fav, idx) => {
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
                                    { icon: '▴', label: 'Move up', action: () => { onFavMove(fav.path, 'up'); favCtx.close(); }, disabled: idx === 0 },
                                    { icon: '▾', label: 'Move down', action: () => { onFavMove(fav.path, 'down'); favCtx.close(); }, disabled: idx === favorites.length - 1 },
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
                                    <div className="fav-actions">
                                        <button className="fav-move" title="Move up"
                                            disabled={idx === 0}
                                            onClick={e => { e.stopPropagation(); onFavMove(fav.path, 'up'); }}>▴</button>
                                        <button className="fav-move" title="Move down"
                                            disabled={idx === favorites.length - 1}
                                            onClick={e => { e.stopPropagation(); onFavMove(fav.path, 'down'); }}>▾</button>
                                        <button className="fav-remove"
                                            onMouseDown={e => e.stopPropagation()}
                                            onClick={e => { e.stopPropagation(); onFavRemove(fav.path); }}>✕</button>
                                    </div>
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
