// ─── APP ROOT (ShortcutsOverlay + Sidebar + App) ─────────────────────────────
// Requires: utils.js (useBridge), all *_page.js files

const { useState, useEffect, useCallback, useMemo } = React;
const { motion, AnimatePresence } = window.Motion;
const { useBridge } = window;
const { MissionsPage, HistoryPage, AnalyticsPage, AIChatPage, WorldClockPage, SettingsPage } = window;

// ─── SHORTCUTS OVERLAY ───────────────────────────────────────────────────────
const ShortcutsOverlay = ({ onClose }) => {
    const SHORTCUTS = [
        { keys: 'Ctrl+K', desc: 'Quick capture' },
        { keys: 'Shift+F', desc: 'Exit focus mode' },
        { keys: '?', desc: 'Toggle shortcuts help' },
        { keys: 'F12', desc: 'Open DevTools' },
        { keys: 'Right-click', desc: 'Task context menu' },
        { keys: 'Double-click', desc: 'Edit task title' },
        { keys: 'Click title', desc: 'Expand/collapse details' },
    ];
    return (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
            <motion.div initial={{ y: 20, opacity: 0, scale: 0.97 }} animate={{ y: 0, opacity: 1, scale: 1 }}
                className="card p-6 space-y-4 w-full max-w-sm" style={{ boxShadow: 'var(--shadow-lg)' }}>
                <div className="flex items-center justify-between">
                    <h3 className="font-bold text-base" style={{ color: 'var(--text-primary)' }}>Keyboard Shortcuts</h3>
                    <button onClick={onClose} className="action-btn">✕</button>
                </div>
                <div className="space-y-1">
                    {SHORTCUTS.map(s => (
                        <div key={s.keys} className="flex items-center justify-between py-2 px-1" style={{ borderBottom: '1px solid var(--border)' }}>
                            <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>{s.desc}</span>
                            <span className="kbd">{s.keys}</span>
                        </div>
                    ))}
                </div>
            </motion.div>
        </div>
    );
};

// ─── SIDEBAR ─────────────────────────────────────────────────────────────────
const Sidebar = ({ tab, setTab, badges = {} }) => {
    const NAV = [
        { id: 'missions', l: 'Tasks', ic: '☐', c: 'var(--warning)' },
        { id: 'log', l: 'Logbook', ic: '◈', c: 'var(--accent-pressed)' },
        { id: 'analytics', l: 'Recap', ic: '◉', c: 'var(--accent-hover)' },
        { id: 'aichat', l: 'AI Chat', ic: '◇', c: 'var(--accent)' },
        { id: 'worldclock', l: 'World Clock', ic: '◷', c: 'var(--accent-pressed)' },
        { id: 'settings', l: 'Settings', ic: '◎', c: 'var(--text-disabled)' },
    ];
    return (
        <aside className="sidebar-wrap flex flex-col pt-7 pb-6" style={{ borderRight: '1px solid var(--border)', background: 'var(--bg-base)' }}>
            <div className="px-5 mb-8">
                <div className="font-bold text-base tracking-tight" style={{ color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
                    CHRONOS<span style={{ color: 'var(--warning)' }}>_</span>
                </div>
            </div>
            <nav className="flex-1 space-y-0.5 px-3">
                {NAV.map(item => (
                    <button key={item.id} onClick={() => setTab(item.id)}
                        className={`nav-item w-full flex items-center gap-3 px-3 py-2.5 text-sm ${tab === item.id ? 'active' : ''}`}
                        style={{ color: tab === item.id ? item.c : 'var(--text-disabled)', background: 'transparent', border: 'none', textAlign: 'left', cursor: 'pointer' }}>
                        <span style={{ fontSize: 13, opacity: .75 }}>{item.ic}</span>
                        <span className="font-semibold">{item.l}</span>
                        {badges[item.id] > 0 && (
                            <span className="ml-auto mono text-xs font-bold px-1.5 py-0.5 rounded-md"
                                style={{ background: item.c + '22', color: item.c, fontSize: 10 }}>
                                {badges[item.id]}
                            </span>
                        )}
                        {!badges[item.id] && tab === item.id && (
                            <div style={{ width: 5, height: 5, borderRadius: '50%', background: item.c, marginLeft: 'auto', flexShrink: 0 }} />
                        )}
                    </button>
                ))}
            </nav>
            <div className="px-5 pt-4" style={{ borderTop: '1px solid var(--border)' }}>
                <div className="text-xs" style={{ color: 'var(--text-disabled)' }}>
                    Press <span className="kbd">?</span> for shortcuts
                </div>
            </div>
        </aside>
    );
};

// ─── APP ROOT ────────────────────────────────────────────────────────────────
const App = () => {
    const { data, call: safeCall } = useBridge();
    const [tab, setTab] = useState('missions');
    const [focusId, setFocusId] = useState(null);
    const [timers, setTimers] = useState({});
    const [showShortcuts, setShowShortcuts] = useState(false);
    const [pendingTaskCtx, setPendingTaskCtx] = useState(null);

    const openChatWithTask = useCallback(async (taskId) => {
        const detail = await safeCall('get_task_detail', taskId);
        if (detail) setPendingTaskCtx(detail);
        setTab('aichat');
    }, [safeCall]);

    useEffect(() => { document.body.classList.toggle('focus-mode', !!focusId); }, [focusId]);

    useEffect(() => {
        const h = (e) => {
            if (e.shiftKey && e.key === 'F') setFocusId(null);
            if (e.key === '?' && !e.target.closest('input, textarea, select')) setShowShortcuts(p => !p);
        };
        window.addEventListener('keydown', h);
        return () => window.removeEventListener('keydown', h);
    }, []);

    const badges = useMemo(() => ({
        missions: data.tasks.filter(t => t.status !== 'Completed' && t.parent_id === 0).length,
        log: data.tasks.filter(t => t.status === 'Completed').length,
    }), [data.tasks]);

    // Allow Python to trigger reminder popup
    window.triggerReminderPopup = () => setTab('missions');

    return (
        <div id="app" style={{ display: 'flex', height: '100vh', width: '100vw', overflow: 'hidden', background: 'var(--bg-base)' }}>
            <Sidebar tab={tab} setTab={setTab} badges={badges} />
            <main style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', position: 'relative' }}>
                {/* Deep Focus banner */}
                <AnimatePresence>
                    {focusId && (
                        <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
                            className="no-dim"
                            style={{ position: 'absolute', top: 14, left: '50%', transform: 'translateX(-50%)', zIndex: 50, display: 'flex', alignItems: 'center', gap: 10, padding: '7px 16px', borderRadius: 99, background: 'var(--bg-base)', border: '1px solid var(--border-light)', boxShadow: 'var(--shadow-md)' }}>
                            <div style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--warning)' }} className="breathe" />
                            <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--warning)' }}>Deep Focus</span>
                            <button onClick={() => setFocusId(null)} style={{ fontSize: 10, color: 'var(--text-disabled)', marginLeft: 6, fontWeight: 700, cursor: 'pointer', background: 'none', border: 'none' }}>
                                Exit <span className="kbd">Shift+F</span>
                            </button>
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* Tab pages */}
                <AnimatePresence mode="wait">
                    {tab === 'missions' && (
                        <motion.div key="m" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
                            <MissionsPage data={data} safeCall={safeCall} focusId={focusId} setFocusId={setFocusId} timers={timers} setTimers={setTimers} onAskAI={openChatWithTask} />
                        </motion.div>
                    )}
                    {tab === 'log' && (
                        <motion.div key="l" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
                            <HistoryPage data={data} safeCall={safeCall} />
                        </motion.div>
                    )}
                    {tab === 'analytics' && (
                        <motion.div key="a" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
                            <AnalyticsPage data={data} safeCall={safeCall} />
                        </motion.div>
                    )}
                    {tab === 'aichat' && (
                        <motion.div key="ai" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
                            <AIChatPage data={data} safeCall={safeCall} pendingTaskCtx={pendingTaskCtx} clearPendingTaskCtx={() => setPendingTaskCtx(null)} />
                        </motion.div>
                    )}
                    {tab === 'worldclock' && (
                        <motion.div key="w" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
                            <WorldClockPage data={data} safeCall={safeCall} />
                        </motion.div>
                    )}
                    {tab === 'settings' && (
                        <motion.div key="s" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
                            <SettingsPage data={data} safeCall={safeCall} />
                        </motion.div>
                    )}
                </AnimatePresence>
            </main>

            <AnimatePresence>
                {showShortcuts && <ShortcutsOverlay onClose={() => setShowShortcuts(false)} />}
            </AnimatePresence>
        </div>
    );
};

// ─── MOUNT ────────────────────────────────────────────────────────────────────
ReactDOM.createRoot(document.getElementById('root')).render(<App />);
