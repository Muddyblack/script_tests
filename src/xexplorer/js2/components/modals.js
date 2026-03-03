// ── Confirm Modal ─────────────────────────────────────────────────────────────
const ConfirmModal = ({ title, message, confirmLabel = 'OK', danger = false, onConfirm, onClose }) => {
    const btnCls = danger ? 'btn btn-danger' : 'btn btn-primary';
    return (
        <Modal onClose={onClose}>
            <div className="modal-header">
                <span>{title}</span>
                <button className="modal-close" onClick={onClose}>✕</button>
            </div>
            <div className="modal-body">
                <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, whiteSpace: 'pre-line' }}>{message}</p>
            </div>
            <div className="modal-footer">
                <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
                <button className={btnCls} onClick={() => { onConfirm(); onClose(); }}>{confirmLabel}</button>
            </div>
        </Modal>
    );
};

// ── Input Modal ───────────────────────────────────────────────────────────────
const InputModal = ({ title, label, placeholder = '', initial = '', onConfirm, onClose }) => {
    const [val, setVal] = useState(initial);
    const ref = useRef(null);
    useEffect(() => { ref.current?.focus(); if (initial) ref.current?.select(); }, []);
    function submit() { const t = val.trim(); if (t) { onConfirm(t); onClose(); } }
    return (
        <Modal onClose={onClose}>
            <div className="modal-header">
                <span>{title}</span>
                <button className="modal-close" onClick={onClose}>✕</button>
            </div>
            <div className="modal-body">
                {label && <div className="modal-label">{label}</div>}
                <input ref={ref} className="modal-input" value={val} placeholder={placeholder}
                    onChange={e => setVal(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') onClose(); }}
                />
            </div>
            <div className="modal-footer">
                <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
                <button className="btn btn-primary" disabled={!val.trim()} onClick={submit}>OK</button>
            </div>
        </Modal>
    );
};

// ── Rename Dialog ─────────────────────────────────────────────────────────────
const RenameDialog = ({ file, onDone, onClose }) => {
    const [name, setName] = useState(file.name);
    const [err, setErr] = useState('');
    const inputRef = useRef(null);
    useEffect(() => {
        const inp = inputRef.current;
        if (!inp) return;
        inp.focus();
        const dotIdx = !file.is_dir ? file.name.lastIndexOf('.') : -1;
        inp.setSelectionRange(0, dotIdx > 0 ? dotIdx : file.name.length);
    }, []);
    function submit() {
        const trimmed = name.trim();
        if (!trimmed || trimmed === file.name) { onClose(); return; }
        getBridge(async br => {
            const errStr = await br.rename_item(file.path, trimmed);
            if (errStr) { setErr(errStr); return; }
            onDone();
            onClose();
        });
    }
    return (
        <Modal width={380} onClose={onClose}>
            <div className="modal-header">
                <span>✏️ Rename</span>
                <button className="modal-close" onClick={onClose}>✕</button>
            </div>
            <div className="modal-body">
                <div className="modal-file-row">
                    <FileIcon name={file.name} path={file.path} is_dir={file.is_dir} size={20} />
                    <span className="modal-old-name" title={file.path}>{file.name}</span>
                </div>
                <input ref={inputRef} className="modal-input"
                    value={name}
                    onChange={e => { setName(e.target.value); setErr(''); }}
                    onKeyDown={e => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') onClose(); }}
                />
                {err && <div className="modal-err">{err}</div>}
            </div>
            <div className="modal-footer">
                <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
                <button className="btn btn-primary" onClick={submit}
                    disabled={!name.trim() || name.trim() === file.name}>Rename</button>
            </div>
        </Modal>
    );
};

// ── File-op Progress Modal ────────────────────────────────────────────────────
const FileOpModal = ({ ops, onDismiss, onCancel }) => {
    const visible = ops.filter(o => !o.finished || o.errors.length > 0);
    if (!visible.length) return null;
    const op = visible[visible.length - 1];
    const pct = op.total > 0 ? Math.round((op.done / op.total) * 100) : 0;
    const modeLabel = { move: '✂️ Moving', delete: '🗑️ Deleting', copy: '📋 Copying' }[op.mode] || '⚙️ Working';
    const cancelled = op.errors.length === 1 && op.errors[0] === 'Cancelled';
    return (
        <div className={`modal-overlay${op.finished ? '' : ' modal-nonblock'}`}
            onClick={e => { if (op.finished && e.target === e.currentTarget) onDismiss(op.id); }}>
            <div className="modal-box" style={{ width: 430 }} onClick={e => e.stopPropagation()}>
                <div className="modal-header">
                    <span>
                        {modeLabel} {op.sources.length} item{op.sources.length > 1 ? 's' : ''}
                        {op.finished && !op.errors.length ? ' — Done ✅' : ''}
                        {op.finished && cancelled ? ' — Cancelled' : ''}
                    </span>
                </div>
                <div className="modal-body">
                    {op.dest && <div className="modal-dest">→ {op.dest}</div>}
                    {op.current && !op.finished && (
                        <div className="modal-current" title={op.current} style={{ fontSize: '0.78rem', opacity: 0.7, marginBottom: 6, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            ↳ {op.current}
                        </div>
                    )}
                    <div className="modal-progress-track">
                        <div className="modal-progress-fill"
                            style={{ width: `${pct}%`, background: op.errors.length ? 'var(--error,#ef4444)' : undefined }} />
                    </div>
                    <div className="modal-prog-label">{op.done} / {op.total} &nbsp;·&nbsp; {pct}%</div>
                    {op.errors.length > 0 && !cancelled && (
                        <div className="modal-errors">
                            {op.errors.map((e, i) => <div key={i} className="modal-error-item">⚠️ {e}</div>)}
                        </div>
                    )}
                </div>
                <div className="modal-footer">
                    {!op.finished && (
                        <button className="btn btn-danger" onClick={() => onCancel(op.id)}>Cancel</button>
                    )}
                    {op.finished && (
                        <button className="btn btn-primary" onClick={() => onDismiss(op.id)}>Close</button>
                    )}
                </div>
            </div>
        </div>
    );
};
