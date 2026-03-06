// ── Details View ──────────────────────────────────────────────────────────────
const SORT_KEYS = { Name: 'name', Type: 'ext', Size: 'size', Modified: 'mtime' };

// Memoized row component to prevent unnecessary re-renders
const FileRow = React.memo(({ file, isSelected, isDragOver, isCut, onSelect, onDouble, onCtxMenu, onDragStart, onDropOnFolder }) => {
    const [localDragOver, setLocalDragOver] = useState(false);
    
    return (
        <tr data-path={file.path}
            className={`file-row ${isSelected ? 'selected' : ''} ${(isDragOver || localDragOver) ? 'drag-over' : ''} ${isCut ? 'cut-item' : ''}`}
            draggable={true}
            onDragStart={e => onDragStart && onDragStart(e, file)}
            onDragOver={file.is_dir ? e => { e.preventDefault(); e.stopPropagation(); setLocalDragOver(true); } : e => e.preventDefault()}
            onDragLeave={file.is_dir ? () => setLocalDragOver(false) : undefined}
            onDrop={file.is_dir ? e => { e.preventDefault(); e.stopPropagation(); setLocalDragOver(false); onDropOnFolder && onDropOnFolder(e, file.path); } : undefined}
            onClick={e => onSelect(file, e)}
            onDoubleClick={() => onDouble(file)}
            onContextMenu={e => { e.preventDefault(); onCtxMenu(e, file); }}>
            <td>
                <FileIcon name={file.name} path={file.path} is_dir={file.is_dir} size={15} className="file-icon" />
                <span className="file-name">{file.name}</span>
                {file.ext && !file.is_dir && <span className="ext-badge">.{file.ext}</span>}
            </td>
            <td style={{ color: 'var(--text-disabled)', fontSize: 11 }}>
                {file.is_dir ? 'Folder' : (file.ext ? file.ext.toUpperCase() : 'File')}
            </td>
            <td style={{ color: 'var(--text-disabled)', fontVariantNumeric: 'tabular-nums' }}>{file.size}</td>
            <td style={{ color: 'var(--text-disabled)', fontVariantNumeric: 'tabular-nums' }}>{file.mtime}</td>
        </tr>
    );
}, (prev, next) => {
    // Custom comparison to prevent re-renders when nothing changed
    return prev.file.path === next.file.path &&
           prev.isSelected === next.isSelected &&
           prev.isDragOver === next.isDragOver &&
           prev.isCut === next.isCut &&
           prev.file.name === next.file.name &&
           prev.file.size === next.file.size &&
           prev.file.mtime === next.file.mtime;
});

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
                    {files.map(f => (
                        <FileRow
                            key={f.path}
                            file={f}
                            isSelected={selected.has(f.path)}
                            isDragOver={dragOverPath === f.path}
                            isCut={cutPaths?.has(f.path)}
                            onSelect={onSelect}
                            onDouble={onDouble}
                            onCtxMenu={onCtxMenu}
                            onDragStart={onDragStart}
                            onDropOnFolder={onDropOnFolder}
                        />
                    ))}
                </tbody>
            </table>
        </div>
    );
};

// ── Icons View ────────────────────────────────────────────────────────────────
const IconItem = React.memo(({ file, isSelected, onSelect, onDouble, onCtxMenu }) => {
    const short = file.name.length > 15 ? file.name.slice(0, 14) + '…' : file.name;
    return (
        <div data-path={file.path} className={`icon-item ${isSelected ? 'selected' : ''}`}
            onClick={e => onSelect(file, e)}
            onDoubleClick={() => onDouble(file)}
            onContextMenu={e => { e.preventDefault(); onCtxMenu(e, file); }}
            title={file.path}>
            <FileIcon name={file.name} path={file.path} is_dir={file.is_dir} size={38} className="big-icon" />
            <span className="icon-name">{short}</span>
        </div>
    );
}, (prev, next) => {
    return prev.file.path === next.file.path &&
           prev.isSelected === next.isSelected &&
           prev.file.name === next.file.name;
});

const IconsView = ({ files, selected, onSelect, onDouble, onCtxMenu }) => (
    <div style={{ flex: 1, overflowY: 'auto' }}>
        <div className="icons-grid">
            {files.slice(0, 800).map(f => (
                <IconItem
                    key={f.path}
                    file={f}
                    isSelected={selected.has(f.path)}
                    onSelect={onSelect}
                    onDouble={onDouble}
                    onCtxMenu={onCtxMenu}
                />
            ))}
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

const TreeNode = React.memo(({ node, depth, selected, onSelect, onDouble, onCtxMenu, expanded, onToggle }) => {
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
}, (prev, next) => {
    const prevExp = prev.expanded.has(prev.node.path);
    const nextExp = next.expanded.has(next.node.path);
    const prevSel = prev.selected.has(prev.node.path);
    const nextSel = next.selected.has(next.node.path);
    
    return prev.node.path === next.node.path &&
           prev.depth === next.depth &&
           prevExp === nextExp &&
           prevSel === nextSel &&
           prev.node.children.length === next.node.children.length;
});

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
