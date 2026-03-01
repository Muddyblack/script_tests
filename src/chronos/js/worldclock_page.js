// ─── WORLD CLOCK PAGE ────────────────────────────────────────────────────────
// No shared utils needed beyond hooks.

const { useState, useEffect, useRef } = React;

const ALL_TIMEZONES = (() => {
    try { return Intl.supportedValuesOf('timeZone'); }
    catch (e) { return ['UTC', 'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles', 'Europe/London', 'Europe/Berlin', 'Europe/Paris', 'Asia/Tokyo', 'Asia/Shanghai', 'Asia/Kolkata', 'Australia/Sydney']; }
})();

const WorldClockPage = ({ data, safeCall }) => {
    const [clocks, setClocks] = useState(data.settings?.world_clocks || []);
    const [now, setNow] = useState(new Date());
    const [adding, setAdding] = useState(false);
    const [search, setSearch] = useState('');
    const searchRef = useRef(null);

    useEffect(() => {
        const iv = setInterval(() => setNow(new Date()), 1000);
        return () => clearInterval(iv);
    }, []);
    useEffect(() => {
        if (data.settings?.world_clocks) setClocks(data.settings.world_clocks);
    }, [data.settings?.world_clocks]);

    const addClock = (tz) => {
        const label = tz.split('/').pop().replace(/_/g, ' ');
        const updated = [...clocks, { label, tz }];
        setClocks(updated);
        safeCall('save_world_clocks', JSON.stringify(updated));
        setAdding(false); setSearch('');
    };
    const removeClock = (idx) => {
        const updated = clocks.filter((_, i) => i !== idx);
        setClocks(updated);
        safeCall('save_world_clocks', JSON.stringify(updated));
    };
    const getTimeInTz = (tz) => {
        try {
            return {
                time: now.toLocaleTimeString('en-US', { timeZone: tz, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }),
                date: now.toLocaleDateString('en-US', { timeZone: tz, weekday: 'short', month: 'short', day: 'numeric' }),
                hour: parseInt(now.toLocaleTimeString('en-US', { timeZone: tz, hour: '2-digit', hour12: false })),
            };
        } catch (e) { return { time: '--:--', date: '', hour: 0 }; }
    };

    const localHour = now.getHours();
    const filteredTz = search ? ALL_TIMEZONES.filter(tz => tz.toLowerCase().includes(search.toLowerCase())).slice(0, 12) : [];

    return (
        <div className="flex-1 overflow-y-auto px-7 py-7 space-y-6 max-w-4xl">
            <header className="flex items-end justify-between">
                <div>
                    <h2 className="text-xl font-bold tracking-tight" style={{ color: 'var(--text-primary)' }}>World Clock</h2>
                    <p className="text-sm mt-0.5" style={{ color: 'var(--text-disabled)' }}>
                        {now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })} local
                    </p>
                </div>
                <button onClick={() => { setAdding(!adding); setTimeout(() => searchRef.current?.focus(), 100); }}
                    className="btn btn-ghost" style={{ fontSize: 11 }}>
                    {adding ? '✕ Cancel' : '+ Add Zone'}
                </button>
            </header>

            {adding && (
                <div className="card p-4 space-y-3">
                    <input ref={searchRef} value={search} onChange={e => setSearch(e.target.value)}
                        className="input-field text-sm" placeholder="Search timezone (e.g. Tokyo, Berlin, New York)..." />
                    {filteredTz.length > 0 && (
                        <div className="space-y-1 max-h-48 overflow-y-auto">
                            {filteredTz.map(tz => {
                                const info = getTimeInTz(tz);
                                return (
                                    <button key={tz} onClick={() => addClock(tz)}
                                        className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm hover:bg-bg2 transition-colors"
                                        style={{ color: 'var(--text-primary)', background: 'transparent', border: 'none', cursor: 'pointer', textAlign: 'left' }}>
                                        <span>{tz.replace(/_/g, ' ')}</span>
                                        <span className="mono text-xs" style={{ color: 'var(--text-disabled)' }}>{info.time}</span>
                                    </button>
                                );
                            })}
                        </div>
                    )}
                </div>
            )}

            {clocks.length > 0 && (
                <div className="card p-5 space-y-4">
                    <div className="flex items-center justify-between mb-2">
                        <div className="section-label">Timeline</div>
                        <div className="flex items-center gap-3 text-xs" style={{ color: 'var(--text-disabled)' }}>
                            <span className="flex items-center gap-1"><div style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--success-dim)', border: '1px solid var(--success)' }} /> Business hours</span>
                            <span className="flex items-center gap-1"><div style={{ width: 2, height: 12, borderRadius: 1, background: 'var(--warning)' }} /> Now</span>
                        </div>
                    </div>
                    <div className="flex items-center" style={{ paddingLeft: 120 }}>
                        <div className="flex-1 flex justify-between mono" style={{ fontSize: 9, color: 'var(--text-disabled)' }}>
                            <span>0</span><span>3</span><span>6</span><span>9</span><span>12</span><span>15</span><span>18</span><span>21</span><span>24</span>
                        </div>
                    </div>
                    {clocks.map((clock, idx) => {
                        const info = getTimeInTz(clock.tz);
                        const hourDiff = info.hour - localHour;
                        const adjustedWorkStart = ((9 - hourDiff + 24) % 24) / 24 * 100;
                        const adjustedWorkEnd = ((17 - hourDiff + 24) % 24) / 24 * 100;
                        const nowPct = (info.hour + now.getMinutes() / 60) / 24 * 100;
                        return (
                            <div key={idx} className="tz-row group">
                                <div style={{ width: 110, flexShrink: 0 }}>
                                    <div className="text-sm font-semibold truncate" style={{ color: 'var(--text-primary)' }}>{clock.label}</div>
                                    <div className="mono text-xs" style={{ color: 'var(--text-disabled)' }}>{info.time}</div>
                                    <div className="text-xs" style={{ color: 'var(--text-disabled)', fontSize: 9 }}>{info.date}</div>
                                </div>
                                <div className="tz-bar">
                                    <div className="tz-bar-bg" />
                                    {adjustedWorkStart < adjustedWorkEnd ? (
                                        <div className="tz-bar-work" style={{ left: `${adjustedWorkStart}%`, width: `${adjustedWorkEnd - adjustedWorkStart}%`, background: 'var(--success-dim)', border: '1px solid rgba(68,255,177,0.2)' }} />
                                    ) : (
                                        <>
                                            <div className="tz-bar-work" style={{ left: `${adjustedWorkStart}%`, right: 0, background: 'var(--success-dim)', border: '1px solid rgba(68,255,177,0.2)' }} />
                                            <div className="tz-bar-work" style={{ left: 0, width: `${adjustedWorkEnd}%`, background: 'var(--success-dim)', border: '1px solid rgba(68,255,177,0.2)' }} />
                                        </>
                                    )}
                                    <div className="tz-bar-now" style={{ left: `${nowPct}%`, background: 'var(--warning)' }} />
                                </div>
                                <button onClick={() => removeClock(idx)} className="action-btn opacity-0 group-hover:opacity-100" style={{ flexShrink: 0 }}>✕</button>
                            </div>
                        );
                    })}
                </div>
            )}

            {clocks.length === 0 && !adding && (
                <div className="empty">
                    <div style={{ fontSize: 40 }}>🌍</div>
                    <div className="text-sm font-bold" style={{ color: 'var(--text-disabled)' }}>No time zones configured</div>
                    <div className="text-xs" style={{ color: 'var(--text-disabled)' }}>Add zones to see the timeline</div>
                </div>
            )}
        </div>
    );
};

// ─── EXPORTS ─────────────────────────────────────────────────────────────────
window.WorldClockPage = WorldClockPage;
