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
    const browseNavRef = useRef({ tabId: null, path: null }); // last real-navigation context
    const [liveRefreshTick, setLiveRefreshTick] = useState(0);

    // Command palette
    const [palette, setPalette] = useState(false);

    // ── File-op clipboard & active ops ───────────────────────────────────────
    const [clipboard, setClipboard] = useState(null); // { paths:[], mode:'copy'|'cut' }
    const [renameTarget, setRenameTarget] = useState(null);
    const [fileOps, setFileOps] = useState([]);
    const dragPathsRef = useRef([]);
    const [confirmModal, setConfirmModal] = useState(null); // { title, message, confirmLabel, danger, onConfirm }
    const [inputModal, setInputModal] = useState(null);    // { title, label, placeholder, onConfirm }

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
        getBridge(br => {
            br.drop_tab(tab.browsePath || '', tab.title || '');
            // If it was the last tab, close the whole window
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
            if (br.file_op_progress?.connect) {
                br.file_op_progress.connect((opId, done, total, current) => {
                    setFileOps(prev => prev.map(op =>
                        op.id === opId ? { ...op, done, total, current: current || '' } : op));
                });
            }
            if (br.file_op_done?.connect) {
                br.file_op_done.connect((opId, jsonStr) => {
                    const { errors } = JSON.parse(jsonStr);
                    setFileOps(prev => prev.map(op =>
                        op.id === opId ? { ...op, done: op.total, finished: true, errors, current: '' } : op));
                    if (!errors.length) showToast('\u2705 Done');
                    else showToast(`\u26a0\ufe0f ${errors.length} error(s)`);
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
        // Determine whether this is a real navigation or a background live-refresh.
        // Only real navigations should show a loading spinner and clear the selection;
        // live refreshes silently swap the result list in-place so there is no flicker.
        const isLiveRefresh = (
            browseNavRef.current.tabId === tabId &&
            browseNavRef.current.path  === path
        );
        browseNavRef.current = { tabId, path };
        if (!isLiveRefresh) {
            patchTab(tabId, { loading: true, selected: new Set() });
        }
        getBridge(async br => {
            const raw = await br.list_folder(path);
            const list = JSON.parse(raw);
            patchTab(tabId, { results: list, loading: false });
            if (!isLiveRefresh) setStatusMsg(`📁 ${list.length} items`);
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

    // "..": parent-folder sentinel shown at top of browse listings
    const dotDotEntry = useMemo(() => {
        if (!activeTab.browsePath) return null;
        const p = activeTab.browsePath.replace(/[\\/]+$/, '');
        if (/^[A-Za-z]:\\?$/.test(p) || p === '/') return null; // already at root
        const lastSep = Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\'));
        if (lastSep < 0) return null;
        let parent = p.slice(0, lastSep) || '/';
        if (/^[A-Za-z]:$/.test(parent)) parent += '\\';
        return { path: parent, name: '..', is_dir: true, __isParent: true };
    }, [activeTab.browsePath]);

    // displayFiles = what the view actually renders (includes .. if applicable)
    const displayFiles = useMemo(() =>
        dotDotEntry ? [dotDotEntry, ...sortedResults] : sortedResults,
        [dotDotEntry, sortedResults]);

    function handleSort(key) {
        if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
        else { setSortKey(key); setSortDir('asc'); }
    }

    // ── Selection ─────────────────────────────────────────────────────────────
    async function handlePreviewSelection(file) {
        if (!file || file.is_dir) {
            patchActive({ previewFile: null });
            return;
        }
        getBridge(async br => {
            if (br.can_preview) {
                const ok = await br.can_preview(file.path);
                patchActive({ previewFile: ok ? file : null });
            } else {
                // Fallback for older bridge
                patchActive({ previewFile: file });
            }
        });
    }

    function handleSelect(file, e) {
        if (file.__isParent) return; // "..": not selectable
        if (e.shiftKey) {
            const anchorPath = activeTab.selectionAnchor || file.path;
            const anchorIdx = sortedResults.findIndex(x => x.path === anchorPath);
            const currentIdx = sortedResults.findIndex(x => x.path === file.path);
            if (anchorIdx >= 0 && currentIdx >= 0) {
                const lo = Math.min(anchorIdx, currentIdx);
                const hi = Math.max(anchorIdx, currentIdx);
                const range = new Set(sortedResults.slice(lo, hi + 1).map(x => x.path));
                patchActive({ selected: range, selectionAnchor: anchorPath });
                handlePreviewSelection(file);
                return;
            }
        }

        if (e.ctrlKey) {
            const next = new Set(activeTab.selected);
            if (next.has(file.path)) next.delete(file.path);
            else next.add(file.path);
            patchActive({ selected: next, selectionAnchor: file.path });
            return;
        }

        if (activeTab.selected.has(file.path) && !e.ctrlKey && !e.shiftKey) {
            if (activeTab.selected.size > 1) {
                patchActive({ selected: new Set([file.path]), selectionAnchor: file.path });
                handlePreviewSelection(file);
            }
            return;
        }
        patchActive({
            selected: new Set([file.path]),
            selectionAnchor: file.path,
        });
        handlePreviewSelection(file);
    }

    function handleDouble(file) {
        if (file.__isParent) { handleNavUp(); return; }
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

    // ── File operations ───────────────────────────────────────────────────────
    function doFileOp(mode, sources, dest = '') {
        const opId = Math.random().toString(36).slice(2, 10);
        setFileOps(prev => [...prev, { id: opId, mode, sources, dest, done: 0, total: sources.length, errors: [], finished: false, current: '' }]);
        getBridge(br => {
            if (mode === 'copy') br.copy_items(opId, JSON.stringify(sources), dest);
            else if (mode === 'move') br.move_items(opId, JSON.stringify(sources), dest);
            else if (mode === 'delete') br.delete_items(opId, JSON.stringify(sources));
        });
    }

    function handleCancelOp(opId) {
        getBridge(br => br.cancel_file_op(opId));
        // Mark as finished immediately in the UI so the cancel is responsive
        setFileOps(prev => prev.map(op =>
            op.id === opId ? { ...op, finished: true, errors: ['Cancelled'], current: '' } : op));
    }

    function handleCopy() {
        const paths = [...activeTab.selected];
        if (!paths.length) return;
        setClipboard({ paths, mode: 'copy' });
        showToast(`\ud83d\udccb ${paths.length} item${paths.length > 1 ? 's' : ''} copied`);
    }

    function handleCut() {
        const paths = [...activeTab.selected];
        if (!paths.length) return;
        setClipboard({ paths, mode: 'cut' });
        showToast(`\u2702\ufe0f ${paths.length} item${paths.length > 1 ? 's' : ''} cut`);
    }

    function handlePaste() {
        if (!clipboard?.paths.length) return;
        const dest = activeTab.browsePath;
        if (!dest) { showToast('Navigate into a folder first to paste', true); return; }
        doFileOp(clipboard.mode === 'cut' ? 'move' : clipboard.mode, clipboard.paths, dest);
        if (clipboard.mode === 'cut') setClipboard(null);
    }

    function handleDelete() {
        const paths = [...activeTab.selected];
        if (!paths.length) return;
        const msg = `Delete ${paths.length} item${paths.length > 1 ? 's' : ''}?\nFiles will be sent to the Recycle Bin.`;
        if (!confirm(msg)) return;
        doFileOp('delete', paths);
        patchActive({ selected: new Set() });
    }

    function handleRenameStart() {
        if (activeTab.selected.size !== 1) return;
        const path = [...activeTab.selected][0];
        const file = sortedResults.find(f => f.path === path);
        if (file) setRenameTarget(file);
    }

    function handleDragStart(e, file) {
        if (file.__isParent) return; // can’t drag the “..” entry
        const paths = activeTab.selected.has(file.path)
            ? sortedResults.filter(f => activeTab.selected.has(f.path)).map(f => f.path)
            : [file.path];
        dragPathsRef.current = paths;
        e.dataTransfer.effectAllowed = 'copyMove';
        const ghost = document.createElement('div');
        ghost.className = 'drag-ghost';
        ghost.textContent = paths.length === 1 ? file.name : `${paths.length} items`;
        ghost.style.cssText = 'position:fixed;top:-200px;left:0;pointer-events:none;';
        document.body.appendChild(ghost);
        e.dataTransfer.setDragImage(ghost, 20, 12);
        setTimeout(() => document.body.removeChild(ghost), 0);
    }

    function handleDropOnFolder(e, destPath) {
        const paths = dragPathsRef.current;
        if (!paths.length) return;
        doFileOp(e.ctrlKey ? 'copy' : 'move', paths, destPath);
        dragPathsRef.current = [];
    }

    function handleDropOnCurrentDir(e) {
        e.preventDefault();
        const dest = activeTab.browsePath;
        if (!dest) return;
        handleDropOnFolder(e, dest);
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
            { icon: '📂', label: 'Open', kbd: 'Enter', action: () => getBridge(b => pathStrs.forEach(p => b.open_path(p))) },
            { icon: '🔍', label: 'Show in Explorer', action: () => getBridge(b => b.show_in_explorer(pathStrs[0])) },
            'sep',
            { icon: '✂️', label: 'Cut', kbd: 'Ctrl+X', action: handleCut },
            { icon: '📋', label: 'Copy', kbd: 'Ctrl+C', action: handleCopy },
            { icon: '📄', label: 'Copy Path', action: () => { getBridge(b => b.copy_to_clipboard(pathStrs.join('\n'))); showToast('Path copied'); } },
            ...(clipboard && activeTab.browsePath ? [{ icon: '📥', label: 'Paste here', kbd: 'Ctrl+V', action: handlePaste }] : []),
            'sep',
            { icon: '✏️', label: 'Rename…', kbd: 'F2', action: handleRenameStart },
            { icon: '🗑️', label: `Delete${paths.length > 1 ? ` (${paths.length})` : ''}`, kbd: 'Del', danger: true, action: handleDelete },
            'sep',
            { icon: '👁️', label: 'Preview', action: () => handlePreviewSelection(file) },
            ...(file.is_dir ? [{ icon: '🗂️', label: 'Open in new tab', action: () => addTab(file.path) }] : []),
            {
                icon: isFav ? '💔' : '⭐', label: isFav ? 'Remove from Favorites' : 'Add to Favorites',
                action: () => isFav ? handleRemoveFavorite(file.path) : handleAddFavorite(file)
            },
            'sep',
            { icon: '🗄️', label: 'Open in File Ops', action: () => getBridge(b => b.open_in_file_ops(JSON.stringify(pathStrs))) },
            { icon: '🗜️', label: 'Compress / Extract…', action: () => getBridge(b => b.open_in_archiver(JSON.stringify(pathStrs))) },
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
        setConfirmModal({
            title: '🗑️ Clear Index',
            message: `Clear the entire index (${stats.db_mb} MB)?\nAll indexed data will be removed and you'll need to re-index.`,
            confirmLabel: 'Clear',
            danger: true,
            onConfirm: async () => {
                const br = b.current; if (!br) return;
                await br.clear_index();
                setTabs(prev => prev.map(t => ({ ...t, results: [] })));
                setStatusMsg('Index cleared');
                showToast('Index cleared');
            },
        });
    }

    // ── Ignore ──────────────────────────────────────────────────────────────────────
    function handleAddIgnore() {
        setInputModal({
            title: '🚫 Add Ignore Rule',
            label: 'Folder name, file extension (.tmp), or full path:',
            placeholder: 'e.g.  node_modules  or  .tmp',
            onConfirm: async (rule) => {
                const newIgnore = [...ignore, { rule, enabled: true }];
                setIgnore(newIgnore);
                await persistConfig(folders, newIgnore);
            },
        });
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
            // File-op shortcuts
            if (!e.target.matches('input,textarea')) {
                if ((e.ctrlKey || e.metaKey) && e.key === 'c') { e.preventDefault(); handleCopy(); return; }
                if ((e.ctrlKey || e.metaKey) && e.key === 'x') { e.preventDefault(); handleCut(); return; }
                if ((e.ctrlKey || e.metaKey) && e.key === 'v') { e.preventDefault(); handlePaste(); return; }
                if (e.key === 'Delete' && activeTab.selected.size > 0) { e.preventDefault(); handleDelete(); return; }
                if (e.key === 'F2') { e.preventDefault(); handleRenameStart(); return; }
            }
            // Alt+Left or Backspace (outside input) = navigate up in browse mode
            if ((e.altKey && e.key === 'ArrowLeft') || (e.key === 'Backspace' && !e.target.matches('input,textarea') && activeTab.browsePath)) {
                e.preventDefault();
                handleNavUp();
                return;
            }
            // Arrow key navigation through the file list
            if ((e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Home' || e.key === 'End')
                && !e.target.matches('input,textarea') && sortedResults.length > 0) {
                e.preventDefault();
                const anchor = activeTab.selectionAnchor;
                let curIdx = anchor ? sortedResults.findIndex(r => r.path === anchor) : -1;
                if (curIdx === -1 && activeTab.selected.size > 0) {
                    const first = [...activeTab.selected][0];
                    curIdx = sortedResults.findIndex(r => r.path === first);
                }
                let nextIdx;
                if (e.key === 'ArrowDown') nextIdx = curIdx < sortedResults.length - 1 ? curIdx + 1 : curIdx < 0 ? 0 : curIdx;
                else if (e.key === 'ArrowUp') nextIdx = curIdx > 0 ? curIdx - 1 : 0;
                else if (e.key === 'Home') nextIdx = 0;
                else nextIdx = sortedResults.length - 1; // End
                const next = sortedResults[nextIdx];
                if (!next) return;
                if (e.shiftKey) {
                    // Range-extend selection from anchor
                    const anchorIdx = anchor ? sortedResults.findIndex(r => r.path === anchor) : nextIdx;
                    const lo = Math.min(anchorIdx >= 0 ? anchorIdx : nextIdx, nextIdx);
                    const hi = Math.max(anchorIdx >= 0 ? anchorIdx : nextIdx, nextIdx);
                    const range = new Set(sortedResults.slice(lo, hi + 1).map(r => r.path));
                    patchActive({ selected: range, selectionAnchor: activeTab.selectionAnchor || next.path });
                    handlePreviewSelection(next);
                } else {
                    patchActive({ selected: new Set([next.path]), selectionAnchor: next.path });
                    handlePreviewSelection(next);
                }
                // Scroll into view after React paint
                setTimeout(() => {
                    const el = document.querySelector(`[data-path="${next.path.replace(/"/g, '\\"')}"]`);
                    el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                }, 0);
                return;
            }
            if (e.key === 'Escape') { setCtxMenu(null); setPalette(false); setConfirmModal(null); setInputModal(null); patchActive({ previewFile: null }); }
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
    }, [activeTab.selected, activeTab.selectionAnchor, activeTab.browsePath, activeTabId, tabs, sortedResults, clipboard]);

    // ── Common view props ─────────────────────────────────────────────────────
    const cutPaths = useMemo(() =>
        clipboard?.mode === 'cut' ? new Set(clipboard.paths) : new Set()
    , [clipboard]);

    const viewProps = {
        files: displayFiles,
        selected: activeTab.selected,
        onSelect: handleSelect,
        onDouble: handleDouble,
        onCtxMenu: handleCtxMenu,
        onDragStart: handleDragStart,
        onDropOnFolder: handleDropOnFolder,
        cutPaths,
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
                {activeTab.selected.size > 0 ? (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 600 }}>{activeTab.selected.size} selected</span>
                        <button className="btn btn-ghost" style={{ padding: '2px 8px', fontSize: 11 }}
                            onClick={() => { getBridge(b => b.copy_to_clipboard([...activeTab.selected].join('\n'))); showToast('Paths copied'); }}>
                            📋 Copy paths
                        </button>
                        <button className="btn btn-ghost" style={{ padding: '2px 8px', fontSize: 11 }}
                            onClick={() => patchActive({ selected: new Set() })}>
                            ✕ Deselect
                        </button>
                    </div>
                ) : (
                    <span style={{ fontSize: 11, color: 'var(--text-disabled)' }}>
                        {stats.count.toLocaleString()} indexed
                    </span>
                )}
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
                <div className="main-panel"
                    onDragOver={activeTab.browsePath ? e => e.preventDefault() : undefined}
                    onDrop={activeTab.browsePath ? handleDropOnCurrentDir : undefined}>

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
            {/* ── File-op progress modal ────────────────────────────────────── */}
            {fileOps.length > 0 && (
                <FileOpModal
                    ops={fileOps}
                    onDismiss={id => setFileOps(prev => prev.filter(o => o.id !== id))}
                    onCancel={handleCancelOp}
                />
            )}
            {/* ── Rename dialog ─────────────────────────────────────────────── */}
            {renameTarget && (
                <RenameDialog
                    file={renameTarget}
                    onDone={() => setLiveRefreshTick(t => t + 1)}
                    onClose={() => setRenameTarget(null)}
                />
            )}
            {/* ── Confirm modal ─────────────────────────────────────────────── */}
            {confirmModal && (
                <ConfirmModal {...confirmModal} onClose={() => setConfirmModal(null)} />
            )}
            {/* ── Input modal ───────────────────────────────────────────────── */}
            {inputModal && (
                <InputModal {...inputModal} onClose={() => setInputModal(null)} />
            )}
        </div>
    );
};

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
// 