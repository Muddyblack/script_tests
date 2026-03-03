const { useState, useEffect, useCallback, useRef, useMemo, memo } = React;
const { getBridge, fileEmoji, showToast } = window;

// ── Tailwind config ───────────────────────────────────────────────────────────
tailwind.config = {
    theme: {
        extend: {
            colors: {
                bg: 'var(--bg-base)', bg1: 'var(--bg-elevated)', bg2: 'var(--bg-overlay)',
                acc: 'var(--accent)', t1: 'var(--text-primary)', t2: 'var(--text-secondary)', t3: 'var(--text-disabled)',
            }
        }
    }
};

// ── Context Menu ─────────────────────────────────────────────────────────────
const CtxMenu = memo(({ items, pos, onClose }) => {
    useEffect(() => {
        const h = e => { if (!e.target.closest('.ctx-menu')) onClose(); };
        const t = setTimeout(() => document.addEventListener('mousedown', h), 0);
        return () => { clearTimeout(t); document.removeEventListener('mousedown', h); };
    }, [onClose]);

    const top = Math.min(pos.y, window.innerHeight - items.length * 34 - 20);
    const left = Math.min(pos.x, window.innerWidth - 220);

    return (
        <div className="ctx-menu" style={{ top, left }}>
            {items.map((it, i) =>
                it === 'sep'
                    ? <div key={i} className="ctx-sep" />
                    : <div key={i} className={`ctx-item ${it.danger ? 'danger' : ''}`}
                        onClick={() => { it.action(); onClose(); }}>
                        <em className="ctx-icon">{it.icon}</em>
                        {it.label}
                        {it.kbd && <span className="kbd">{it.kbd}</span>}
                    </div>
            )}
        </div>
    );
});

// ── Toggle ────────────────────────────────────────────────────────────────────
const Tog = ({ on, onChange }) => (
    <div className={`tog ${on ? 'on' : ''}`} onClick={() => onChange(!on)}>
        <div className="tog-thumb" />
    </div>
);

// ── Modal shell (shared by every dialog) ─────────────────────────────────────
// Uses onClick so dragging text inside an input never accidentally closes it.
const Modal = ({ width = 380, onClose, children }) => (
    <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
        <div className="modal-box" style={{ width }} onClick={e => e.stopPropagation()}>
            {children}
        </div>
    </div>
);

// ── Drag-resize handle ────────────────────────────────────────────────────────
const Resizer = ({ onDrag }) => {
    const latest = useRef(onDrag);
    useEffect(() => { latest.current = onDrag; }, [onDrag]);

    const handleMouseDown = useCallback(e => {
        e.preventDefault();
        let lastX = e.clientX;
        const handle = e.currentTarget;
        handle.classList.add('dragging');
        const onMove = ev => { const dx = ev.clientX - lastX; lastX = ev.clientX; latest.current(dx); };
        const onUp = () => {
            handle.classList.remove('dragging');
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    }, []);

    return <div className="resize-handle" onMouseDown={handleMouseDown} />;
};
