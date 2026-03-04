// ─── ANALYTICS PAGE ──────────────────────────────────────────────────────────

const { useState, useMemo } = React;
const { md, fmtHuman, PC, aiListeners } = window;

const AnalyticsPage = ({ data, safeCall }) => {
    const [timeVal, setTimeVal] = useState('24');
    const [timeUnit, setTimeUnit] = useState('hours');
    const [recap, setRecap] = useState('');
    const [loading, setLoading] = useState(false);
    const [aiLoading, setAiLoading] = useState(false);

    const stats = useMemo(() => {
        const total = data.tasks.length, done = data.tasks.filter(t => t.status === 'Completed').length;
        const overdue = data.tasks.filter(t => { if (!t.due_date || t.status === 'Completed') return false; return new Date(t.due_date) < new Date(); }).length;
        const high = data.tasks.filter(t => t.priority === 'High' && t.status !== 'Completed').length;
        const wins = data.tasks.filter(t => t.is_achievement).length;
        return { total, done, active: total - done, overdue, high, wins, momentum: total > 0 ? Math.round((done / total) * 100) : 0 };
    }, [data]);

    const priDist = useMemo(() => {
        const C = { High: 0, Medium: 0, Low: 0 };
        data.tasks.filter(t => t.status !== 'Completed').forEach(t => { if (C[t.priority] !== undefined) C[t.priority]++; });
        const T = Object.values(C).reduce((a, b) => a + b, 0) || 1;
        return Object.entries(C).map(([k, v]) => ({ label: k, count: v, pct: Math.round((v / T) * 100), color: PC[k].color }));
    }, [data.tasks]);

    const scan = async () => { setLoading(true); const r = await safeCall('generate_summary', `-${timeVal} ${timeUnit}`); setRecap(r || 'No data in this range.'); setLoading(false); };
    const scanPreset = async (p) => { setLoading(true); const r = await safeCall('generate_summary', p); setRecap(r || 'No data in this range.'); setLoading(false); };
    const aiSynth = () => {
        setAiLoading(true);
        const reqId = 'insights_' + Date.now();
        const handler = (id, text) => {
            if (id !== reqId) return;
            aiListeners.delete(handler);
            setRecap(text || recap);
            setAiLoading(false);
        };
        aiListeners.add(handler);
        safeCall('send_ai_chat', JSON.stringify([
            { role: 'system', content: 'You are a chill productivity buddy reviewing someone\'s task data. Give a short, casual take — what looks good, what stands out, anything worth noting. Keep it conversational and brief. No corporate bullet-point essays.' },
            { role: 'user', content: `Here\'s my productivity data, what do you think?\n${recap}` },
        ]), reqId);
    };

    const totalTime = useMemo(() => data.tasks.reduce((s, t) => s + (t.time_spent || 0), 0), [data.tasks]);
    const avgWorkTime = useMemo(() => {
        const done = data.tasks.filter(t => t.status === 'Completed' && t.time_spent > 0);
        return done.length > 0 ? Math.round(done.reduce((s, t) => s + t.time_spent, 0) / done.length) : 0;
    }, [data.tasks]);

    const CARDS = [
        { l: 'Total',       v: stats.total,    c: 'var(--text-primary)' },
        { l: 'Completed',   v: stats.done,     c: 'var(--success)' },
        { l: 'Active',      v: stats.active,   c: 'var(--warning)' },
        { l: 'Overdue',     v: stats.overdue,  c: 'var(--danger)' },
        { l: 'Time Tracked', v: fmtHuman(totalTime) || '0m', c: 'var(--accent-hover)' },
        { l: 'Avg Work Time', v: avgWorkTime > 0 ? fmtHuman(avgWorkTime) : '—', c: 'var(--accent-pressed)' },
        { l: 'Achievements', v: stats.wins,    c: 'var(--warning)' },
    ];

    return (
        <div className="flex-1 overflow-y-auto px-7 py-7 space-y-6 max-w-4xl">
            <header className="flex items-end justify-between">
                <div>
                    <h2 className="text-xl font-bold tracking-tight" style={{ color: 'var(--text-primary)' }}>Intelligence</h2>
                    <p className="text-sm mt-0.5" style={{ color: 'var(--text-disabled)' }}>Analytics & reports</p>
                </div>
                <div className="text-right">
                    <div className="section-label mb-1">Momentum</div>
                    <div className="text-4xl font-black mono" style={{ color: 'var(--warning)' }}>{stats.momentum}%</div>
                </div>
            </header>
            <div className="card p-4 space-y-2">
                <div className="flex justify-between text-xs" style={{ color: 'var(--text-disabled)' }}>
                    <span>{stats.done} completed of {stats.total} total</span>
                    <span className="mono font-bold" style={{ color: 'var(--warning)' }}>{stats.momentum}%</span>
                </div>
                <div className="progress-track" style={{ height: 6 }}>
                    <div className="progress-fill" style={{ width: `${stats.momentum}%`, background: `linear-gradient(90deg, var(--warning), var(--accent-pressed))` }} />
                </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
                {CARDS.map(s => (
                    <div key={s.l} className="card p-4 space-y-1">
                        <div className="section-label">{s.l}</div>
                        <div className="text-2xl font-black mono" style={{ color: s.c }}>{s.v}</div>
                    </div>
                ))}
            </div>
            <div className="card p-5 space-y-4">
                <div className="section-label">Active Tasks by Priority</div>
                {priDist.map(d => (
                    <div key={d.label} className="flex items-center gap-3">
                        <div className="w-16 text-xs font-bold" style={{ color: d.color }}>{d.label}</div>
                        <div className="flex-1 progress-track"><div className="progress-fill" style={{ width: `${d.pct}%`, background: d.color }} /></div>
                        <div className="w-8 text-xs mono text-right" style={{ color: 'var(--text-disabled)' }}>{d.count}</div>
                    </div>
                ))}
            </div>
            <div className="card p-5 space-y-4">
                <div className="flex items-center justify-between flex-wrap gap-3">
                    <div className="flex items-center gap-2">
                        <div className="section-label">Timeline Scanner</div>
                        <div className="ml-2 flex gap-1 p-1 rounded-xl" style={{ border: '1px solid var(--border)' }}>
                            {[['daily', 'Day'], ['weekly', 'Week'], ['monthly', 'Month']].map(([v, l]) => (
                                <button key={v} onClick={() => scanPreset(v)}
                                    className="px-2.5 py-1 text-[11px] font-bold rounded-lg transition-colors hover:bg-bg1"
                                    style={{ color: 'var(--text-primary)', background: 'var(--bg-elevated)' }}>{l}</button>
                            ))}
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <span className="text-xs" style={{ color: 'var(--text-disabled)' }}>Custom:</span>
                        <input type="number" value={timeVal} onChange={e => setTimeVal(e.target.value)}
                            className="mono text-sm text-center rounded-lg py-1.5 px-2"
                            style={{ width: 52, background: 'var(--bg-overlay)', border: '1px solid var(--border)', color: 'var(--text-primary)' }} />
                        <select value={timeUnit} onChange={e => setTimeUnit(e.target.value)}
                            className="mono text-sm rounded-lg py-1.5 px-3 appearance-none"
                            style={{ background: 'var(--bg-overlay)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}>
                            <option value="hours">Hr</option><option value="days">Day</option><option value="months">Mo</option>
                        </select>
                        <button onClick={scan} className="btn btn-ghost" style={{ fontSize: 11 }}>{loading ? '...' : 'Scan'}</button>
                        {recap && <button onClick={aiSynth} className="btn" style={{ background: 'var(--accent-hover)', color: 'var(--bg-base)', fontSize: 11 }}>{aiLoading ? '...' : 'AI Insights'}</button>}
                    </div>
                </div>
                {recap ? (
                    <div className="text-sm leading-relaxed p-5 rounded-xl md" style={{ background: 'var(--bg-overlay)', color: 'var(--text-primary)', minHeight: 120 }}>
                        {loading ? <div className="shimmer rounded h-4 w-1/2" /> : <div dangerouslySetInnerHTML={{ __html: md(recap) }} />}
                    </div>
                ) : (
                    <div className="py-8 text-center text-sm" style={{ color: 'var(--text-disabled)' }}>Select a range to generate a report</div>
                )}
            </div>
        </div>
    );
};

// ─── EXPORTS ─────────────────────────────────────────────────────────────────
window.AnalyticsPage = AnalyticsPage;
