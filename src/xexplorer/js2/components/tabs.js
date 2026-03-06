// ── Tab helpers ───────────────────────────────────────────────────────────────
const INIT_TAB = (id, browsePath = null) => ({
    id,
    title: browsePath
        ? (browsePath.split(/[/\\]/).filter(Boolean).pop() || browsePath)
        : 'New Tab',
    browsePath,
    browseStack: [],
    forwardStack: [],
    query: '',
    results: [],
    loading: false,
    selected: new Set(),
    selectionAnchor: null,
    previewFile: null,
});

const TabBar = ({ tabs, activeTabId, onSelect, onClose, onNew, onTearOff, onReorder }) => {
    const barRef = useRef(null);
    const [drag, setDrag] = useState(null);
    // drag = { tabId, startX, startY, curX, curY, isTearOff, insertIdx }

    function startDrag(e, tabId) {
        if (e.button !== 0) return;
        e.preventDefault();
        onSelect(tabId);
        const state = {
            tabId, startX: e.clientX, startY: e.clientY,
            curX: e.clientX, curY: e.clientY,
            isTearOff: false, insertIdx: null, moved: false
        };
        setDrag(state);

        const onMove = ev => {
            setDrag(prev => {
                if (!prev) return null;
                const bar = barRef.current?.getBoundingClientRect();
                const dy = bar ? ev.clientY - bar.bottom : 0;
                const dx = Math.abs(ev.clientX - prev.startX);
                const moved = dx > 4 || Math.abs(ev.clientY - prev.startY) > 4;
                const outOfViewport = (
                    ev.clientX < -20 ||
                    ev.clientY < -20 ||
                    ev.clientX > window.innerWidth + 20 ||
                    ev.clientY > window.innerHeight + 20
                );
                const isTearOff = dy > 52 || (bar && ev.clientY < bar.top - 36) || outOfViewport;

                let insertIdx = null;
                if (!isTearOff && barRef.current) {
                    const tabEls = [...barRef.current.querySelectorAll('.tab')];
                    insertIdx = tabEls.length;
                    for (let i = 0; i < tabEls.length; i++) {
                        const r = tabEls[i].getBoundingClientRect();
                        if (ev.clientX < r.left + r.width / 2) { insertIdx = i; break; }
                    }
                }
                return { ...prev, curX: ev.clientX, curY: ev.clientY, isTearOff, insertIdx, moved };
            });
        };

        const onUp = ev => {
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
            setDrag(prev => {
                if (!prev) return null;
                const bar = barRef.current?.getBoundingClientRect();
                const dy = bar ? ev.clientY - bar.bottom : 0;
                const outOfViewport = (
                    ev.clientX < -20 ||
                    ev.clientY < -20 ||
                    ev.clientX > window.innerWidth + 20 ||
                    ev.clientY > window.innerHeight + 20
                );
                const isTearOff = dy > 52 || (bar && ev.clientY < bar.top - 36) || outOfViewport;
                if (prev.moved && isTearOff) {
                    onTearOff(prev.tabId);
                } else if (prev.moved && prev.insertIdx !== null) {
                    onReorder(prev.tabId, prev.insertIdx);
                }
                return null;
            });
        };

        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    }

    const draggingTab = drag ? tabs.find(t => t.id === drag.tabId) : null;

    // compute reorder-preview order
    let displayTabs = tabs;
    if (drag && !drag.isTearOff && drag.insertIdx !== null && drag.moved) {
        const idx = tabs.findIndex(t => t.id === drag.tabId);
        if (idx !== -1) {
            const reordered = [...tabs];
            const [moved] = reordered.splice(idx, 1);
            const target = drag.insertIdx > idx ? drag.insertIdx - 1 : drag.insertIdx;
            reordered.splice(Math.max(0, target), 0, moved);
            displayTabs = reordered;
        }
    }

    return (
        <>
            <div className="tabs-bar" ref={barRef}>
                {displayTabs.map(tab => (
                    <div key={tab.id}
                        className={[
                            'tab',
                            tab.id === activeTabId ? 'active' : '',
                            drag?.tabId === tab.id && drag.isTearOff ? 'tab-tearing' : '',
                            drag?.tabId === tab.id && drag.moved && !drag.isTearOff ? 'tab-dragging' : '',
                        ].join(' ')}
                        onMouseDown={e => startDrag(e, tab.id)}
                        onAuxClick={e => { if (e.button === 1) { e.preventDefault(); onClose(tab.id); } }}>
                        <span className="tab-icon">{tab.browsePath ? '📂' : '🔍'}</span>
                        <span className="tab-label">{tab.title}</span>
                        {tabs.length > 1 && (
                            <button className="tab-close"
                                onMouseDown={e => e.stopPropagation()}
                                onClick={e => { e.stopPropagation(); onClose(tab.id); }}>✕</button>
                        )}
                    </div>
                ))}
                <button className="tab-new" title="New tab (Ctrl+T)" onClick={onNew}>＋</button>
            </div>
            {/* Floating ghost when tearing off */}
            {drag?.isTearOff && draggingTab && (
                <div className="tab-ghost" style={{ left: drag.curX - 70, top: drag.curY - 18 }}>
                    <span className="tab-icon">{draggingTab.browsePath ? '📂' : '🔍'}</span>
                    <span className="tab-label">{draggingTab.title}</span>
                    <span style={{ fontSize: 10, opacity: .6, marginLeft: 6, flexShrink: 0 }}>drop on window to merge · release to detach</span>
                </div>
            )}
        </>
    );
};
