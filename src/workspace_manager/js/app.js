// Workspace Manager — React app (v2)

const { useState, useEffect, useCallback, useRef, useMemo } = React;
const { motion, AnimatePresence } = window.Motion;
const Icons = window.lucide;

// ── Icon wrapper ────────────────────────────────────────────────────────────
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

// ── Bridge ──────────────────────────────────────────────────────────────────
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
    setTimeout(() => {
        _bridge = {
            get_workspaces: () => JSON.stringify([]),
            save_workspace: j => { const d = JSON.parse(j); d.id = Date.now(); return JSON.stringify(d); },
            delete_workspace: () => JSON.stringify({ deleted: true }),
            launch_workspace: () => JSON.stringify({ ok: true, launched: 2 }),
            toggle_pin: () => {},
            list_windows_sync: () => JSON.stringify([
                { hwnd: 1, title: 'fast-explorer — Visual Studio Code', pid: 100, proc_name: 'Code.exe', exec_path: 'C:\\Code\\Code.exe', x: 0, y: 0, w: 960, h: 1080 },
                { hwnd: 2, title: 'Google Chrome', pid: 200, proc_name: 'chrome.exe', exec_path: 'C:\\Chrome\\chrome.exe', x: 960, y: 0, w: 960, h: 1080 },
            ]),
            refresh_windows: () => {},
            snap_window: () => {}, focus_window: () => {},
            minimize_window: () => {}, maximize_window: () => {}, close_window: () => {},
            capture_windows: j => { const d = JSON.parse(j); d.id = Date.now(); d.entries = []; return JSON.stringify(d); },
            get_installed_apps: () => JSON.stringify([
                { name: 'Visual Studio Code', path: 'C:\\...\\Visual Studio Code.lnk' },
                { name: 'Google Chrome', path: 'C:\\...\\Google Chrome.lnk' },
                { name: 'Discord', path: 'C:\\...\\Discord.lnk' },
                { name: 'Obsidian', path: 'C:\\...\\Obsidian.lnk' },
            ]),
            browse_folder: () => 'C:\\Projects\\my-project',
            browse_file: () => 'C:\\Program Files\\app.exe',
            get_screen_info: () => JSON.stringify({ width: 1920, height: 1080 }),
            get_position_presets: () => JSON.stringify([
                { id: 'default',    label: 'Default',    icon: 'Monitor' },
                { id: 'left_half',  label: 'Left Half',  icon: 'PanelLeft' },
                { id: 'right_half', label: 'Right Half', icon: 'PanelRight' },
                { id: 'top_half',   label: 'Top Half',   icon: 'PanelTop' },
                { id: 'bottom_half',label: 'Bot Half',   icon: 'PanelBottom' },
                { id: 'fullscreen', label: 'Full',       icon: 'Maximize2' },
                { id: 'top_left',   label: 'Top-Left',   icon: 'ArrowUpLeft' },
                { id: 'top_right',  label: 'Top-Right',  icon: 'ArrowUpRight' },
                { id: 'bot_left',   label: 'Bot-Left',   icon: 'ArrowDownLeft' },
                { id: 'bot_right',  label: 'Bot-Right',  icon: 'ArrowDownRight' },
            ]),
            get_monitors: () => JSON.stringify([{ index: 0, x: 0, y: 0, w: 1920, h: 1080, primary: true }]),
            duplicate_workspace: _id => JSON.stringify({ id: Date.now(), name: 'Copy', entries: [], pinned: false, color: '', last_opened: null, open_count: 0 }),
            export_workspace: _id => JSON.stringify({ ok: true }),
            import_workspace: () => JSON.stringify({ id: Date.now(), name: 'Imported Workspace', entries: [], pinned: false, color: '' }),
            save_all_windows: name => JSON.stringify({ id: Date.now(), name, entries: [], pinned: false, color: '' }),
            snap_window_on: () => {},
            windows_refreshed: { connect: () => {} },
        };
        _bridgeReady = true;
        _cbs.forEach(fn => fn(_bridge));
        _cbs.length = 0;
    }, 50);
}

// ── Icon map ────────────────────────────────────────────────────────────────
const IMAP = {
    Monitor: Icons.Monitor, PanelLeft: Icons.PanelLeft, PanelRight: Icons.PanelRight,
    PanelTop: Icons.PanelTop, PanelBottom: Icons.PanelBottom,
    ArrowUpLeft: Icons.ArrowUpLeft, ArrowUpRight: Icons.ArrowUpRight,
    ArrowDownLeft: Icons.ArrowDownLeft, ArrowDownRight: Icons.ArrowDownRight,
    Maximize2: Icons.Maximize2,
};

// ── IDE registry ─────────────────────────────────────────────────────────────
const IDES = [
    { key: 'vscode',         label: 'VS Code',         icon: Icons.Code2 },
    { key: 'cursor',         label: 'Cursor',          icon: Icons.Crosshair },
    { key: 'windsurf',       label: 'Windsurf',        icon: Icons.Wind },
    { key: 'zed',            label: 'Zed',             icon: Icons.Zap },
    { key: 'intellij',       label: 'IntelliJ IDEA',   icon: Icons.Coffee },
    { key: 'pycharm',        label: 'PyCharm',         icon: Icons.Cpu },
    { key: 'webstorm',       label: 'WebStorm',        icon: Icons.Globe },
    { key: 'clion',          label: 'CLion',           icon: Icons.Cpu },
    { key: 'rider',          label: 'Rider',           icon: Icons.Code2 },
    { key: 'goland',         label: 'GoLand',          icon: Icons.Code2 },
    { key: 'android_studio', label: 'Android Studio',  icon: Icons.Smartphone },
    { key: 'rubymine',       label: 'RubyMine',        icon: Icons.Code2 },
    { key: 'datagrip',       label: 'DataGrip',        icon: Icons.Database },
    { key: 'sublime',        label: 'Sublime Text',    icon: Icons.Layers },
    { key: 'nvim',           label: 'Neovim',          icon: Icons.Terminal },
];
const IDE_BY_KEY = Object.fromEntries(IDES.map(i => [i.key, i]));

// ── useStatus ───────────────────────────────────────────────────────────────
function useStatus() {
    const [s, setS] = useState(null);
    const t = useRef(null);
    const flash = useCallback((msg, type = 'info') => {
        clearTimeout(t.current);
        setS({ msg, type });
        t.current = setTimeout(() => setS(null), 3200);
    }, []);
    return [s, flash];
}

// ── PositionStrip — row of preset buttons ───────────────────────────────────
function PositionStrip({ presets, value, onChange }) {
    return (
        <div className="pos-strip">
            {presets.filter(p => p.id !== 'custom').map(p => (
                <button key={p.id} title={p.label}
                    className={`pos-chip ${value === p.id ? 'active' : ''}`}
                    onClick={() => onChange(p.id)}>
                    <Icon icon={IMAP[p.icon] || Icons.Monitor} size={12} />
                </button>
            ))}
        </div>
    );
}

// ══════════════════════════════════════════════════════════════════════════════
// ── APP PICKER MODAL ──────────────────────────────────────────────────────────
// ══════════════════════════════════════════════════════════════════════════════
function AppPickerModal({ onPick, onClose }) {
    const [apps, setApps] = useState(null);
    const [q, setQ] = useState('');
    const [urlInput, setUrlInput] = useState('');
    const [mode, setMode] = useState('apps'); // 'apps' | 'ide' | 'url'
    const [pendingIde, setPendingIde] = useState(null); // ide key chosen, awaiting folder
    const searchRef = useRef(null);

    useEffect(() => {
        getBridge(b => {
            Promise.resolve(b.get_installed_apps()).then(json => setApps(JSON.parse(json)));
        });
        setTimeout(() => searchRef.current?.focus(), 80);
    }, []);

    const filtered = useMemo(() => {
        if (!apps) return [];
        const lq = q.toLowerCase();
        return !lq ? apps : apps.filter(a => a.name.toLowerCase().includes(lq));
    }, [apps, q]);

    const pick = (type, name, path, extra = {}) => onPick({ type, name, path, ...extra });

    const browseExe = () => {
        getBridge(b => {
            Promise.resolve(b.browse_file()).then(path => {
                if (path) pick('program', path.split('\\').pop().replace(/\.[^.]+$/, ''), path);
            });
        });
    };

    const browseIdeFolder = (ideKey) => {
        getBridge(b => {
            Promise.resolve(b.browse_folder()).then(path => {
                if (!path) return;
                const folderName = path.split('\\').pop() || path.split('/').pop();
                const ideLabel = IDE_BY_KEY[ideKey]?.label || ideKey;
                pick('ide', `${folderName} — ${ideLabel}`, path, { ide: ideKey });
            });
        });
    };

    const submitUrl = () => {
        const u = urlInput.trim();
        if (!u) return;
        pick('url', u, u);
    };

    const TABS = [
        { id: 'apps', label: 'Apps' },
        { id: 'ide',  label: 'Open in IDE' },
        { id: 'url',  label: 'URL' },
    ];

    return (
        <motion.div className="modal-overlay"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            exit={{ opacity: 0 }} transition={{ duration: 0.12 }}
            onClick={onClose}>
            <motion.div className="picker-panel"
                initial={{ opacity: 0, scale: 0.97, y: 8 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.97, y: 8 }}
                transition={{ duration: 0.13 }}
                onClick={e => e.stopPropagation()}>

                {/* Header */}
                <div className="picker-header">
                    <span className="picker-title">
                        <Icon icon={Icons.Plus} size={14} /> Add App
                    </span>
                    <div className="picker-tab-row">
                        {TABS.map(t => (
                            <button key={t.id} className={`picker-tab ${mode === t.id ? 'active' : ''}`}
                                onClick={() => setMode(t.id)}>
                                {t.label}
                            </button>
                        ))}
                    </div>
                </div>

                {/* ── Installed Apps ───────────────────────────────── */}
                {mode === 'apps' && (
                    <>
                        <div className="picker-search-wrap">
                            <Icon icon={Icons.Search} size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-disabled)', pointerEvents: 'none' }} />
                            <input ref={searchRef} className="picker-search"
                                placeholder="Search apps…"
                                value={q} onChange={e => setQ(e.target.value)}
                                autoFocus spellCheck={false} />
                        </div>
                        <div className="picker-list">
                            {apps === null ? (
                                <div className="picker-empty">
                                    <Icon icon={Icons.Loader2} size={18} style={{ animation: 'spin 1s linear infinite' }} />
                                    <span>Loading apps…</span>
                                </div>
                            ) : filtered.length === 0 ? (
                                <div className="picker-empty">
                                    <Icon icon={Icons.SearchX} size={18} />
                                    <span>No match for "{q}"</span>
                                </div>
                            ) : filtered.map((a, i) => (
                                <button key={i} className="picker-app-row"
                                    onClick={() => pick('program', a.name, a.path)}>
                                    <span className="picker-app-icon">
                                        <Icon icon={Icons.AppWindow} size={15} />
                                    </span>
                                    <span className="picker-app-name">{a.name}</span>
                                    <Icon icon={Icons.ChevronRight} size={12} style={{ color: 'var(--text-disabled)', flexShrink: 0 }} />
                                </button>
                            ))}
                        </div>
                        <div className="picker-footer">
                            <button className="picker-action" onClick={browseExe}>
                                <Icon icon={Icons.FolderOpen} size={14} />
                                Browse .exe / file…
                            </button>
                        </div>
                    </>
                )}

                {/* ── Open in IDE ──────────────────────────────────── */}
                {mode === 'ide' && (
                    <div className="picker-ide-grid">
                        <div className="picker-ide-hint">Pick an editor, then choose a folder</div>
                        {IDES.map(ide => (
                            <button key={ide.key} className="picker-ide-btn"
                                onClick={() => browseIdeFolder(ide.key)}>
                                <span className="picker-ide-icon">
                                    <Icon icon={ide.icon} size={16} />
                                </span>
                                <span className="picker-ide-label">{ide.label}</span>
                                <Icon icon={Icons.FolderOpen} size={12} style={{ color: 'var(--text-disabled)', marginLeft: 'auto' }} />
                            </button>
                        ))}
                    </div>
                )}

                {/* ── URL ─────────────────────────────────────────── */}
                {mode === 'url' && (
                    <div className="picker-url-section">
                        <div className="section-label">URL to open</div>
                        <input className="input-field" placeholder="https://…"
                            value={urlInput} onChange={e => setUrlInput(e.target.value)}
                            autoFocus
                            onKeyDown={e => { if (e.key === 'Enter') submitUrl(); }} />
                        <div style={{ marginTop: 8 }}>
                            <button className="btn btn-primary" onClick={submitUrl} disabled={!urlInput.trim()}>
                                <Icon icon={Icons.Plus} size={12} /> Add URL
                            </button>
                        </div>
                    </div>
                )}
            </motion.div>
        </motion.div>
    );
}

// ══════════════════════════════════════════════════════════════════════════════
// ── ENTRY ROW (inside workspace editor) ──────────────────────────────────────
// ══════════════════════════════════════════════════════════════════════════════
function EntryRow({ entry, index, presets, monitors, onUpdate, onRemove, onMoveEntry }) {
    const [showAdv, setShowAdv] = useState(false);
    const cardRef = useRef(null);

    const typeIcon = entry.type === 'ide'
        ? (IDE_BY_KEY[entry.ide]?.icon || Icons.Code2)
        : entry.type === 'vscode' ? Icons.Code2
        : entry.type === 'url' ? Icons.Globe
        : Icons.AppWindow;
    const displayName = entry.title_hint || entry.proc_name || entry.path?.split('\\').pop() || 'Unknown';

    // ── drag-and-drop ────────────────────────────────────────────────────────
    const handleDragStart = (e) => {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', String(index));
        setTimeout(() => cardRef.current?.classList.add('dragging'), 0);
    };
    const handleDragEnd = () => {
        cardRef.current?.classList.remove('dragging');
        cardRef.current?.removeAttribute('data-dragover');
    };
    const handleDragOver = (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        cardRef.current?.setAttribute('data-dragover', '1');
    };
    const handleDragLeave = (e) => {
        if (!cardRef.current?.contains(e.relatedTarget))
            cardRef.current?.removeAttribute('data-dragover');
    };
    const handleDrop = (e) => {
        e.preventDefault();
        cardRef.current?.removeAttribute('data-dragover');
        const from = parseInt(e.dataTransfer.getData('text/plain'), 10);
        if (!isNaN(from) && from !== index) onMoveEntry(from, index);
    };

    return (
        <div ref={cardRef} className="entry-card float-in" draggable
            onDragStart={handleDragStart} onDragEnd={handleDragEnd}
            onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}>
            <div className="entry-card-top">
                <span className="entry-drag-handle">
                    <Icon icon={Icons.GripVertical} size={14} />
                </span>
                <span className="entry-type-icon">
                    <Icon icon={typeIcon} size={14} />
                </span>
                <div className="entry-names">
                    <div className="entry-name">{displayName}</div>
                    {entry.path && entry.path !== displayName && (
                        <div className="entry-path">{entry.path.length > 60 ? '…' + entry.path.slice(-58) : entry.path}</div>
                    )}
                </div>
                <button className={`btn-icon ${showAdv ? 'active' : ''}`}
                    onClick={() => setShowAdv(v => !v)} title="Advanced options">
                    <Icon icon={Icons.Settings2} size={13} />
                </button>
                <button className="btn-icon btn-danger" onClick={() => onRemove(index)} title="Remove">
                    <Icon icon={Icons.Trash2} size={13} />
                </button>
            </div>
            <div className="entry-card-bot">
                <span className="entry-pos-label">Position:</span>
                <PositionStrip presets={presets} value={entry.position || 'default'}
                    onChange={pos => onUpdate(index, { ...entry, position: pos })} />
            </div>
            {showAdv && (
                <div className="entry-adv">
                    {monitors && monitors.length > 1 && (
                        <label className="adv-field">
                            <span>Monitor</span>
                            <select className="adv-select"
                                value={entry.monitor ?? 0}
                                onChange={e => onUpdate(index, { ...entry, monitor: parseInt(e.target.value) })}>
                                {monitors.map(m => (
                                    <option key={m.index} value={m.index}>
                                        {`Monitor ${m.index + 1}${m.primary ? ' (primary)' : ''}  ${m.w}×${m.h}`}
                                    </option>
                                ))}
                            </select>
                        </label>
                    )}
                    <label className="adv-field">
                        <span>Window wait (s)</span>
                        <input type="number" className="adv-num" min="0" max="30" step="0.5"
                            value={entry.window_wait ?? 1.8}
                            onChange={e => onUpdate(index, { ...entry, window_wait: parseFloat(e.target.value) || 1.8 })} />
                    </label>
                    <label className="adv-field">
                        <span>Launch delay (s)</span>
                        <input type="number" className="adv-num" min="0" max="30" step="0.5"
                            value={entry.launch_delay ?? 0.3}
                            onChange={e => onUpdate(index, { ...entry, launch_delay: parseFloat(e.target.value) || 0.3 })} />
                    </label>
                    <label className="adv-field adv-field-check">
                        <span>Kill if running</span>
                        <input type="checkbox"
                            checked={!!entry.close_existing}
                            onChange={e => onUpdate(index, { ...entry, close_existing: e.target.checked })} />
                    </label>
                </div>
            )}
        </div>
    );
}

// ══════════════════════════════════════════════════════════════════════════════
// ── WORKSPACE EDITOR ─────────────────────────────────────────────────────────
// ══════════════════════════════════════════════════════════════════════════════
function WorkspaceEditor({ workspace, presets, monitors, onClose, onSave }) {
    const isNew = !workspace?.id;
    const [name, setName] = useState(workspace?.name || '');
    const [entries, setEntries] = useState(workspace?.entries ? [...workspace.entries] : []);
    const [showPicker, setShowPicker] = useState(false);
    const nameRef = useRef(null);

    useEffect(() => { setTimeout(() => nameRef.current?.focus(), 60); }, []);

    const updateEntry = (i, e) => setEntries(prev => prev.map((x, j) => j === i ? e : x));
    const removeEntry = (i) => setEntries(prev => prev.filter((_, j) => j !== i));
    const moveEntry   = useCallback((from, to) => {
        setEntries(prev => {
            const next = [...prev];
            const [moved] = next.splice(from, 1);
            next.splice(to, 0, moved);
            return next;
        });
    }, []);

    const handlePick = ({ type, name: appName, path, ide }) => {
        setShowPicker(false);
        const isIde   = type === 'ide' || type === 'vscode';
        const isUrl   = type === 'url';
        setEntries(prev => [...prev, {
            type: isIde ? 'ide' : type,
            ide:  isIde ? (ide || 'vscode') : undefined,
            path,
            proc_name: isUrl ? '' : (path?.split('\\').pop() || ''),
            title_hint: appName,
            position: 'default',
            x: 0, y: 0, w: 0, h: 0,
        }]);
    };

    const handleSave = () => {
        if (!name.trim() || entries.length === 0) return;
        onSave({ id: workspace?.id, name: name.trim(), entries, pinned: workspace?.pinned || false, color: workspace?.color || '' });
    };

    return (
        <motion.div className="editor-overlay"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
            <motion.div className="editor-panel"
                initial={{ x: 40, opacity: 0 }} animate={{ x: 0, opacity: 1 }}
                exit={{ x: 40, opacity: 0 }} transition={{ duration: 0.18, ease: 'easeOut' }}>

                {/* Editor header */}
                <div className="editor-header">
                    <button className="btn-icon" onClick={onClose} title="Back">
                        <Icon icon={Icons.ArrowLeft} size={15} />
                    </button>
                    <span className="editor-title">{isNew ? 'New Workspace' : `Edit: ${workspace.name}`}</span>
                    <button className="btn btn-primary btn-sm" onClick={handleSave}
                        disabled={!name.trim() || entries.length === 0}>
                        <Icon icon={Icons.Check} size={12} />
                        {isNew ? 'Create' : 'Save'}
                    </button>
                </div>

                {/* Name */}
                <div className="editor-section">
                    <div className="section-label">Workspace Name</div>
                    <input ref={nameRef} className="input-field" placeholder="e.g. Dev Setup"
                        value={name} onChange={e => setName(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && document.activeElement.blur()} />
                </div>

                {/* Apps */}
                <div className="editor-section editor-apps-section">
                    <div className="editor-apps-header">
                        <div className="section-label" style={{ margin: 0 }}>
                            Apps
                            {entries.length > 0 && <span className="entry-count">{entries.length}</span>}
                        </div>
                        <button className="btn btn-ghost btn-sm" onClick={() => setShowPicker(true)}>
                            <Icon icon={Icons.Plus} size={12} /> Add App
                        </button>
                    </div>

                    {entries.length === 0 ? (
                        <button className="entry-add-cta" onClick={() => setShowPicker(true)}>
                            <Icon icon={Icons.Plus} size={16} />
                            <span>Add your first app</span>
                            <span className="entry-add-hint">apps, VS Code projects, URLs</span>
                        </button>
                    ) : (
                        <div className="entry-list">
                            {entries.map((e, i) => (
                                <EntryRow key={i} entry={e} index={i} presets={presets} monitors={monitors || []}
                                    onUpdate={updateEntry} onRemove={removeEntry} onMoveEntry={moveEntry} />
                            ))}
                            <button className="entry-add-more" onClick={() => setShowPicker(true)}>
                                <Icon icon={Icons.Plus} size={12} /> Add another app
                            </button>
                        </div>
                    )}
                </div>
            </motion.div>

            <AnimatePresence>
                {showPicker && (
                    <AppPickerModal onPick={handlePick} onClose={() => setShowPicker(false)} />
                )}
            </AnimatePresence>
        </motion.div>
    );
}

// ── Workspace Card ──────────────────────────────────────────────────────────
function WorkspaceCard({ ws, onLaunch, onEdit, onDelete, onPin, onDuplicate, onExport }) {
    const entryCount = ws.entries?.length || 0;
    const types = [...new Set((ws.entries || []).map(e => e.type))];
    return (
        <motion.div className="ws-card"
            initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97 }} transition={{ duration: 0.12 }} layout>
            <div className="ws-card-left">
                <div className="ws-card-icon" style={ws.color ? { borderColor: ws.color, color: ws.color } : {}}>
                    <Icon icon={Icons.LayoutGrid} size={17} />
                </div>
                <div className="ws-card-info">
                    <div className="ws-card-name">{ws.name}</div>
                    <div className="ws-card-meta">
                        <span>{entryCount} app{entryCount !== 1 ? 's' : ''}</span>
                        {types.includes('vscode') && <span className="ws-badge ws-badge-code">Code</span>}
                        {types.includes('url') && <span className="ws-badge ws-badge-url">URL</span>}
                        {ws.pinned && <span className="ws-badge ws-badge-pin">pinned</span>}
                        {ws.open_count > 0 && <span className="ws-launch-count">{ws.open_count}×</span>}
                    </div>
                </div>
            </div>
            <div className="ws-card-actions">
                <button className="btn-icon" title={ws.pinned ? 'Unpin' : 'Pin'}
                    onClick={() => onPin(ws)} style={ws.pinned ? { color: 'var(--warning)' } : {}}>
                    <Icon icon={ws.pinned ? Icons.PinOff : Icons.Pin} size={14} />
                </button>
                <button className="btn-icon" title="Duplicate" onClick={() => onDuplicate(ws)}>
                    <Icon icon={Icons.Copy} size={14} />
                </button>
                <button className="btn-icon" title="Export to file" onClick={() => onExport(ws)}>
                    <Icon icon={Icons.Download} size={14} />
                </button>
                <button className="btn-icon" title="Edit" onClick={() => onEdit(ws)}>
                    <Icon icon={Icons.Pencil} size={14} />
                </button>
                <button className="btn-icon btn-danger" title="Delete" onClick={() => onDelete(ws)}>
                    <Icon icon={Icons.Trash2} size={14} />
                </button>
                <button className="btn-launch" onClick={() => onLaunch(ws)}>
                    <Icon icon={Icons.Rocket} size={12} /> Launch
                </button>
            </div>
        </motion.div>
    );
}

// ── Window Row ──────────────────────────────────────────────────────────────
function WindowRow({ win, selected, onToggle, onFocus, onSnap, presets }) {
    const [showSnap, setShowSnap] = useState(false);
    const ref = useRef(null);
    useEffect(() => {
        if (!showSnap) return;
        const h = e => { if (ref.current && !ref.current.contains(e.target)) setShowSnap(false); };
        document.addEventListener('mousedown', h);
        return () => document.removeEventListener('mousedown', h);
    }, [showSnap]);
    return (
        <div ref={ref} className={`win-row ${selected ? 'selected' : ''}`}>
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
            <div className="win-actions" onClick={e => e.stopPropagation()}>
                <button className="btn-icon" title="Bring to front" onClick={() => onFocus(win.hwnd)}>
                    <Icon icon={Icons.Eye} size={13} />
                </button>
                <button className={`btn-icon ${showSnap ? 'active' : ''}`} title="Snap position"
                    onClick={() => setShowSnap(v => !v)}>
                    <Icon icon={Icons.LayoutGrid} size={13} />
                </button>
            </div>
            <AnimatePresence>
                {showSnap && (
                    <motion.div className="win-snap-popover"
                        initial={{ opacity: 0, scale: 0.95, y: -4 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.95, y: -4 }}
                        transition={{ duration: 0.1 }}>
                        <div className="snap-grid">
                            {presets.filter(p => p.id !== 'custom').map(p => (
                                <button key={p.id} className="snap-btn" title={p.label}
                                    onClick={() => { onSnap(win.hwnd, p.id); setShowSnap(false); }}>
                                    <Icon icon={IMAP[p.icon] || Icons.Monitor} size={14} />
                                    <span>{p.label}</span>
                                </button>
                            ))}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}

// ── Capture Modal ───────────────────────────────────────────────────────────
function CaptureModal({ selectedWindows, windows, onClose, onCapture }) {
    const [name, setName] = useState('');
    const selected = windows.filter(w => selectedWindows.has(w.hwnd));
    const inputRef = useRef(null);
    useEffect(() => { setTimeout(() => inputRef.current?.focus(), 60); }, []);
    return (
        <motion.div className="modal-overlay"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            exit={{ opacity: 0 }} transition={{ duration: 0.12 }}
            onClick={onClose}>
            <motion.div className="modal-content"
                initial={{ opacity: 0, scale: 0.96, y: 8 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.96, y: 8 }}
                transition={{ duration: 0.13 }}
                onClick={e => e.stopPropagation()}>
                <div className="modal-title">
                    <Icon icon={Icons.Save} size={15} /> Save as Workspace
                </div>
                <div className="capture-list">
                    {selected.map(w => (
                        <div key={w.hwnd} className="capture-item">
                            <Icon icon={Icons.AppWindow} size={12} />
                            <span className="capture-item-title">{w.title.length > 48 ? w.title.slice(0, 48) + '…' : w.title}</span>
                            <span className="capture-pos">{w.w}×{w.h}</span>
                        </div>
                    ))}
                </div>
                <div className="section-label">Name this workspace</div>
                <input ref={inputRef} className="input-field" placeholder="My Desktop Layout"
                    value={name} onChange={e => setName(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && name.trim() && onCapture(name.trim())} />
                <div className="modal-actions">
                    <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
                    <button className="btn btn-primary" disabled={!name.trim()}
                        onClick={() => onCapture(name.trim())}>
                        <Icon icon={Icons.Check} size={12} /> Create Workspace
                    </button>
                </div>
            </motion.div>
        </motion.div>
    );
}

// ══════════════════════════════════════════════════════════════════════════════
// ── MAIN APP ──────────────────────────────────────────────────────────────────
// ══════════════════════════════════════════════════════════════════════════════
function App() {
    const [tab, setTab] = useState('workspaces');
    const [workspaces, setWorkspaces] = useState([]);
    const [windows, setWindows] = useState([]);
    const [selectedWins, setSelectedWins] = useState(new Set());
    const [search, setSearch] = useState('');
    const [presets, setPresets] = useState([]);
    const [monitors, setMonitors] = useState([]);
    const [editor, setEditor] = useState(null);   // null | {workspace}
    const [captureModal, setCaptureModal] = useState(false);
    const [status, flash] = useStatus();
    const [loading, setLoading] = useState(true);
    const searchRef = useRef(null);

    // ── init ────────────────────────────────────────────────────────────────
    useEffect(() => {
        getBridge(b => {
            Promise.all([
                Promise.resolve(b.get_workspaces()),
                Promise.resolve(b.get_position_presets()),
                Promise.resolve(b.get_monitors()),
            ]).then(([wsj, psj, monj]) => {
                setWorkspaces(JSON.parse(wsj));
                setPresets(JSON.parse(psj));
                setMonitors(JSON.parse(monj));
                setLoading(false);
            });
            b.windows_refreshed.connect(j => setWindows(JSON.parse(j)));
        });
    }, []);

    // load windows when switching to that tab
    useEffect(() => {
        if (tab === 'windows' && windows.length === 0) {
            getBridge(b => Promise.resolve(b.list_windows_sync()).then(j => setWindows(JSON.parse(j))));
        }
    }, [tab]);

    useEffect(() => {
        const h = e => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'f') { e.preventDefault(); searchRef.current?.focus(); }
            if (e.key === 'Escape' && !editor) { setCaptureModal(false); }
        };
        document.addEventListener('keydown', h);
        return () => document.removeEventListener('keydown', h);
    }, [editor]);

    // ── data helpers ────────────────────────────────────────────────────────
    const refreshWorkspaces = useCallback(() => {
        getBridge(b => Promise.resolve(b.get_workspaces()).then(j => setWorkspaces(JSON.parse(j))));
    }, []);
    const refreshWindows = useCallback(() => {
        getBridge(b => Promise.resolve(b.list_windows_sync()).then(j => setWindows(JSON.parse(j))));
    }, []);

    // ── workspace actions ───────────────────────────────────────────────────
    const handleLaunch = useCallback((ws) => {
        getBridge(b => {
            Promise.resolve(b.launch_workspace(ws.id)).then(j => {
                const r = JSON.parse(j);
                r.error ? flash(r.error, 'error') : flash(`Launched "${ws.name}"  (${r.launched} apps)`, 'success');
                refreshWorkspaces();
            });
        });
    }, [flash, refreshWorkspaces]);

    const handleDelete = useCallback((ws) => {
        getBridge(b => {
            Promise.resolve(b.delete_workspace(ws.id)).then(() => {
                refreshWorkspaces(); flash(`Deleted "${ws.name}"`, 'info');
            });
        });
    }, [flash, refreshWorkspaces]);

    const handlePin = useCallback((ws) => {
        getBridge(b => {
            b.toggle_pin(ws.id, !ws.pinned);
            setTimeout(refreshWorkspaces, 100);
            flash(ws.pinned ? 'Unpinned' : 'Pinned', 'info');
        });
    }, [flash, refreshWorkspaces]);

    const handleSaveWorkspace = useCallback((data) => {
        getBridge(b => {
            Promise.resolve(b.save_workspace(JSON.stringify(data))).then(j => {
                const r = JSON.parse(j);
                r.error ? flash(r.error, 'error') : (refreshWorkspaces(), flash(`Saved "${r.name}"`, 'success'), setEditor(null));
            });
        });
    }, [flash, refreshWorkspaces]);

    const handleDuplicate = useCallback((ws) => {
        getBridge(b => {
            Promise.resolve(b.duplicate_workspace(ws.id)).then(j => {
                const r = JSON.parse(j);
                r.error ? flash(r.error, 'error') : (refreshWorkspaces(), flash(`Duplicated "${ws.name}"`, 'success'));
            });
        });
    }, [flash, refreshWorkspaces]);

    const handleExport = useCallback((ws) => {
        getBridge(b => {
            Promise.resolve(b.export_workspace(ws.id)).then(j => {
                const r = JSON.parse(j);
                if (r.cancelled) return;
                r.error ? flash(r.error, 'error') : flash(`Exported "${ws.name}"`, 'success');
            });
        });
    }, [flash]);

    const handleImport = useCallback(() => {
        getBridge(b => {
            Promise.resolve(b.import_workspace()).then(j => {
                const r = JSON.parse(j);
                if (r.cancelled) return;
                r.error ? flash(r.error, 'error') : (refreshWorkspaces(), flash(`Imported "${r.name}"`, 'success'));
            });
        });
    }, [flash, refreshWorkspaces]);

    // ── window actions ──────────────────────────────────────────────────────
    const toggleWin = useCallback((hwnd) => {
        setSelectedWins(prev => {
            const n = new Set(prev);
            n.has(hwnd) ? n.delete(hwnd) : n.add(hwnd);
            return n;
        });
    }, []);

    const handleCapture = useCallback((name) => {
        getBridge(b => {
            Promise.resolve(b.capture_windows(JSON.stringify({ name, hwnds: [...selectedWins] }))).then(j => {
                const r = JSON.parse(j);
                if (r.error) { flash(r.error, 'error'); return; }
                flash(`Created "${r.name}"  (${r.entries?.length || 0} apps)`, 'success');
                refreshWorkspaces();
                setCaptureModal(false);
                setSelectedWins(new Set());
                setTab('workspaces');
            });
        });
    }, [selectedWins, flash, refreshWorkspaces]);

    // ── filtering ───────────────────────────────────────────────────────────
    const q = search.toLowerCase();

    const filteredWs = useMemo(() => {
        const list = workspaces.filter(ws => !q || ws.name.toLowerCase().includes(q));
        return list.sort((a, b) => {
            if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
            return (b.last_opened || 0) - (a.last_opened || 0);
        });
    }, [workspaces, q]);

    const filteredWins = useMemo(() =>
        windows.filter(w => !q || w.title.toLowerCase().includes(q) || w.proc_name.toLowerCase().includes(q)),
    [windows, q]);

    // ════════════════════════════════════════════════════════════════════════
    return (
        <div className="app-shell">
            {/* Header */}
            <div className="app-header">
                <div className="app-header-icon"><Icon icon={Icons.LayoutGrid} size={16} /></div>
                <div>
                    <div className="app-header-title">Workspace Manager</div>
                    <div className="app-header-sub">capture · organize · launch</div>
                </div>
                <div className="app-header-right">
                    <button className="btn btn-ghost" onClick={handleImport} title="Import workspace from file">
                        <Icon icon={Icons.Upload} size={12} /> Import
                    </button>
                    <button className="btn btn-primary" onClick={() => setEditor({ workspace: {} })}>
                        <Icon icon={Icons.Plus} size={12} /> New
                    </button>
                </div>
            </div>

            {/* Search */}
            <div className="search-wrap">
                <span className="search-icon"><Icon icon={Icons.Search} size={13} /></span>
                <input ref={searchRef} className="search-field"
                    placeholder="Search…  (Ctrl+F)" value={search}
                    onChange={e => setSearch(e.target.value)} spellCheck={false} />
            </div>

            {/* Tabs */}
            <div className="tab-bar">
                {[
                    ['workspaces', Icons.LayoutGrid, 'Workspaces', workspaces.length],
                    ['windows',    Icons.AppWindow,   'Open Windows', null],
                ].map(([id, icon, label, count]) => (
                    <button key={id} className={`tab-btn ${tab === id ? 'active' : ''}`}
                        onClick={() => { setTab(id); setSearch(''); }}>
                        <Icon icon={icon} size={11} style={{ marginRight: 5, verticalAlign: 'middle' }} />
                        {label}
                        {count > 0 && <span className="tab-count">{count}</span>}
                    </button>
                ))}
            </div>

            {/* Content */}
            <AnimatePresence mode="wait">
                {/* ── Workspaces tab ─────────────────────────────────────── */}
                {tab === 'workspaces' && (
                    <motion.div key="ws" className="content-area"
                        initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0 }} transition={{ duration: 0.13 }}>
                        {loading ? (
                            <div className="empty-state">
                                <Icon icon={Icons.Loader2} size={22} style={{ animation: 'spin 1s linear infinite', color: 'var(--text-disabled)' }} />
                            </div>
                        ) : filteredWs.length === 0 ? (
                            <div className="empty-state">
                                <Icon icon={workspaces.length ? Icons.SearchX : Icons.LayoutGrid} size={28} style={{ color: 'var(--text-disabled)' }} />
                                <div className="empty-state-title">
                                    {workspaces.length ? `No match for "${search}"` : 'No workspaces yet'}
                                </div>
                                {!workspaces.length && (
                                    <div className="empty-state-hint">Capture your open windows or build one manually.</div>
                                )}
                                {!workspaces.length && (
                                    <div className="empty-cta-row">
                                        <button className="btn btn-primary" onClick={() => setTab('windows')}>
                                            <Icon icon={Icons.AppWindow} size={12} /> Capture Windows
                                        </button>
                                        <button className="btn btn-ghost" onClick={() => setEditor({ workspace: {} })}>
                                            <Icon icon={Icons.Plus} size={12} /> Build Manually
                                        </button>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <AnimatePresence>
                                {filteredWs.map(ws => (
                                    <WorkspaceCard key={ws.id} ws={ws}
                                        onLaunch={handleLaunch}
                                        onEdit={w => setEditor({ workspace: w })}
                                        onDelete={handleDelete}
                                        onPin={handlePin}
                                        onDuplicate={handleDuplicate}
                                        onExport={handleExport} />
                                ))}
                            </AnimatePresence>
                        )}
                    </motion.div>
                )}

                {/* ── Open Windows tab ───────────────────────────────────── */}
                {tab === 'windows' && (
                    <motion.div key="win" className="content-area"
                        initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0 }} transition={{ duration: 0.13 }}>

                        <div className="windows-toolbar">
                            <span className="win-toolbar-label">
                                {filteredWins.length} window{filteredWins.length !== 1 ? 's' : ''}
                                {selectedWins.size > 0 && <span className="win-sel-count"> · {selectedWins.size} selected</span>}
                            </span>
                            <div className="win-toolbar-actions">
                                <button className="btn btn-ghost btn-sm" onClick={refreshWindows}>
                                    <Icon icon={Icons.RefreshCw} size={11} /> Refresh
                                </button>
                                <button className="btn btn-ghost btn-sm"
                                    onClick={() => setSelectedWins(new Set(windows.map(w => w.hwnd)))}>
                                    <Icon icon={Icons.CheckSquare} size={11} /> All
                                </button>
                                <button className="btn btn-ghost btn-sm"
                                    title="Capture all open windows as a new workspace"
                                    onClick={() => { setSelectedWins(new Set(windows.map(w => w.hwnd))); setCaptureModal(true); }}>
                                    <Icon icon={Icons.SaveAll} size={11} /> Save All
                                </button>
                                {selectedWins.size > 0 && (
                                    <button className="btn btn-primary btn-sm" onClick={() => setCaptureModal(true)}>
                                        <Icon icon={Icons.Save} size={11} /> Save {selectedWins.size}
                                    </button>
                                )}
                            </div>
                        </div>

                        {filteredWins.length === 0 ? (
                            <div className="empty-state">
                                <Icon icon={Icons.AppWindow} size={28} style={{ color: 'var(--text-disabled)' }} />
                                <div className="empty-state-title">No windows visible</div>
                                <button className="btn btn-ghost btn-sm" onClick={refreshWindows}>
                                    <Icon icon={Icons.RefreshCw} size={11} /> Refresh
                                </button>
                            </div>
                        ) : filteredWins.map(w => (
                            <WindowRow key={w.hwnd} win={w}
                                selected={selectedWins.has(w.hwnd)}
                                onToggle={toggleWin}
                                onFocus={hwnd => getBridge(b => b.focus_window(hwnd))}
                                onSnap={(hwnd, p) => getBridge(b => { b.snap_window(hwnd, p); setTimeout(refreshWindows, 400); })}
                                presets={presets} />
                        ))}
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Status bar */}
            <div className="status-bar">
                <span className={`status-msg ${status?.type || ''}`}>
                    {status?.msg || `${workspaces.length} workspace${workspaces.length !== 1 ? 's' : ''}`}
                </span>
                <span className="status-hint">Ctrl+F</span>
            </div>

            {/* Workspace editor (full overlay) */}
            <AnimatePresence>
                {editor && (
                    <WorkspaceEditor workspace={editor.workspace} presets={presets} monitors={monitors}
                        onClose={() => setEditor(null)} onSave={handleSaveWorkspace} />
                )}
            </AnimatePresence>

            {/* Capture modal */}
            <AnimatePresence>
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
