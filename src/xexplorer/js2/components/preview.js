// ── Preview Pane ──────────────────────────────────────────────────────────────
const PreviewPane = ({ file, onClose }) => {
    const [preview, setPreview] = useState(null);
    const [page, setPage] = useState(0);
    // Tracks the async key of a background win32com render so we can match
    // the preview_ready event when it fires.
    const loadingKeyRef = useRef(null);

    function fetchPage(path, pageNum) {
        setPreview(null);
        loadingKeyRef.current = null;
        getBridge(async b => {
            const raw = pageNum === 0
                ? await b.get_preview(path)
                : await b.get_preview_page(path, pageNum);
            const parsed = JSON.parse(raw);
            if (parsed.type === 'loading') {
                // Background render in progress — show spinner and wait for signal
                loadingKeyRef.current = parsed.key || null;
            } else {
                loadingKeyRef.current = null;
            }
            setPreview(parsed);
        });
    }

    // Resolve spinner when the background render completes
    useEffect(() => {
        function onReady(e) {
            const data = e.detail;
            if (!loadingKeyRef.current || data.key !== loadingKeyRef.current) return;
            loadingKeyRef.current = null;
            setPreview(data);
        }
        window.addEventListener('xex:preview_ready', onReady);
        return () => window.removeEventListener('xex:preview_ready', onReady);
    }, []);

    useEffect(() => {
        if (!file) return;
        setPage(0);
        fetchPage(file.path, 0);
    }, [file?.path]);

    function goPage(delta) {
        if (!preview?.page_count) return;
        const next = Math.max(0, Math.min(preview.page_count - 1, page + delta));
        if (next === page) return;
        setPage(next);
        fetchPage(file.path, next);
    }

    if (!file) return null;
    const canPage = preview?.page_count > 1;

    return (
        <aside className="preview-pane">
            <div className="preview-header">
                <FileIcon name={file.name} path={file.path} is_dir={file.is_dir} size={18} />
                <span className="preview-filename">{file.name}</span>
                <button className="btn-icon" onClick={onClose}>✕</button>
            </div>
            <div className="preview-body" style={{ flex: 1, overflow: 'auto', padding: preview?.type === 'sheet' ? 0 : 14 }}>
                {!preview && (
                    <div style={{ color: 'var(--text-disabled)', fontSize: 12, padding: 14 }}>Loading preview…</div>
                )}
                {preview?.type === 'pdf' && (
                    <div style={{ textAlign: 'center' }}>
                        <img src={preview.content} alt={`Page ${page + 1}`}
                            style={{ maxWidth: '100%', borderRadius: 6, boxShadow: '0 4px 20px rgba(0,0,0,.3)' }} />
                    </div>
                )}
                {preview?.type === 'slide_image' && (
                    <div style={{ textAlign: 'center' }}>
                        <img src={preview.content} alt={`Slide ${page + 1}`}
                            style={{ maxWidth: '100%', borderRadius: 6, boxShadow: '0 4px 20px rgba(0,0,0,.3)' }} />
                    </div>
                )}
                {preview?.type === 'slide' && (
                    <div className="slide-content"
                        dangerouslySetInnerHTML={{ __html: preview.content }} />
                )}
                {preview?.type === 'docx' && (
                    <div className="slide-content"
                        dangerouslySetInnerHTML={{ __html: preview.content }} />
                )}
                {preview?.type === 'sheet' && (
                    <div style={{ overflow: 'auto', height: '100%', padding: 8 }}
                        dangerouslySetInnerHTML={{ __html: preview.content }} />
                )}
                {preview?.type === 'image' && (
                    <div style={{ textAlign: 'center' }}>
                        <img src={preview.content} alt={file.name} style={{ maxWidth: '100%' }} />
                    </div>
                )}
                {preview?.type === 'text' && (
                    <>
                        <div className="preview-meta">{file.path}</div>
                        <pre className="preview-code">{preview.content}</pre>
                    </>
                )}
                {preview?.type === 'loading' && (
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, paddingTop: 40, color: 'var(--text-disabled)', fontSize: 12 }}>
                        <div className="spin-ring" />
                        <span>{preview.content || 'Rendering…'}</span>
                    </div>
                )}
                {preview?.type === 'error' && (
                    <div style={{ color: 'var(--error,#ef4444)', fontSize: 12 }}>Error: {preview.content}</div>
                )}
                {preview?.type === 'unsupported' && (
                    <div className="empty-state" style={{ height: 'auto', paddingTop: 40 }}>
                        <span className="empty-icon">👁️</span>
                        <span style={{ fontSize: 12, color: 'var(--text-disabled)' }}>{preview.content || 'No preview available'}</span>
                    </div>
                )}
            </div>
            {canPage && (
                <div className="preview-pages">
                    <button className="page-btn" onClick={() => goPage(-1)} disabled={page === 0}>‹</button>
                    <span className="page-label">{preview.label || `${page + 1} / ${preview.page_count}`}</span>
                    <button className="page-btn" onClick={() => goPage(1)} disabled={page >= preview.page_count - 1}>›</button>
                </div>
            )}
        </aside>
    );
};
