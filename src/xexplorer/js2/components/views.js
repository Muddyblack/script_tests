// ── Details View ──────────────────────────────────────────────────────────────
const SORT_KEYS = { Name: 'name', Type: 'ext', Size: 'size', Modified: 'mtime' };

const DetailsView = ({ files, selected, onSelect, onDouble, onCtxMenu, sortKey, sortDir, onSort, onDragStart, onDropOnFolder, cutPaths }) => {
    const [dragOverPath, setDragOverPath] = useState(null);
    const cols = [
        { label: 'Name', key: 'name', width: '42%' },
        { label: 'Type', key: 'ext', width: '10%' },
        { label: 'Size', key: 'size', width: '10%' },
        { label: 'Modified', key: 'mtime', width: '38%' },
    ];
    return (
        <div style={{ flex: 1, overflowY: 'auto' }}>
            <table className="details-table">
                <thead>
                    <tr className="details-head">
                        {cols.map(col => (
                            <th key={col.key} style={{ width: col.width }}
                                className={sortKey === col.key ? 'sorted' : ''}
                                onClick={() => onSort(col.key)}>
                                {col.label} {sortKey === col.key ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {files.map(f => {
                        const isSel = selected.has(f.path);
                        return (
                            <tr key={f.path} data-path={f.path}
                                className={`file-row ${isSel ? 'selected' : ''} ${dragOverPath === f.path ? 'drag-over' : ''} ${cutPaths?.has(f.path) ? 'cut-item' : ''}`}
                                draggable={true}
                                onDragStart={e => onDragStart && onDragStart(e, f)}
                                onDragOver={f.is_dir ? e => { e.preventDefault(); e.stopPropagation(); setDragOverPath(f.path); } : e => e.preventDefault()}
                                onDragLeave={f.is_dir ? () => setDragOverPath(null) : undefined}
                                onDrop={f.is_dir ? e => { e.preventDefault(); e.stopPropagation(); setDragOverPath(null); onDropOnFolder && onDropOnFolder(e, f.path); } : undefined}
                                onClick={e => onSelect(f, e)}
                                onDoubleClick={() => onDouble(f)}
                                onContextMenu={e => { e.preventDefault(); onCtxMenu(e, f); }}>
                                <td>
                                    <FileIcon name={f.name} path={f.path} is_dir={f.is_dir} size={15} className="file-icon" />
                                    <span className="file-name">{f.name}</span>
                                    {f.ext && !f.is_dir && <span className="ext-badge">.{f.ext}</span>}
                                </td>
                                <td style={{ color: 'var(--text-disabled)', fontSize: 11 }}>
                                    {f.is_dir ? 'Folder' : (f.ext ? f.ext.toUpperCase() : 'File')}
                                </td>
                                <td style={{ color: 'var(--text-disabled)', fontVariantNumeric: 'tabular-nums' }}>{f.size}</td>
                                <td style={{ color: 'var(--text-disabled)', fontVariantNumeric: 'tabular-nums' }}>{f.mtime}</td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
};

// ── Icons View ────────────────────────────────────────────────────────────────
const IconsView = ({ files, selected, onSelect, onDouble, onCtxMenu }) => (
    <div style={{ flex: 1, overflowY: 'auto' }}>
        <div className="icons-grid">
            {files.slice(0, 800).map(f => {
                const isSel = selected.has(f.path);
                const short = f.name.length > 15 ? f.name.slice(0, 14) + '…' : f.name;
                return (
                    <div key={f.path} data-path={f.path} className={`icon-item ${isSel ? 'selected' : ''}`}
                        onClick={e => onSelect(f, e)}
                        onDoubleClick={() => onDouble(f)}
                        onContextMenu={e => { e.preventDefault(); onCtxMenu(e, f); }}
                        title={f.path}>
                        <FileIcon name={f.name} path={f.path} is_dir={f.is_dir} size={38} className="big-icon" />
                        <span className="icon-name">{short}</span>
                    </div>
                );
            })}
        </div>
    </div>
);

// ── Tree View ─────────────────────────────────────────────────────────────────
function buildTree(files) {
    const nodes = {};
    const roots = [];
    for (const f of files.slice(0, 1500)) {
        const parts = f.path.replace(/\//g, '\\').split('\\').filter(Boolean);
        let path_acc = '';
        for (let i = 0; i < parts.length; i++) {
            path_acc = i === 0 ? parts[0] : path_acc + '\\' + parts[i];
            if (!nodes[path_acc]) {
                const isLast = i === parts.length - 1;
                nodes[path_acc] = {
                    path: path_acc, name: parts[i],
                    is_dir: isLast ? f.is_dir : true,
                    ext: isLast ? f.ext : '',
                    children: [],
                };
                if (i === 0) roots.push(nodes[path_acc]);
                else {
                    const parentPath = parts.slice(0, i).join('\\');
                    if (nodes[parentPath]) nodes[parentPath].children.push(nodes[path_acc]);
                }
            }
        }
    }
    return roots;
}

const TreeNode = ({ node, depth, selected, onSelect, onDouble, onCtxMenu, expanded, onToggle }) => {
    const hasKids = node.children.length > 0;
    const isExp = expanded.has(node.path);
    const isSel = selected.has(node.path);
    return (
        <div className="tree-node">
            <div className={`tree-row ${isSel ? 'selected' : ''}`}
                style={{ paddingLeft: 8 + depth * 16 }}
                onClick={e => { onSelect(node, e); if (hasKids) onToggle(node.path); }}
                onDoubleClick={() => onDouble(node)}
                onContextMenu={e => { e.preventDefault(); onCtxMenu(e, node); }}>
                <span className="tree-expander">
                    {hasKids ? (isExp ? '▾' : '▸') : ''}
                </span>
                <FileIcon name={node.name} path={node.path} is_dir={node.is_dir} size={14} style={{ marginRight: 5 }} />
                <span className="tree-label">{node.name}</span>
            </div>
            {isExp && hasKids && node.children.map(child => (
                <TreeNode key={child.path} node={child} depth={depth + 1}
                    selected={selected} onSelect={onSelect} onDouble={onDouble}
                    onCtxMenu={onCtxMenu} expanded={expanded} onToggle={onToggle} />
            ))}
        </div>
    );
};

const TreeView = ({ files, selected, onSelect, onDouble, onCtxMenu }) => {
    const [expanded, setExpanded] = useState(new Set());
    const roots = useMemo(() => buildTree(files), [files]);
    const toggle = path => setExpanded(prev => {
        const next = new Set(prev);
        if (next.has(path)) next.delete(path); else next.add(path);
        return next;
    });
    return (
        <div style={{ flex: 1, overflowY: 'auto', padding: '4px 4px' }} className="tree-root">
            {roots.map(n => <TreeNode key={n.path} node={n} depth={0}
                selected={selected} onSelect={onSelect} onDouble={onDouble}
                onCtxMenu={onCtxMenu} expanded={expanded} onToggle={toggle} />)}
        </div>
    );
};
