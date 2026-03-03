// Workspace Manager — React app
// Manage multi-program workspaces: capture open windows, add programs, launch & position

const { useState, useEffect, useCallback, useRef, useMemo } = React;
const { motion, AnimatePresence } = window.Motion;
const Icons = window.lucide;

// ── Icon wrapper ───────────────────────────────────────────────────────────
function Icon({ icon, size = 16, style, className }) {
    if (!icon || !Array.isArray(icon)) return null;
    return React.createElement('svg', {
        xmlns: 'http://www.w3.org/2000/svg', width: size, height: size,
        viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
        strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round',
        style: { flexShrink: 0, display: 'inline-block', ...style },
        className, 'aria-hidden': 'true',
    }, ...icon.map(([tag, attrs], i) => React.createElement(tag, { key: i, ...attrs })));
}

// ── Bridge ─────────────────────────────────────────────────────────────────
let _bridge = null, _bridgeReady = false;
const _cbs = [];
function getBridge(cb) { if (_bridgeReady) { cb(_bridge); return; } _cbs.push(cb); }

if (typeof QWebChannel !== 'undefined') {
    new QWebChannel(qt.webChannelTransport, ch => {
        _bridge = ch.objects.pyBridge;
        _bridgeReady = true;
        _cbs.forEach(fn => fn(_bridge));
        _cbs.length = 0;
    });
} else {
    // Dev mock
    setTimeout(() => {
        _bridge = {
            get_workspaces: () => JSON.stringify([]),
            save_workspace: (j) => { const d = JSON.parse(j); d.id = Date.now(); return JSON.stringify(d); },
            delete_workspace: () => JSON.stringify({ deleted: true }),
            launch_workspace: () => JSON.stringify({ ok: true, launched: 2 }),
            toggle_pin: () => {},
            list_windows_sync: () => JSON.stringify([
                { hwnd: 1, title: 'My Project — Visual Studio Code', pid: 100, proc_name: 'Code.exe', exec_path: 'C:\\Code\\Code.exe', x: 0, y: 0, w: 960, h: 1080 },
                { hwnd: 2, title: 'Google Chrome', pid: 200, proc_name: 'chrome.exe', exec_path: 'C:\\Chrome\\chrome.exe', x: 960, y: 0, w: 960, h: 1080 },
                { hwnd: 3, title: 'Windows Terminal', pid: 300, proc_name: 'WindowsTerminal.exe', exec_path: 'C:\\Terminal\\wt.exe', x: 100, y: 100, w: 800, h: 600 },
            ]),
            refresh_windows: () => {},
            snap_window: () => {},
            focus_window: () => {},
            minimize_window: () => {},
            maximize_window: () => {},
            close_window: () => {},
            capture_windows: (j) => { const d = JSON.parse(j); d.id = Date.now(); d.entries = []; return JSON.stringify(d); },
            scan_vscode_recent: () => JSON.stringify([
                { path: 'C:\\Projects\\my-app', name: 'my-app', exists: true },
            ]),
            browse_folder: () => 'C:\\mock',
            browse_file: () => 'C:\\mock\\app.exe',
            get_screen_info: () => JSON.stringify({ width: 1920, height: 1080 }),
            get_position_presets: () => JSON.stringify([
                { id: 'default', label: 'Default', icon: 'Monitor' },
                { id: 'left_half', label: 'Left Half', icon: 'PanelLeft' },
                { id: 'right_half', label: 'Right Half', icon: 'PanelRight' },
                { id: 'fullscreen', label: 'Full Screen', icon: 'Maximize2' },
            ]),
            windows_refreshed: { connect: () => {} },
            workspace_opened: { connect: () => {} },
        };
        _bridgeReady = true;
        _cbs.forEach(fn => fn(_bridge));
        _cbs.length = 0;
    }, 50);
}

// ── Icon map ──────────────────────────────────────────────────────────────
const ICON_MAP = {
    Monitor: Icons.Monitor, PanelLeft: Icons.PanelLeft, PanelRight: Icons.PanelRight,
    PanelTop: Icons.PanelTop, PanelBottom: Icons.PanelBottom,
    ArrowUpLeft: Icons.ArrowUpLeft, ArrowUpRight: Icons.ArrowUpRight,
    ArrowDownLeft: Icons.ArrowDownLeft, ArrowDownRight: Icons.ArrowDownRight,
    Maximize2: Icons.Maximize2, Square: Icons.Square, Minimize2: Icons.Minimize2,
    Move: Icons.Move,
};

// ── Status hook ───────────────────────────────────────────────────────────
function useStatus() {
    const [s, setS] = useState(null);
    const t = useRef(null);
    const flash = useCallback((msg, type = 'info') => {
        clearTimeout(t.current);
        setS({ msg, type });
        t.current = setTimeout(() => setS(null), 3000);
    }, []);
    return [s, flash];
}

// ── Shorten path for display ──────────────────────────────────────────────
function shortPath(p) {
    if (!p) return '';
    const parts = p.replace(/\\/g, '/').split('/');
    if (parts.length <= 3) return p;
    return parts[0] + '/…/' + parts.slice(-2).join('/');
}

// ── Position Picker (inline grid) ─────────────────────────────────────────
function PositionPicker({ presets, value, onChange, compact }) {
    return (
        <div className={compact ? 'pos-grid-compact' : 'position-grid'}>
            {presets.filter(p => p.id !== 'custom').map(p => (
                <button key={p.id}
                    className={`pos-btn ${value === p.id ? 'active' : ''}`}
                    onClick={() => onChange(p.id)} title={p.label}>
                    <Icon icon={ICON_MAP[p.icon] || Icons.Monitor} size={compact ? 12 : 14} />
                    {!compact && <span>{p.label}</span>}
                </button>
            ))}
        </div>
    );
}

// ── Open Window row (for capture tab) ─────────────────────────────────────
function WindowRow({ win, selected, onToggle, onFocus, onSnap, presets }) {
    const [showSnap, setShowSnap] = useState(false);
    return (
        <div className={`win-row ${selected ? 'selected' : ''}`}>
            <label className="win-check-wrap" onClick={e => e.stopPropagation()}>
                <input type="checkbox" checked={selected} onChange={() => onToggle(win.hwnd)} />
                <span className="win-check" />
            </label>
            <div className="win-info" onClick={() => onToggle(win.hwnd)}>
                <div className="win-title">{win.title}</div>
                <div className="win-meta">
                    <span className="win-proc">{win.proc_name}</span>
                    <span className="win-pos">{win.x},{win.y} · {win.w}×{win.h}</span>
                </div>
            </div>
            <div className="win-actions">
                <button className="btn-icon tooltip" data-tip="Focus"
                    onClick={() => onFocus(win.hwnd)}>
                    <Icon icon={Icons.Eye} size={13} />
                </button>
                <button className={`btn-icon tooltip ${showSnap ? 'active' : ''}`}
                    data-tip="Snap" onClick={() => setShowSnap(v => !v)}>
                    <Icon icon={Icons.LayoutGrid} size={13} />
                </button>
            </div>
            {showSnap && (
                <div className="win-snap-popover">
                    <PositionPicker presets={presets} value="" compact
                        onChange={p => { onSnap(win.hwnd, p); setShowSnap(false); }} />
                </div>
            )}
        </div>
    );
}

// ── Workspace entry row (inside workspace detail) ─────────────────────────
function EntryRow({ entry, index, presets, onUpdate, onRemove }) {
    const posLabel = presets.find(p => p.id === entry.position)?.label || entry.position;
    const isCustom = entry.position === 'custom';
    return (
        <div className="entry-row float-in">
            <div className="entry-icon">
                <Icon icon={entry.type === 'vscode' ? Icons.Code2 : entry.type === 'url' ? Icons.Globe : Icons.AppWindow} size={15} />
            </div>
            <div className="entry-info">
                <div className="entry-name">
                    {entry.title_hint || entry.proc_name || entry.path?.split('\\').pop() || 'Unknown'}
                </div>
                <div className="entry-path">{shortPath(entry.path)}</div>
                <div className="entry-pos-label">
                    {isCustom ? `${entry.x},${entry.y} · ${entry.w}×${entry.h}` : posLabel}
                </div>
            </div>
            <div className="entry-actions">
                <select className="entry-pos-select"
                    value={entry.position || 'default'}
                    onChange={e => onUpdate(index, { ...entry, position: e.target.value })}>
                    {presets.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
                </select>
                <button className="btn-icon btn-danger tooltip" data-tip="Remove"
                    onClick={() => onRemove(index)}>
                    <Icon icon={Icons.X} size={13} />
                </button>
            </div>
        </div>
    );
}

// ── Workspace Card ────────────────────────────────────────────────────────
function WorkspaceCard({ ws, onLaunch, onEdit, onDelete, onPin }) {
    const entryCount = ws.entries?.length || 0;
    const types = [...new Set((ws.entries || []).map(e => e.type))];
    return (
        <motion.div className="ws-card float-in"
            initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.12 }} layout>
            <div className="ws-card-left">
                <div className="ws-card-icon" style={ws.color ? { borderColor: ws.color, color: ws.color } : {}}>
                    <Icon icon={Icons.LayoutGrid} size={18} />
                </div>
                <div className="ws-card-info">
                    <div className="ws-card-name">{ws.name}</div>
                    <div className="ws-card-meta">
                        <span>{entryCount} app{entryCount !== 1 ? 's' : ''}</span>
                        {types.includes('vscode') && <span className="ws-badge ws-badge-vscode">VS Code</span>}
                        {types.includes('program') && <span className="ws-badge ws-badge-app">Apps</span>}
                        {types.includes('url') && <span className="ws-badge ws-badge-url">URLs</span>}
                        {ws.pinned && <span className="ws-badge ws-badge-pin"><Icon icon={Icons.Pin} size={8} /> Pinned</span>}
                        {ws.open_count > 0 && <span className="ws-card-count">launched {ws.open_count}×</span>}
                    </div>
                </div>
            </div>
            <div className="ws-card-actions">
                <button className="btn-icon tooltip" data-tip={ws.pinned ? 'Unpin' : 'Pin'}
                    onClick={() => onPin(ws)} style={ws.pinned ? { color: '#eab308' } : {}}>
                    <Icon icon={ws.pinned ? Icons.PinOff : Icons.Pin} size={14} />
                </button>
                <button className="btn-icon tooltip" data-tip="Edit"
                    onClick={() => onEdit(ws)}>
                    <Icon icon={Icons.Pencil} size={14} />
                </button>
                <button className="btn-icon btn-danger tooltip" data-tip="Delete"
                    onClick={() => onDelete(ws)}>
                    <Icon icon={Icons.Trash2} size={14} />
                </button>
                <button className="btn-launch" onClick={() => onLaunch(ws)}>
                    <Icon icon={Icons.Rocket} size={12} /> Launch
                </button>
            </div>
        </motion.div>
    );
}

// ── Edit Workspace Modal ──────────────────────────────────────────────────
function EditModal({ workspace, presets, onClose, onSave }) {
    const isNew = !workspace?.id;
    const [name, setName] = useState(workspace?.name || '');
    const [entries, setEntries] = useState(workspace?.entries || []);

    const updateEntry = (i, e) => setEntries(prev => prev.map((x, j) => j === i ? e : x));
    const removeEntry = (i) => setEntries(prev => prev.filter((_, j) => j !== i));

    const addProgram = () => {
        getBridge(b => {
            Promise.resolve(b.browse_file()).then(path => {
                if (path) {
                    const proc = path.split('\\').pop();
                    setEntries(prev => [...prev, {
                        type: 'program', path, proc_name: proc,
                        title_hint: proc, position: 'default',
                        x: 0, y: 0, w: 0, h: 0,
                    }]);
                }
            });
        });
    };

    const addVscode = () => {
        getBridge(b => {
            Promise.resolve(b.browse_folder()).then(path => {
                if (path) {
                    setEntries(prev => [...prev, {
                        type: 'vscode', path, proc_name: 'Code.exe',
                        title_hint: path.split('\\').pop(), position: 'default',
                        x: 0, y: 0, w: 0, h: 0,
                    }]);
                }
            });
        });
    };

    const addUrl = () => {
        const url = prompt('Enter URL to open:');
        if (url) {
            setEntries(prev => [...prev, {
                type: 'url', path: url, proc_name: '',
                title_hint: url, position: 'default',
                x: 0, y: 0, w: 0, h: 0,
            }]);
        }
    };

    const handleSave = () => {
        if (!name.trim()) return;
        onSave({
            id: workspace?.id,
            name: name.trim(),
            entries,
            pinned: workspace?.pinned || false,
            color: workspace?.color || '',
        });
    };

    return (
        <motion.div className="modal-overlay"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            exit={{ opacity: 0 }} transition={{ duration: 0.15 }}
            onClick={onClose}>
            <motion.div className="modal-content modal-wide"
                initial={{ opacity: 0, scale: 0.95, y: 10 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 10 }}
                transition={{ duration: 0.15 }}
                onClick={e => e.stopPropagation()}>
                <div className="modal-title">
                    {isNew ? 'New Workspace' : 'Edit Workspace'}
                </div>

                <div>
                    <div className="section-label">Name</div>
                    <input className="input-field" placeholder="My Workspace"
                        value={name} onChange={e => setName(e.target.value)} autoFocus />
                </div>

                <div>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div className="section-label" style={{ marginBottom: 0 }}>
                            Programs ({entries.length})
                        </div>
                        <div style={{ display: 'flex', gap: 6 }}>
                            <button className="btn btn-ghost btn-sm" onClick={addProgram}>
                                <Icon icon={Icons.AppWindow} size={11} /> App
                            </button>
                            <button className="btn btn-ghost btn-sm" onClick={addVscode}>
                                <Icon icon={Icons.Code2} size={11} /> VS Code
                            </button>
                            <button className="btn btn-ghost btn-sm" onClick={addUrl}>
                                <Icon icon={Icons.Globe} size={11} /> URL
                            </button>
                        </div>
                    </div>
                    <div className="entry-list">
                        {entries.length === 0 ? (
                            <div className="entry-empty">
                                No programs yet — add apps, VS Code folders, or URLs above
                            </div>
                        ) : entries.map((e, i) => (
                            <EntryRow key={i} entry={e} index={i} presets={presets}
                                onUpdate={updateEntry} onRemove={removeEntry} />
                        ))}
                    </div>
                </div>

                <div className="modal-actions">
                    <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
                    <button className="btn btn-primary" onClick={handleSave}
                        disabled={!name.trim() || entries.length === 0}>
                        <Icon icon={Icons.Check} size={12} />
                        {isNew ? 'Create Workspace' : 'Save Changes'}
                    </button>
                </div>
            </motion.div>
        </motion.div>
    );
}

// ── Capture Modal (name the captured workspace) ───────────────────────────
function CaptureModal({ selectedWindows, windows, onClose, onCapture }) {
    const [name, setName] = useState('');
    const selected = windows.filter(w => selectedWindows.has(w.hwnd));

    return (
        <motion.div className="modal-overlay"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            exit={{ opacity: 0 }} transition={{ duration: 0.15 }}
            onClick={onClose}>
            <motion.div className="modal-content"
                initial={{ opacity: 0, scale: 0.95, y: 10 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 10 }}
                transition={{ duration: 0.15 }}
                onClick={e => e.stopPropagation()}>
                <div className="modal-title">Save as Workspace</div>
                <div className="section-label">
                    {selected.length} window{selected.length !== 1 ? 's' : ''} selected
                </div>
                <div className="capture-preview">
                    {selected.map(w => (
                        <div key={w.hwnd} className="capture-item">
                            <Icon icon={Icons.AppWindow} size={12} />
                            <span>{w.title.slice(0, 50)}</span>
                            <span className="capture-pos">{w.x},{w.y} · {w.w}×{w.h}</span>
                        </div>
                    ))}
                </div>
                <div className="section-label">Workspace Name</div>
                <input className="input-field" placeholder="My Desktop Layout"
                    value={name} onChange={e => setName(e.target.value)} autoFocus
                    onKeyDown={e => e.key === 'Enter' && name.trim() && onCapture(name.trim())} />
                <div className="modal-actions">
                    <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
                    <button className="btn btn-primary" onClick={() => onCapture(name.trim())}
                        disabled={!name.trim()}>
                        <Icon icon={Icons.Save} size={12} /> Save Workspace
                    </button>
                </div>
            </motion.div>
        </motion.div>
    );
}

// ══════════════════════════════════════════════════════════════════════════
// ── MAIN APP ──────────────────────────────────────────────────────────────
// ══════════════════════════════════════════════════════════════════════════
function App() {
    const [tab, setTab] = useState('workspaces');
    const [workspaces, setWorkspaces] = useState([]);
    const [windows, setWindows] = useState([]);
    const [selectedWins, setSelectedWins] = useState(new Set());
    const [recentEntries, setRecentEntries] = useState([]);
    const [search, setSearch] = useState('');
    const [presets, setPresets] = useState([]);
    const [editModal, setEditModal] = useState(null);
    const [captureModal, setCaptureModal] = useState(false);
    const [status, flash] = useStatus();
    const [loading, setLoading] = useState(true);
    const searchRef = useRef(null);

    // ── Init ──────────────────────────────────────────────────────────────
    useEffect(() => {
        getBridge(b => {
            Promise.all([
                Promise.resolve(b.get_workspaces()),
                Promise.resolve(b.get_position_presets()),
            ]).then(([wsJson, presetsJson]) => {
                setWorkspaces(JSON.parse(wsJson));
                setPresets(JSON.parse(presetsJson));
                setLoading(false);
            });
            // Connect signal for live window refresh
            b.windows_refreshed.connect(json => setWindows(JSON.parse(json)));
        });
    }, []);

    // Refresh windows when switching to that tab
    useEffect(() => {
        if (tab === 'windows') {
            getBridge(b => {
                Promise.resolve(b.list_windows_sync()).then(json => setWindows(JSON.parse(json)));
            });
        }
        if (tab === 'recent' && recentEntries.length === 0) {
            getBridge(b => {
                Promise.resolve(b.scan_vscode_recent()).then(json => setRecentEntries(JSON.parse(json)));
            });
        }
    }, [tab]);

    // Keyboard shortcuts
    useEffect(() => {
        const h = (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'f') { e.preventDefault(); searchRef.current?.focus(); }
            if (e.key === 'Escape') { setEditModal(null); setCaptureModal(false); }
        };
        document.addEventListener('keydown', h);
        return () => document.removeEventListener('keydown', h);
    }, []);

    // ── Refresh helpers ───────────────────────────────────────────────────
    const refreshWorkspaces = useCallback(() => {
        getBridge(b => Promise.resolve(b.get_workspaces()).then(j => setWorkspaces(JSON.parse(j))));
    }, []);

    const refreshWindows = useCallback(() => {
        getBridge(b => Promise.resolve(b.list_windows_sync()).then(j => setWindows(JSON.parse(j))));
    }, []);

    // ── Workspace actions ─────────────────────────────────────────────────
    const handleLaunch = useCallback((ws) => {
        getBridge(b => {
            Promise.resolve(b.launch_workspace(ws.id)).then(json => {
                const r = JSON.parse(json);
                if (r.error) flash(r.error, 'error');
                else { flash(`Launched ${ws.name} (${r.launched} apps)`, 'success'); refreshWorkspaces(); }
            });
        });
    }, [flash, refreshWorkspaces]);

    const handleDelete = useCallback((ws) => {
        getBridge(b => {
            Promise.resolve(b.delete_workspace(ws.id)).then(() => {
                refreshWorkspaces(); flash(`Deleted ${ws.name}`, 'info');
            });
        });
    }, [flash, refreshWorkspaces]);

    const handlePin = useCallback((ws) => {
        getBridge(b => {
            b.toggle_pin(ws.id, !ws.pinned);
            refreshWorkspaces();
            flash(ws.pinned ? 'Unpinned' : 'Pinned', 'info');
        });
    }, [flash, refreshWorkspaces]);

    const handleSaveWorkspace = useCallback((data) => {
        getBridge(b => {
            Promise.resolve(b.save_workspace(JSON.stringify(data))).then(json => {
                const r = JSON.parse(json);
                if (r.error) flash(r.error, 'error');
                else { refreshWorkspaces(); flash(`Saved ${r.name}`, 'success'); setEditModal(null); }
            });
        });
    }, [flash, refreshWorkspaces]);

    // ── Window actions ────────────────────────────────────────────────────
    const toggleWin = useCallback((hwnd) => {
        setSelectedWins(prev => {
            const next = new Set(prev);
            next.has(hwnd) ? next.delete(hwnd) : next.add(hwnd);
            return next;
        });
    }, []);

    const handleFocus = useCallback((hwnd) => {
        getBridge(b => b.focus_window(hwnd));
    }, []);

    const handleSnap = useCallback((hwnd, preset) => {
        getBridge(b => { b.snap_window(hwnd, preset); setTimeout(refreshWindows, 400); });
    }, [refreshWindows]);

    const selectAllWins = useCallback(() => {
        setSelectedWins(new Set(windows.map(w => w.hwnd)));
    }, [windows]);

    const handleCapture = useCallback((name) => {
        const hwnds = [...selectedWins];
        getBridge(b => {
            Promise.resolve(b.capture_windows(JSON.stringify({ name, hwnds }))).then(json => {
                const r = JSON.parse(json);
                if (r.error) flash(r.error, 'error');
                else {
                    flash(`Created workspace "${r.name}" with ${r.entries?.length || 0} apps`, 'success');
                    refreshWorkspaces();
                    setCaptureModal(false);
                    setSelectedWins(new Set());
                    setTab('workspaces');
                }
            });
        });
    }, [selectedWins, flash, refreshWorkspaces]);

    // ── VS Code recent: quick-add as single-entry workspace ───────────────
    const handleAddRecent = useCallback((entry) => {
        const data = {
            name: entry.name,
            entries: [{
                type: 'vscode', path: entry.path,
                proc_name: 'Code.exe', title_hint: entry.name,
                position: 'default', x: 0, y: 0, w: 0, h: 0,
            }],
        };
        getBridge(b => {
            Promise.resolve(b.save_workspace(JSON.stringify(data))).then(json => {
                const r = JSON.parse(json);
                if (r.error) flash(r.error, 'error');
                else { refreshWorkspaces(); flash(`Added ${entry.name}`, 'success'); }
            });
        });
    }, [flash, refreshWorkspaces]);

    // ── Filtering ─────────────────────────────────────────────────────────
    const q = search.toLowerCase();
    const filteredWs = useMemo(() => {
        let list = workspaces.filter(ws => !q || ws.name.toLowerCase().includes(q));
        list.sort((a, b) => {
            if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
            return (b.last_opened || 0) - (a.last_opened || 0);
        });
        return list;
    }, [workspaces, q]);

    const filteredWins = useMemo(() =>
        windows.filter(w => !q || w.title.toLowerCase().includes(q) || w.proc_name.toLowerCase().includes(q)),
    [windows, q]);

    const filteredRecent = useMemo(() =>
        recentEntries.filter(e => !q || e.name.toLowerCase().includes(q) || e.path.toLowerCase().includes(q)),
    [recentEntries, q]);

    const savedPaths = new Set(workspaces.flatMap(ws => (ws.entries || []).map(e => e.path)));

    // ══════════════════════════════════════════════════════════════════════
    return (
        <div className="app-shell">
            {/* Header */}
            <div className="app-header">
                <div className="app-header-icon">
                    <Icon icon={Icons.LayoutGrid} size={16} />
                </div>
                <div>
                    <div className="app-header-title">Workspace Manager</div>
                    <div className="app-header-sub">capture · organize · launch desktop layouts</div>
                </div>
                <div className="app-header-right">
                    <button className="btn btn-primary"
                        onClick={() => setEditModal({ mode: 'new', workspace: {} })}>
                        <Icon icon={Icons.Plus} size={12} /> New
                    </button>
                </div>
            </div>

            {/* Search */}
            <div className="search-wrap">
                <div className="search-icon-wrap">
                    <span className="search-icon"><Icon icon={Icons.Search} size={14} /></span>
                    <input ref={searchRef} className="search-field"
                        placeholder="Search…  (Ctrl+F)" value={search}
                        onChange={e => setSearch(e.target.value)} spellCheck={false} />
                </div>
            </div>

            {/* Tabs */}
            <div className="tab-bar">
                {[
                    ['workspaces', Icons.LayoutGrid, 'Workspaces', workspaces.length],
                    ['windows', Icons.AppWindow, 'Open Windows', null],
                    ['recent', Icons.Clock, 'VS Code Recent', null],
                ].map(([id, icon, label, count]) => (
                    <button key={id} className={`tab-btn ${tab === id ? 'active' : ''}`}
                        onClick={() => setTab(id)}>
                        <Icon icon={icon} size={11} style={{ display: 'inline', marginRight: 5, verticalAlign: 'middle' }} />
                        {label}
                        {count > 0 && <span style={{ marginLeft: 6, opacity: 0.5 }}>{count}</span>}
                    </button>
                ))}
            </div>

            {/* Content */}
            <AnimatePresence mode="wait">
                {/* ── TAB: Workspaces ────────────────────────────────────── */}
                {tab === 'workspaces' && (
                    <motion.div key="ws" className="content-area"
                        initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.14 }}>
                        {loading ? (
                            <div className="empty-state">
                                <div className="empty-state-icon">
                                    <Icon icon={Icons.Loader2} size={22} style={{ animation: 'spin 1s linear infinite' }} />
                                </div>
                                <div className="empty-state-title">Loading…</div>
                            </div>
                        ) : filteredWs.length === 0 ? (
                            <div className="empty-state">
                                <div className="empty-state-icon">
                                    <Icon icon={workspaces.length ? Icons.SearchX : Icons.LayoutGrid} size={22} />
                                </div>
                                <div className="empty-state-title">
                                    {workspaces.length ? 'No matches' : 'No workspaces yet'}
                                </div>
                                <div className="empty-state-hint">
                                    {workspaces.length
                                        ? `Nothing matches "${search}"`
                                        : 'Capture your current window layout or add programs manually.'
                                    }
                                </div>
                                {!workspaces.length && (
                                    <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                                        <button className="btn btn-primary"
                                            onClick={() => setTab('windows')}>
                                            <Icon icon={Icons.AppWindow} size={12} /> Capture Windows
                                        </button>
                                        <button className="btn btn-ghost"
                                            onClick={() => setEditModal({ mode: 'new', workspace: {} })}>
                                            <Icon icon={Icons.Plus} size={12} /> Manual
                                        </button>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <AnimatePresence>
                                {filteredWs.map(ws => (
                                    <WorkspaceCard key={ws.id} ws={ws}
                                        onLaunch={handleLaunch}
                                        onEdit={(w) => setEditModal({ mode: 'edit', workspace: w })}
                                        onDelete={handleDelete}
                                        onPin={handlePin} />
                                ))}
                            </AnimatePresence>
                        )}
                    </motion.div>
                )}

                {/* ── TAB: Open Windows ──────────────────────────────────── */}
                {tab === 'windows' && (
                    <motion.div key="win" className="content-area"
                        initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.14 }}>

                        <div className="windows-toolbar">
                            <span className="section-label" style={{ marginBottom: 0 }}>
                                {filteredWins.length} window{filteredWins.length !== 1 ? 's' : ''}
                                {selectedWins.size > 0 && ` · ${selectedWins.size} selected`}
                            </span>
                            <div style={{ display: 'flex', gap: 6 }}>
                                <button className="btn btn-ghost btn-sm" onClick={refreshWindows}>
                                    <Icon icon={Icons.RefreshCw} size={11} /> Refresh
                                </button>
                                <button className="btn btn-ghost btn-sm" onClick={selectAllWins}>
                                    <Icon icon={Icons.CheckSquare} size={11} /> All
                                </button>
                                {selectedWins.size > 0 && (
                                    <button className="btn btn-primary btn-sm"
                                        onClick={() => setCaptureModal(true)}>
                                        <Icon icon={Icons.Save} size={11} /> Capture {selectedWins.size}
                                    </button>
                                )}
                            </div>
                        </div>

                        {filteredWins.length === 0 ? (
                            <div className="empty-state">
                                <div className="empty-state-icon"><Icon icon={Icons.AppWindow} size={22} /></div>
                                <div className="empty-state-title">No windows found</div>
                            </div>
                        ) : filteredWins.map(w => (
                            <WindowRow key={w.hwnd} win={w}
                                selected={selectedWins.has(w.hwnd)}
                                onToggle={toggleWin}
                                onFocus={handleFocus}
                                onSnap={handleSnap}
                                presets={presets} />
                        ))}
                    </motion.div>
                )}

                {/* ── TAB: VS Code Recent ────────────────────────────────── */}
                {tab === 'recent' && (
                    <motion.div key="recent" className="content-area"
                        initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.14 }}>
                        {filteredRecent.length === 0 ? (
                            <div className="empty-state">
                                <div className="empty-state-icon"><Icon icon={Icons.Clock} size={22} /></div>
                                <div className="empty-state-title">
                                    {recentEntries.length ? 'No matches' : 'Scanning VS Code…'}
                                </div>
                            </div>
                        ) : filteredRecent.map((entry) => (
                            <div key={entry.path} className={`ws-card float-in ${!entry.exists ? 'ws-card-missing' : ''}`}>
                                <div className="ws-card-left">
                                    <div className="ws-card-icon" style={{ borderColor: '#3b82f6', color: '#3b82f6' }}>
                                        <Icon icon={Icons.Code2} size={18} />
                                    </div>
                                    <div className="ws-card-info">
                                        <div className="ws-card-name">{entry.name}</div>
                                        <div className="ws-card-path">{entry.path}</div>
                                    </div>
                                </div>
                                <div className="ws-card-actions">
                                    {!savedPaths.has(entry.path) ? (
                                        <button className="btn btn-ghost btn-sm" onClick={() => handleAddRecent(entry)}>
                                            <Icon icon={Icons.Plus} size={11} /> Save
                                        </button>
                                    ) : (
                                        <span className="saved-badge">✓ Saved</span>
                                    )}
                                </div>
                            </div>
                        ))}
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Status bar */}
            <div className="status-bar">
                <span className={`status-text ${status?.type || ''}`}>
                    {status?.msg || `${workspaces.length} workspace${workspaces.length !== 1 ? 's' : ''}`}
                </span>
                <span className="status-text" style={{ opacity: 0.5 }}>Ctrl+F search</span>
            </div>

            {/* Modals */}
            <AnimatePresence>
                {editModal && (
                    <EditModal workspace={editModal.workspace} presets={presets}
                        onClose={() => setEditModal(null)} onSave={handleSaveWorkspace} />
                )}
                {captureModal && (
                    <CaptureModal selectedWindows={selectedWins} windows={windows}
                        onClose={() => setCaptureModal(false)} onCapture={handleCapture} />
                )}
            </AnimatePresence>
        </div>
    );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(React.createElement(App));
