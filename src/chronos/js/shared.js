// ─── SHARED COMPONENTS ───────────────────────────────────────────────────────
// Requires: utils.js (window.PC)

const { useState, useEffect } = React;
const { motion } = window.Motion;

// ─── CONTEXT MENU ────────────────────────────────────────────────────────────
const CtxMenu = ({ items, pos, onClose }) => {
    useEffect(() => {
        const h = (e) => { if (!e.target.closest('.ctx-menu')) onClose(); };
        setTimeout(() => document.addEventListener('click', h), 0);
        return () => document.removeEventListener('click', h);
    }, [onClose]);
    const style = { top: Math.min(pos.y, window.innerHeight - 300), left: Math.min(pos.x, window.innerWidth - 230) };
    return (
        <div className="ctx-menu float-in" style={style}>
            {items.map((item, i) =>
                item === 'sep'
                    ? <div key={i} className="ctx-sep" />
                    : item.label
                        ? <div key={i} onClick={() => { item.action(); onClose(); }} className={`ctx-item ${item.danger ? 'danger' : ''}`}>
                            <span style={{ opacity: .65, fontSize: 13 }}>{item.icon}</span>
                            {item.label}
                            {item.kbd && <span className="kbd ml-auto">{item.kbd}</span>}
                          </div>
                        : <div key={i} className="ctx-label">{item.heading}</div>
            )}
        </div>
    );
};

// ─── COMPLETE TASK MODAL ─────────────────────────────────────────────────────
const CompleteTaskModal = ({ task, onConfirm, onClose }) => {
    const [custom, setCustom] = useState('');
    const PRESETS = [
        { label: '< 15 min', secs: 14 * 60 },
        { label: '30 min',   secs: 30 * 60 },
        { label: '1 hr',     secs: 3600 },
        { label: '2 hrs',    secs: 7200 },
        { label: '4 hrs',    secs: 14400 },
        { label: '8 hrs',    secs: 28800 },
    ];
    return (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
            <motion.div
                initial={{ y: 20, opacity: 0, scale: 0.97 }}
                animate={{ y: 0, opacity: 1, scale: 1 }}
                transition={{ duration: 0.2, ease: [0.4, 0, 0.2, 1] }}
                className="card p-6 space-y-5 w-full max-w-sm"
                style={{ boxShadow: 'var(--shadow-lg)' }}>
                <div>
                    <h3 className="font-bold text-base" style={{ color: 'var(--text-primary)' }}>Mark Complete ✓</h3>
                    <p className="text-xs mt-1" style={{ color: 'var(--text-disabled)' }}>How long did this actually take?</p>
                    <p className="text-sm mt-2 font-medium truncate" style={{ color: 'var(--text-secondary)' }}>{task.content}</p>
                </div>
                <div className="grid grid-cols-3 gap-2">
                    {PRESETS.map(p => (
                        <button key={p.label} onClick={() => onConfirm(p.secs)}
                            className="py-2.5 px-1 rounded-xl text-xs font-bold transition-all"
                            style={{ background: 'var(--bg-overlay)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
                            {p.label}
                        </button>
                    ))}
                </div>
                <div className="flex items-center gap-2">
                    <input type="number" value={custom} onChange={e => setCustom(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter' && custom) onConfirm(parseInt(custom, 10) * 60); }}
                        className="input-field py-2 text-sm flex-1" placeholder="Custom (min)" min={1} />
                    {custom && (
                        <button onClick={() => onConfirm(parseInt(custom, 10) * 60)} className="btn btn-gold" style={{ fontSize: 11, padding: '8px 14px' }}>OK</button>
                    )}
                </div>
                <div className="flex gap-2.5">
                    <button onClick={() => onConfirm(0)} className="btn btn-ghost flex-1" style={{ fontSize: 11 }}>Skip</button>
                    <button onClick={onClose} className="btn btn-ghost flex-1" style={{ fontSize: 11 }}>Cancel</button>
                </div>
            </motion.div>
        </div>
    );
};

// ─── EXPORTS ─────────────────────────────────────────────────────────────────
Object.assign(window, { CtxMenu, CompleteTaskModal });
