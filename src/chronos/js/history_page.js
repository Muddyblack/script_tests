// ─── HISTORY PAGE ────────────────────────────────────────────────────────────
// Requires: utils.js (window.md, window.fmtDate, window.fmtHuman)

const { useState, useMemo } = React;
const { motion } = window.Motion;
const { md, fmtDate, fmtHuman, PC } = window;

const PAGE_SIZE = window.PAGE_SIZE || 25;

const HistoryPage = ({ data, safeCall }) => {
    const [search, setSearch] = useState('');
    const [filter, setFilter] = useState('all');
    const [sortBy, setSortBy] = useState('date_desc');
    const [editingItem, setEditingItem] = useState(null);
    const [page, setPage] = useState(1);

    const handleSaveLog = () => {
        if (!editingItem) return;
        safeCall('update_task', editingItem.id, editingItem.content, editingItem.notes, editingItem.links || '');
        setEditingItem(null);
    };

    const IC = {
        High:   { dot: 'var(--danger)',  ring: true },
        Medium: { dot: 'var(--warning)', ring: false },
        Low:    { dot: 'var(--success)', ring: false },
    };

    const completedItems = useMemo(() => {
        let items = data.tasks.filter(t => t.status === 'Completed').map(t => ({
            ...t, dateStr: t.completed_at || t.timestamp, impact: t.priority,
        }));
        if (filter === 'tasks')        items = items.filter(i => !i.is_achievement);
        if (filter === 'achievements') items = items.filter(i => i.is_achievement);
        if (search.trim()) {
            const q = search.toLowerCase();
            items = items.filter(i => i.content.toLowerCase().includes(q) || (i.notes && i.notes.toLowerCase().includes(q)));
        }
        items.sort((a, b) => {
            if (sortBy === 'date_asc')  return new Date(a.dateStr || 0) - new Date(b.dateStr || 0);
            if (sortBy === 'name_asc')  return a.content.localeCompare(b.content);
            if (sortBy === 'name_desc') return b.content.localeCompare(a.content);
            return new Date(b.dateStr || 0) - new Date(a.dateStr || 0);
        });
        return items;
    }, [data.tasks, filter, search, sortBy]);

    const pagedItems = completedItems.slice(0, page * PAGE_SIZE);

    const byDate = useMemo(() => {
        const G = {};
        if (sortBy.startsWith('date')) {
            pagedItems.forEach(a => {
                const d = a.dateStr
                    ? new Date(a.dateStr).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
                    : 'Earlier';
                if (!G[d]) G[d] = [];
                G[d].push(a);
            });
        } else {
            G['All Items'] = pagedItems;
        }
        return G;
    }, [pagedItems, sortBy]);

    return (
        <div className="flex-1 overflow-y-auto px-7 py-7 space-y-6 max-w-3xl">
            <header className="flex items-end justify-between">
                <div>
                    <h2 className="text-xl font-bold tracking-tight" style={{ color: 'var(--text-primary)' }}>Logbook</h2>
                    <p className="text-sm mt-0.5" style={{ color: 'var(--text-disabled)' }}>{completedItems.length} items recorded</p>
                </div>
            </header>
            <div className="flex gap-3 text-sm">
                <input value={search} onChange={e => { setSearch(e.target.value); setPage(1); }}
                    className="input-field py-1.5 px-3 flex-1 text-sm bg-transparent" placeholder="Search history..." style={{ border: '1px solid var(--border)' }} />
                <select value={sortBy} onChange={e => setSortBy(e.target.value)}
                    className="input-field py-1 px-2 text-xs bg-transparent" style={{ width: 'auto', border: '1px solid var(--border)', height: 34, borderRadius: 8 }}>
                    <option value="date_desc">Newest First</option>
                    <option value="date_asc">Oldest First</option>
                    <option value="name_asc">Name (A-Z)</option>
                    <option value="name_desc">Name (Z-A)</option>
                </select>
                <div className="flex gap-1.5 flex-shrink-0">
                    {[['all', 'All'], ['tasks', 'Tasks'], ['achievements', 'Achievements']].map(([v, l]) => (
                        <button key={v} onClick={() => { setFilter(v); setPage(1); }}
                            className="px-3 py-1.5 rounded-lg text-xs font-bold transition-all"
                            style={{ background: filter === v ? 'var(--bg-elevated)' : 'transparent', color: filter === v ? 'var(--text-primary)' : 'var(--text-disabled)', border: `1px solid ${filter === v ? 'var(--border-light)' : 'transparent'}` }}>
                            {l}
                        </button>
                    ))}
                </div>
            </div>
            {Object.entries(byDate).map(([date, items]) => (
                <div key={date} className="space-y-2">
                    <div className="section-label px-1">{date}</div>
                    {items.map(a => {
                        const ic = IC[a.impact] || IC.Medium;
                        return (
                            <div key={a.id} className="group card-inset flex items-start gap-4 p-4 hover:border-border-h transition-all"
                                onDoubleClick={() => setEditingItem(a)}>
                                <div className={`mt-1.5 flex-shrink-0 rounded-full ${ic.ring ? 'pulse-ring' : ''}`}
                                    style={{ width: 8, height: 8, background: a.is_achievement ? 'var(--warning)' : ic.dot }} />
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm font-semibold leading-snug" style={{ color: 'var(--text-primary)' }}>
                                        {a.is_achievement ? <span style={{ color: 'var(--warning)', marginRight: 6 }}>★</span> : <span style={{ color: 'var(--success)', marginRight: 6 }}>✓</span>}
                                        {a.content}
                                    </p>
                                    {a.notes && <div className="text-xs mt-2 leading-relaxed md" style={{ color: 'var(--text-secondary)' }} dangerouslySetInnerHTML={{ __html: md(a.notes) }} />}
                                    {(a.due_date || (a.tags && a.tags.length > 0) || a.time_spent > 0) && (
                                        <div className="flex items-center gap-2 mt-2 flex-wrap">
                                            {a.time_spent > 0 && <span className="mono text-xs font-semibold px-1.5 py-0.5 rounded" style={{ background: 'var(--accent-hover-dim)', color: 'var(--accent-hover)' }}>⏱ {fmtHuman(a.time_spent)}</span>}
                                            {a.due_date && <span className="text-xs font-semibold" style={{ color: 'var(--text-disabled)' }}>{a.due_date}</span>}
                                            {a.tags && Array.isArray(a.tags) && a.tags.filter(Boolean).map(tag => <span key={tag} className="tag">#{tag}</span>)}
                                        </div>
                                    )}
                                </div>
                                <div className="flex items-center gap-2 flex-shrink-0">
                                    <button onClick={() => setEditingItem(a)} className="action-btn opacity-0 group-hover:opacity-100" style={{ fontSize: 11 }}>Edit</button>
                                    <button onClick={() => safeCall('update_task_status', a.id, 'Pending')} className="action-btn opacity-0 group-hover:opacity-100" style={{ fontSize: 10 }}>Undo</button>
                                </div>
                            </div>
                        );
                    })}
                </div>
            ))}
            {Object.keys(byDate).length === 0 && (
                <div className="empty"><div style={{ fontSize: 40 }}>📜</div><div className="text-sm font-bold" style={{ color: 'var(--text-disabled)' }}>No history found</div></div>
            )}
            {pagedItems.length < completedItems.length && (
                <button onClick={() => setPage(p => p + 1)} className="btn btn-ghost w-full" style={{ fontSize: 11 }}>
                    Show more ({completedItems.length - pagedItems.length} remaining)
                </button>
            )}

            {editingItem && (
                <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) setEditingItem(null); }}>
                    <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="card p-6 space-y-4 shadow-lg w-full max-w-lg" style={{ background: 'var(--bg-base)' }}>
                        <div className="flex justify-between items-center">
                            <h3 className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>Edit Details</h3>
                            <button onClick={() => setEditingItem(null)} style={{ color: 'var(--text-disabled)', background: 'none', border: 'none', cursor: 'pointer' }}>✕</button>
                        </div>
                        <input value={editingItem.content} onChange={e => setEditingItem({ ...editingItem, content: e.target.value })}
                            className="input-field w-full font-bold" placeholder="Title..." />
                        <textarea value={editingItem.notes || ''} onChange={e => setEditingItem({ ...editingItem, notes: e.target.value })}
                            className="input-field w-full resize-none text-xs mono" style={{ height: 120, lineHeight: 1.6 }}
                            placeholder="Notes, context, markdown..." />
                        <div className="flex gap-2.5 pt-2">
                            <button onClick={() => setEditingItem(null)} className="btn btn-ghost flex-1">Cancel</button>
                            <button onClick={handleSaveLog} className="btn btn-gold flex-1">Save</button>
                        </div>
                    </motion.div>
                </div>
            )}
        </div>
    );
};

// ─── EXPORTS ─────────────────────────────────────────────────────────────────
window.HistoryPage = HistoryPage;
