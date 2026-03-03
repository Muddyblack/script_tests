// Workspace Manager — single-file React app
// Opens VS Code workspaces with optional window positioning

const { useState, useEffect, useCallback, useRef, useMemo } = React;
const { motion, AnimatePresence } = window.Motion;
const Icons = window.lucide;

// ── Icon wrapper ───────────────────────────────────────────────────────────
function Icon({ icon, size = 16, style, className }) {
    if (!icon || !Array.isArray(icon)) return null;
    return React.createElement(
        'svg',
        {
            xmlns: 'http://www.w3.org/2000/svg',
            width: size,
            height: size,
            viewBox: '0 0 24 24',
            fill: 'none',
            stroke: 'currentColor',
            strokeWidth: 2,
            strokeLinecap: 'round',
            strokeLinejoin: 'round',
            style: { flexShrink: 0, display: 'inline-block', ...style },
            className,
            'aria-hidden': 'true',
        },
        ...icon.map(([tag, attrs], i) =>
            React.createElement(tag, { key: i, ...attrs })
        )
    );
}

// ── Bridge (QWebChannel) ──────────────────────────────────────────────────
let _bridge = null;
let _bridgeReady = false;
const _bridgeCbs = [];

function getBridge(cb) {
    if (_bridgeReady) { cb(_bridge); return; }
    _bridgeCbs.push(cb);
}

if (typeof QWebChannel !== 'undefined') {
    new QWebChannel(qt.webChannelTransport, ch => {
        _bridge = ch.objects.pyBridge;
        _bridgeReady = true;
        _bridgeCbs.forEach(fn => fn(_bridge));
        _bridgeCbs.length = 0;
    });
} else {
    setTimeout(() => {
        _bridge = {
            get_workspaces: () => JSON.stringify([]),
            scan_vscode_recent: () => JSON.stringify([
                { path: 'C:\\Projects\\my-app', name: 'my-app', exists: true, source: 'vscode_recent' },
                { path: 'C:\\Projects\\website', name: 'website', exists: true, source: 'vscode_recent' },
            ]),
            add_workspace: (j) => j,
            update_workspace: (j) => j,
            delete_workspace: (id) => JSON.stringify({ deleted: true }),
            open_workspace: (p, pos) => JSON.stringify({ ok: true, path: p }),
            browse_folder: () => 'C:\\mock\\project',
            get_screen_info: () => JSON.stringify({ width: 1920, height: 1080 }),
            get_position_presets: () => JSON.stringify([
                { id: 'default', label: 'Default', icon: 'Monitor' },
                { id: 'left_half', label: 'Left Half', icon: 'PanelLeft' },
                { id: 'right_half', label: 'Right Half', icon: 'PanelRight' },
            ]),
            get_folder_info: (p) => JSON.stringify({ name: 'project', project_type: 'node', has_git: true, files: 12, dirs: 3 }),
            import_from_recent: (j) => j,
            workspace_opened: { connect: () => {} },
        };
        _bridgeReady = true;
        _bridgeCbs.forEach(fn => fn(_bridge));
        _bridgeCbs.length = 0;
    }, 50);
}

// ── Icon map for lucide icons by name ─────────────────────────────────────
const ICON_MAP = {
    Monitor: Icons.Monitor,
    PanelLeft: Icons.PanelLeft,
    PanelRight: Icons.PanelRight,
    PanelTop: Icons.PanelTop,
    PanelBottom: Icons.PanelBottom,
    ArrowUpLeft: Icons.ArrowUpLeft,
    ArrowUpRight: Icons.ArrowUpRight,
    ArrowDownLeft: Icons.ArrowDownLeft,
    ArrowDownRight: Icons.ArrowDownRight,
    Maximize2: Icons.Maximize2,
    Square: Icons.Square,
    Minimize2: Icons.Minimize2,
};

// ── Project type config ───────────────────────────────────────────────────
const PROJECT_TYPES = {
    python: { label: 'Python', color: '#3b82f6', icon: Icons.Code2 },
    node: { label: 'Node', color: '#22c55e', icon: Icons.Hexagon },
    rust: { label: 'Rust', color: '#ef4444', icon: Icons.Cog },
    git: { label: 'Git', color: '#f97316', icon: Icons.GitBranch },
    folder: { label: 'Folder', color: null, icon: Icons.Folder },
};

// ── Status toast ──────────────────────────────────────────────────────────
function useStatus() {
    const [status, setStatus] = useState(null);
    const timerRef = useRef(null);

    const flash = useCallback((msg, type = 'info') => {
        if (timerRef.current) clearTimeout(timerRef.current);
        setStatus({ msg, type });
        timerRef.current = setTimeout(() => setStatus(null), 3000);
    }, []);

    return [status, flash];
}

// ── Position Picker ───────────────────────────────────────────────────────
function PositionPicker({ presets, value, onChange }) {
    return (
        <div className="position-grid">
            {presets.map(p => (
                <button
                    key={p.id}
                    className={`pos-btn ${value === p.id ? 'active' : ''}`}
                    onClick={() => onChange(p.id)}
                    title={p.label}
                >
                    <Icon icon={ICON_MAP[p.icon] || Icons.Monitor} size={14} />
                    <span>{p.label}</span>
                </button>
            ))}
        </div>
    );
}

// ── Workspace item ────────────────────────────────────────────────────────
function WorkspaceItem({ ws, onOpen, onPin, onDelete, onEdit }) {
    const pt = PROJECT_TYPES[ws.project_type] || PROJECT_TYPES.folder;
    const bgColor = ws.color || pt.color || 'var(--text-disabled)';

    return (
        <motion.div
            className={`ws-item float-in ${!ws.exists ? 'ws-item-missing' : ''}`}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.12 }}
            layout
        >
            <div
                className="ws-item-icon"
                style={{
                    background: `color-mix(in srgb, ${bgColor} 14%, transparent)`,
                    border: `1px solid color-mix(in srgb, ${bgColor} 30%, transparent)`,
                    color: bgColor,
                }}
            >
                <Icon icon={pt.icon || Icons.Folder} size={18} />
            </div>

            <div className="ws-item-info">
                <div className="ws-item-name">{ws.name}</div>
                <div className="ws-item-path">{ws.path}</div>
                <div className="ws-item-meta">
                    {ws.project_type && ws.project_type !== 'folder' && (
                        <span className={`ws-tag ws-tag-${ws.project_type}`}>
                            {pt.label}
                        </span>
                    )}
                    {ws.has_git && ws.project_type !== 'git' && (
                        <span className="ws-tag ws-tag-git">Git</span>
                    )}
                    {ws.pinned && (
                        <span className="ws-tag ws-tag-pinned">
                            <Icon icon={Icons.Pin} size={8} /> Pinned
                        </span>
                    )}
                    {ws.open_count > 0 && (
                        <span style={{ fontSize: 9, color: 'var(--text-disabled)', fontFamily: "'JetBrains Mono', monospace" }}>
                            opened {ws.open_count}×
                        </span>
                    )}
                </div>
            </div>

            <div className="ws-item-actions">
                <button
                    className={`btn-icon tooltip ${ws.pinned ? '' : ''}`}
                    data-tip={ws.pinned ? 'Unpin' : 'Pin'}
                    onClick={(e) => { e.stopPropagation(); onPin(ws); }}
                    style={ws.pinned ? { color: '#eab308' } : {}}
                >
                    <Icon icon={ws.pinned ? Icons.PinOff : Icons.Pin} size={14} />
                </button>
                <button
                    className="btn-icon tooltip"
                    data-tip="Edit"
                    onClick={(e) => { e.stopPropagation(); onEdit(ws); }}
                >
                    <Icon icon={Icons.Pencil} size={14} />
                </button>
                <button
                    className="btn-icon btn-danger tooltip"
                    data-tip="Remove"
                    onClick={(e) => { e.stopPropagation(); onDelete(ws); }}
                >
                    <Icon icon={Icons.Trash2} size={14} />
                </button>
            </div>

            {ws.exists && (
                <button
                    className="btn-open"
                    onClick={(e) => { e.stopPropagation(); onOpen(ws); }}
                >
                    <Icon icon={Icons.ExternalLink} size={11} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle' }} />
                    Open
                </button>
            )}
        </motion.div>
    );
}

// ── Recent item (from VS Code scan) ───────────────────────────────────────
function RecentItem({ entry, onImport, onOpen, isImported }) {
    return (
        <motion.div
            className={`ws-item float-in ${!entry.exists ? 'ws-item-missing' : ''}`}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.12 }}
        >
            <div
                className="ws-item-icon"
                style={{
                    background: 'color-mix(in srgb, var(--text-disabled) 10%, transparent)',
                    border: '1px solid color-mix(in srgb, var(--text-disabled) 20%, transparent)',
                    color: 'var(--text-disabled)',
                }}
            >
                <Icon icon={Icons.Clock} size={18} />
            </div>

            <div className="ws-item-info">
                <div className="ws-item-name">{entry.name}</div>
                <div className="ws-item-path">{entry.path}</div>
            </div>

            <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}>
                {!isImported && (
                    <button
                        className="btn btn-ghost"
                        style={{ padding: '5px 12px', fontSize: 9 }}
                        onClick={() => onImport(entry)}
                        title="Save to your workspaces"
                    >
                        <Icon icon={Icons.Plus} size={11} style={{ display: 'inline', marginRight: 3, verticalAlign: 'middle' }} />
                        Save
                    </button>
                )}
                {isImported && (
                    <span style={{ fontSize: 9, color: 'var(--success, #22c55e)', fontFamily: "'JetBrains Mono', monospace", fontWeight: 700 }}>
                        ✓ Saved
                    </span>
                )}
                {entry.exists && (
                    <button
                        className="btn-open"
                        onClick={() => onOpen(entry)}
                    >
                        Open
                    </button>
                )}
            </div>
        </motion.div>
    );
}

// ── Add/Edit Modal ────────────────────────────────────────────────────────
function WorkspaceModal({ mode, workspace, presets, onClose, onSave }) {
    const [path, setPath] = useState(workspace?.path || '');
    const [name, setName] = useState(workspace?.name || '');
    const [position, setPosition] = useState(workspace?.position || 'default');
    const [folderInfo, setFolderInfo] = useState(null);

    useEffect(() => {
        if (path) {
            getBridge(b => {
                Promise.resolve(b.get_folder_info(path)).then(json => {
                    const info = JSON.parse(json);
                    if (!info.error) {
                        setFolderInfo(info);
                        if (!name) setName(info.name);
                    } else {
                        setFolderInfo(null);
                    }
                });
            });
        }
    }, [path]);

    const handleBrowse = () => {
        getBridge(b => {
            Promise.resolve(b.browse_folder()).then(p => {
                if (p) setPath(p);
            });
        });
    };

    const handleSave = () => {
        if (!path.trim()) return;
        onSave({
            id: workspace?.id,
            path: path.trim(),
            name: name.trim() || undefined,
            position,
        });
    };

    return (
        <motion.div
            className="modal-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={onClose}
        >
            <motion.div
                className="modal-content"
                initial={{ opacity: 0, scale: 0.95, y: 10 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 10 }}
                transition={{ duration: 0.15 }}
                onClick={e => e.stopPropagation()}
            >
                <div className="modal-title">
                    {mode === 'edit' ? 'Edit Workspace' : 'Add Workspace'}
                </div>

                <div>
                    <div className="section-label">Folder Path</div>
                    <div className="input-row">
                        <input
                            className="input-field"
                            placeholder="C:\Projects\my-app"
                            value={path}
                            onChange={e => setPath(e.target.value)}
                            autoFocus
                        />
                        <button className="btn btn-ghost" onClick={handleBrowse}>
                            <Icon icon={Icons.FolderOpen} size={13} />
                        </button>
                    </div>
                </div>

                <div>
                    <div className="section-label">Display Name</div>
                    <input
                        className="input-field"
                        placeholder={folderInfo?.name || 'Workspace name'}
                        value={name}
                        onChange={e => setName(e.target.value)}
                    />
                </div>

                {folderInfo && (
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                        {folderInfo.project_type !== 'folder' && (
                            <span className={`ws-tag ws-tag-${folderInfo.project_type}`}>
                                {PROJECT_TYPES[folderInfo.project_type]?.label || folderInfo.project_type}
                            </span>
                        )}
                        {folderInfo.has_git && (
                            <span className="ws-tag ws-tag-git">Git</span>
                        )}
                        <span style={{ fontSize: 10, color: 'var(--text-disabled)', fontFamily: "'JetBrains Mono', monospace" }}>
                            {folderInfo.files} files · {folderInfo.dirs} folders
                        </span>
                    </div>
                )}

                <div>
                    <div className="section-label">Window Position</div>
                    <PositionPicker presets={presets} value={position} onChange={setPosition} />
                </div>

                <div className="modal-actions">
                    <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
                    <button className="btn btn-primary" onClick={handleSave} disabled={!path.trim()}>
                        <Icon icon={mode === 'edit' ? Icons.Check : Icons.Plus} size={12} />
                        {mode === 'edit' ? 'Save' : 'Add Workspace'}
                    </button>
                </div>
            </motion.div>
        </motion.div>
    );
}

// ── Main App ──────────────────────────────────────────────────────────────
function App() {
    const [tab, setTab] = useState('workspaces');
    const [workspaces, setWorkspaces] = useState([]);
    const [recentEntries, setRecentEntries] = useState([]);
    const [importedPaths, setImportedPaths] = useState(new Set());
    const [search, setSearch] = useState('');
    const [presets, setPresets] = useState([]);
    const [modal, setModal] = useState(null); // { mode: 'add'|'edit', workspace? }
    const [status, flash] = useStatus();
    const [loading, setLoading] = useState(true);
    const searchRef = useRef(null);

    // Load data on mount
    useEffect(() => {
        getBridge(b => {
            Promise.all([
                Promise.resolve(b.get_workspaces()),
                Promise.resolve(b.get_position_presets()),
            ]).then(([wsJson, presetsJson]) => {
                const ws = JSON.parse(wsJson);
                setWorkspaces(ws);
                setPresets(JSON.parse(presetsJson));
                setImportedPaths(new Set(ws.map(w => w.path)));
                setLoading(false);
            });
        });
    }, []);

    // Load recent on tab switch
    useEffect(() => {
        if (tab === 'recent' && recentEntries.length === 0) {
            getBridge(b => {
                Promise.resolve(b.scan_vscode_recent()).then(json => {
                    setRecentEntries(JSON.parse(json));
                });
            });
        }
    }, [tab]);

    // Focus search on Ctrl+F
    useEffect(() => {
        const handler = (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
                e.preventDefault();
                searchRef.current?.focus();
            }
        };
        document.addEventListener('keydown', handler);
        return () => document.removeEventListener('keydown', handler);
    }, []);

    // ── Actions ───────────────────────────────────────────────────────────
    const refreshWorkspaces = useCallback(() => {
        getBridge(b => {
            Promise.resolve(b.get_workspaces()).then(json => {
                const ws = JSON.parse(json);
                setWorkspaces(ws);
                setImportedPaths(new Set(ws.map(w => w.path)));
            });
        });
    }, []);

    const handleOpen = useCallback((ws) => {
        const pos = ws.position || 'default';
        getBridge(b => {
            Promise.resolve(b.open_workspace(ws.path, pos)).then(json => {
                const result = JSON.parse(json);
                if (result.error) {
                    flash(result.error, 'error');
                } else {
                    flash(`Opened ${ws.name || ws.path}`, 'success');
                    refreshWorkspaces();
                }
            });
        });
    }, [flash, refreshWorkspaces]);

    const handlePin = useCallback((ws) => {
        getBridge(b => {
            Promise.resolve(b.update_workspace(JSON.stringify({ id: ws.id, pinned: !ws.pinned }))).then(() => {
                refreshWorkspaces();
                flash(ws.pinned ? 'Unpinned' : 'Pinned', 'info');
            });
        });
    }, [flash, refreshWorkspaces]);

    const handleDelete = useCallback((ws) => {
        getBridge(b => {
            Promise.resolve(b.delete_workspace(ws.id)).then(() => {
                refreshWorkspaces();
                flash(`Removed ${ws.name}`, 'info');
            });
        });
    }, [flash, refreshWorkspaces]);

    const handleEdit = useCallback((ws) => {
        setModal({ mode: 'edit', workspace: ws });
    }, []);

    const handleModalSave = useCallback((data) => {
        getBridge(b => {
            if (data.id) {
                // Editing
                Promise.resolve(b.update_workspace(JSON.stringify(data))).then(() => {
                    refreshWorkspaces();
                    flash('Updated workspace', 'success');
                    setModal(null);
                });
            } else {
                // Adding
                Promise.resolve(b.add_workspace(JSON.stringify(data))).then(json => {
                    const result = JSON.parse(json);
                    if (result.error) {
                        flash(result.error, 'error');
                    } else {
                        refreshWorkspaces();
                        flash(`Added ${result.name}`, 'success');
                        setModal(null);
                    }
                });
            }
        });
    }, [flash, refreshWorkspaces]);

    const handleImport = useCallback((entry) => {
        getBridge(b => {
            Promise.resolve(b.import_from_recent(JSON.stringify(entry))).then(json => {
                const result = JSON.parse(json);
                if (result.error && !result.id) {
                    flash(result.error, 'error');
                } else {
                    setImportedPaths(prev => new Set([...prev, entry.path]));
                    refreshWorkspaces();
                    flash(`Saved ${entry.name}`, 'success');
                }
            });
        });
    }, [flash, refreshWorkspaces]);

    const handleOpenRecent = useCallback((entry) => {
        handleOpen({ path: entry.path, name: entry.name, position: 'default' });
    }, [handleOpen]);

    // ── Filtering & sorting ───────────────────────────────────────────────
    const filteredWorkspaces = useMemo(() => {
        const q = search.toLowerCase();
        let list = workspaces.filter(ws =>
            !q || ws.name.toLowerCase().includes(q) || ws.path.toLowerCase().includes(q)
        );
        // Sort: pinned first, then by last_opened desc, then by name
        list.sort((a, b) => {
            if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
            if (a.last_opened !== b.last_opened) return (b.last_opened || 0) - (a.last_opened || 0);
            return a.name.localeCompare(b.name);
        });
        return list;
    }, [workspaces, search]);

    const filteredRecent = useMemo(() => {
        const q = search.toLowerCase();
        return recentEntries.filter(e =>
            !q || e.name.toLowerCase().includes(q) || e.path.toLowerCase().includes(q)
        );
    }, [recentEntries, search]);

    const wsCount = filteredWorkspaces.length;
    const totalWs = workspaces.length;

    return (
        <div className="app-shell">
            {/* Header */}
            <div className="app-header">
                <div className="app-header-icon">
                    <Icon icon={Icons.LayoutGrid} size={16} />
                </div>
                <div>
                    <div className="app-header-title">Workspace Manager</div>
                    <div className="app-header-sub">open · organize · launch VS Code workspaces</div>
                </div>
                <div className="app-header-right">
                    <button
                        className="btn btn-primary"
                        onClick={() => setModal({ mode: 'add', workspace: null })}
                    >
                        <Icon icon={Icons.Plus} size={12} />
                        Add
                    </button>
                </div>
            </div>

            {/* Search */}
            <div className="search-wrap">
                <div className="search-icon-wrap">
                    <span className="search-icon">
                        <Icon icon={Icons.Search} size={14} />
                    </span>
                    <input
                        ref={searchRef}
                        className="search-field"
                        placeholder="Search workspaces…  (Ctrl+F)"
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        spellCheck={false}
                    />
                </div>
            </div>

            {/* Tabs */}
            <div className="tab-bar">
                <button
                    className={`tab-btn ${tab === 'workspaces' ? 'active' : ''}`}
                    onClick={() => setTab('workspaces')}
                >
                    <Icon icon={Icons.FolderOpen} size={11} style={{ display: 'inline', marginRight: 5, verticalAlign: 'middle' }} />
                    Workspaces
                    {totalWs > 0 && (
                        <span style={{ marginLeft: 6, opacity: 0.5 }}>{totalWs}</span>
                    )}
                </button>
                <button
                    className={`tab-btn ${tab === 'recent' ? 'active' : ''}`}
                    onClick={() => setTab('recent')}
                >
                    <Icon icon={Icons.Clock} size={11} style={{ display: 'inline', marginRight: 5, verticalAlign: 'middle' }} />
                    VS Code Recent
                </button>
            </div>

            {/* Content */}
            <AnimatePresence mode="wait">
                {tab === 'workspaces' ? (
                    <motion.div
                        key="workspaces"
                        className="content-area"
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        transition={{ duration: 0.14 }}
                    >
                        {loading ? (
                            <div className="empty-state">
                                <div className="empty-state-icon">
                                    <Icon icon={Icons.Loader2} size={22} style={{ animation: 'spin 1s linear infinite' }} />
                                </div>
                                <div className="empty-state-title">Loading…</div>
                            </div>
                        ) : wsCount === 0 && totalWs === 0 ? (
                            <div className="empty-state">
                                <div className="empty-state-icon">
                                    <Icon icon={Icons.FolderPlus} size={22} />
                                </div>
                                <div className="empty-state-title">No workspaces yet</div>
                                <div className="empty-state-hint">
                                    Add a workspace folder or import from VS Code's recent list to get started.
                                </div>
                                <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                                    <button className="btn btn-primary" onClick={() => setModal({ mode: 'add', workspace: null })}>
                                        <Icon icon={Icons.Plus} size={12} /> Add Workspace
                                    </button>
                                    <button className="btn btn-ghost" onClick={() => setTab('recent')}>
                                        <Icon icon={Icons.Clock} size={12} /> Browse Recent
                                    </button>
                                </div>
                            </div>
                        ) : wsCount === 0 ? (
                            <div className="empty-state">
                                <div className="empty-state-icon">
                                    <Icon icon={Icons.SearchX} size={22} />
                                </div>
                                <div className="empty-state-title">No matches</div>
                                <div className="empty-state-hint">
                                    No workspaces match "{search}"
                                </div>
                            </div>
                        ) : (
                            <AnimatePresence>
                                {filteredWorkspaces.map(ws => (
                                    <WorkspaceItem
                                        key={ws.id}
                                        ws={ws}
                                        onOpen={handleOpen}
                                        onPin={handlePin}
                                        onDelete={handleDelete}
                                        onEdit={handleEdit}
                                    />
                                ))}
                            </AnimatePresence>
                        )}
                    </motion.div>
                ) : (
                    <motion.div
                        key="recent"
                        className="content-area"
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        transition={{ duration: 0.14 }}
                    >
                        {filteredRecent.length === 0 ? (
                            <div className="empty-state">
                                <div className="empty-state-icon">
                                    <Icon icon={Icons.Clock} size={22} />
                                </div>
                                <div className="empty-state-title">
                                    {recentEntries.length === 0 ? 'Scanning VS Code…' : 'No matches'}
                                </div>
                                <div className="empty-state-hint">
                                    {recentEntries.length === 0
                                        ? 'Looking for recently opened workspaces in VS Code.'
                                        : `No recent entries match "${search}"`
                                    }
                                </div>
                            </div>
                        ) : (
                            <>
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 2 }}>
                                    <span className="section-label" style={{ marginBottom: 0 }}>
                                        {filteredRecent.length} recent workspace{filteredRecent.length !== 1 ? 's' : ''} found
                                    </span>
                                </div>
                                <AnimatePresence>
                                    {filteredRecent.map((entry, i) => (
                                        <RecentItem
                                            key={entry.path}
                                            entry={entry}
                                            onImport={handleImport}
                                            onOpen={handleOpenRecent}
                                            isImported={importedPaths.has(entry.path)}
                                        />
                                    ))}
                                </AnimatePresence>
                            </>
                        )}
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Status bar */}
            <div className="status-bar">
                <span className={`status-text ${status?.type || ''}`}>
                    {status?.msg || `${totalWs} workspace${totalWs !== 1 ? 's' : ''}`}
                </span>
                <span className="status-text" style={{ opacity: 0.5 }}>
                    Ctrl+F to search
                </span>
            </div>

            {/* Modal */}
            <AnimatePresence>
                {modal && (
                    <WorkspaceModal
                        mode={modal.mode}
                        workspace={modal.workspace}
                        presets={presets}
                        onClose={() => setModal(null)}
                        onSave={handleModalSave}
                    />
                )}
            </AnimatePresence>
        </div>
    );
}

// ── Mount ─────────────────────────────────────────────────────────────────
const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(React.createElement(App));
