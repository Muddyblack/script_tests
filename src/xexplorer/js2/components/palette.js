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
