// ─── TASKS PAGE COMPONENTS ───────────────────────────────────────────────────
// Requires: utils.js, shared.js

const { useState, useEffect, useCallback, useRef, useMemo, memo } = React;
const { motion, AnimatePresence } = window.Motion;
const { fmt, fmtHuman, fmtRelDate, fmtDate, PC, groupByDate, md, greet, parseLocal } = window;
const { CtxMenu, CompleteTaskModal } = window;

const PAGE_SIZE = 25;

// ─── DAILY FOCUS WIDGET ──────────────────────────────────────────────────────
const DailyFocusWidget = ({ tasks, safeCall }) => {
    const today = useMemo(() => {
        const now = parseLocal(new Date());
        return tasks.filter(t => {
            if (!t.due_date || t.status === 'Completed') return false;
            const d = parseLocal(t.due_date);
            return d.getTime() <= now.getTime();
        });
    }, [tasks]);
    const overdue = useMemo(() => tasks.filter(t => {
        if (!t.due_date || t.status === 'Completed') return false;
        const d = parseLocal(t.due_date);
        const now = parseLocal(new Date());
        return d.getTime() < now.getTime();
    }), [tasks]);

    return (
        <div className="card p-5 space-y-4">
            <div className="flex items-center gap-3">
                <div>
                    <div className="font-bold text-base" style={{ color: 'var(--text-primary)' }}>{greet()}</div>
                    <div className="text-xs" style={{ color: 'var(--text-disabled)' }}>
                        {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
                    </div>
                </div>
            </div>
            {overdue.length > 0 && (
                <div className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold pulse-ring"
                    style={{ background: 'var(--danger-dim)', color: 'var(--danger)', border: '1px solid rgba(232,112,112,0.2)' }}>
                    {overdue.length} overdue
                </div>
            )}
            {today.length > 0 ? (
                <div className="space-y-1.5">
                    <div className="section-label">Today's focus</div>
                    {today.slice(0, 5).map(t => (
                        <div key={t.id} className="flex items-center gap-2 px-2 py-1.5 rounded-lg" style={{ background: 'var(--bg-elevated)' }}>
                            <button onClick={() => safeCall('update_task_status', t.id, 'Completed')}
                                className="check" style={{ width: 14, height: 14, borderRadius: 4 }} />
                            <span className="text-xs font-medium flex-1 truncate" style={{ color: 'var(--text-primary)' }}>{t.content}</span>
                        </div>
                    ))}
                    {today.length > 5 && <div className="text-xs" style={{ color: 'var(--text-disabled)', paddingLeft: 4 }}>+{today.length - 5} more</div>}
                </div>
            ) : (
                <div className="text-xs" style={{ color: 'var(--text-disabled)' }}>No tasks scheduled for today</div>
            )}
        </div>
    );
};

// ─── TASK MODAL (ADD / EDIT) ─────────────────────────────────────────────────
const TaskModal = ({ onSave, onClose, initialTask = null, parentId = 0 }) => {
    const [content, setContent] = useState(initialTask?.content || '');
    const [priority, setPriority] = useState(initialTask?.priority || 'Medium');
    const [dueDate, setDueDate] = useState(initialTask?.due_date || '');
    const [notes, setNotes] = useState(initialTask?.notes || '');
    const [tags, setTags] = useState(initialTask && initialTask.tags ? initialTask.tags.join(', ') : '');
    const [isAch, setIsAch] = useState(initialTask?.is_achievement || false);
    const ref = useRef(null);

    useEffect(() => { ref.current?.focus(); }, []);

    const submit = () => {
        if (!content.trim()) return;
        onSave({
            id: initialTask?.id,
            content: content.trim(),
            priority,
            due_date: dueDate,
            notes,
            tags: tags.split(',').map(t => t.trim()).filter(Boolean),
            parent_id: initialTask ? initialTask.parent_id : parentId,
            is_achievement: isAch,
        });
        onClose();
    };

    return (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
            <motion.div initial={{ y: 20, opacity: 0, scale: 0.97 }} animate={{ y: 0, opacity: 1, scale: 1 }} exit={{ y: 10, opacity: 0, scale: 0.98 }}
                transition={{ duration: 0.22, ease: [0.4, 0, 0.2, 1] }}
                className="card w-full max-w-lg p-6 space-y-5" style={{ boxShadow: 'var(--shadow-lg)' }}>
                <div className="flex items-center justify-between">
                    <h3 className="font-bold text-base" style={{ color: 'var(--text-primary)' }}>
                        {initialTask ? 'Edit Task' : (parentId ? 'Add Subtask' : 'New Task')}
                    </h3>
                    <button onClick={onClose} className="action-btn">✕</button>
                </div>
                <input ref={ref} value={content} onChange={e => setContent(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) submit(); if (e.key === 'Escape') onClose(); }}
                    className="input-field text-[15px] font-medium" placeholder="What needs to get done?" />
                <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-2">
                        <div className="section-label">Priority</div>
                        <div className="flex gap-1.5">
                            {['High', 'Medium', 'Low'].map(p => (
                                <button key={p} onClick={() => setPriority(p)}
                                    className="flex-1 py-2 rounded-xl text-xs font-bold transition-all"
                                    style={{
                                        background: priority === p ? PC[p].bg : 'var(--bg-overlay)',
                                        color: priority === p ? PC[p].color : 'var(--text-disabled)',
                                        border: `1px solid ${priority === p ? PC[p].color + '44' : 'var(--border)'}`,
                                    }}>
                                    {p}
                                </button>
                            ))}
                        </div>
                    </div>
                    <div className="space-y-2">
                        <div className="section-label">Due Date</div>
                        <input type="date" value={dueDate} onChange={e => setDueDate(e.target.value)} className="input-field py-2 text-sm" />
                    </div>
                </div>
                <div className="space-y-2">
                    <div className="section-label">Tags</div>
                    <input value={tags} onChange={e => setTags(e.target.value)} className="input-field py-2.5 text-sm" placeholder="design, backend, review..." />
                </div>
                <div className="space-y-2">
                    <div className="section-label">
                        Notes <span style={{ color: 'var(--text-disabled)', fontWeight: 400, letterSpacing: 0, textTransform: 'none' }}>— markdown ok</span>
                    </div>
                    <textarea value={notes} onChange={e => setNotes(e.target.value)} className="input-field text-sm resize-none" rows={3} placeholder="Context, links, details..." />
                </div>
                {(!parentId && (!initialTask || initialTask.parent_id === 0)) && (
                    <label className="flex items-center gap-3 cursor-pointer px-1">
                        <div className="check" onClick={(e) => { e.preventDefault(); setIsAch(!isAch); }}
                            style={isAch ? { background: 'var(--warning)', borderColor: 'var(--warning)' } : {}}>
                            {isAch && <span style={{ color: 'var(--bg-base)', fontSize: 10, fontWeight: 900 }}>★</span>}
                        </div>
                        <span className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>Mark as achievement / win</span>
                    </label>
                )}
                <div className="flex gap-2.5">
                    <button onClick={onClose} className="btn btn-ghost flex-1">Cancel</button>
                    <button onClick={submit} className="btn btn-gold flex-1" style={{ fontSize: 13 }}>
                        {initialTask ? 'Save Changes' : 'Create'}
                    </button>
                </div>
            </motion.div>
        </div>
    );
};

// ─── TASK NODE ────────────────────────────────────────────────────────────────
const TaskNode = memo(({ task, depth = 0, safeCall, isFocused, onFocus, selMode, isSelected, onSelect, timers, setTimers, onAddSub, onAskAI }) => {
    const [expanded, setExpanded] = useState(false);
    const [localNotes, setLocalNotes] = useState(task.notes || '');
    const [showEdit, setShowEdit] = useState(false);
    const [timerOn, setTimerOn] = useState(false);
    const [ctx, setCtx] = useState(null);
    const [checking, setChecking] = useState(false);
    const [showCompleteModal, setShowCompleteModal] = useState(false);
    const intervalRef = useRef(null);
    const saveRef = useRef(null);
    const isDone = task.status === 'Completed';
    const pc = PC[task.priority] || PC.Medium;
    const due = fmtRelDate(task.due_date);

    useEffect(() => {
        if (task.time_spent && !timers[task.id]) {
            setTimers(p => ({ ...p, [task.id]: task.time_spent }));
        }
    }, [task.id, task.time_spent]);

    useEffect(() => {
        if (timerOn) {
            intervalRef.current = setInterval(() => setTimers(p => ({ ...p, [task.id]: (p[task.id] || 0) + 1 })), 1000);
            saveRef.current = setInterval(() => {
                setTimers(p => { const v = p[task.id]; if (v) safeCall('update_task_time', task.id, v); return p; });
            }, 30000);
        } else {
            clearInterval(intervalRef.current);
            clearInterval(saveRef.current);
            const v = timers[task.id];
            if (v) safeCall('update_task_time', task.id, v);
        }
        return () => { clearInterval(intervalRef.current); clearInterval(saveRef.current); };
    }, [timerOn]);

    const handleCheck = () => {
        if (isDone) {
            setChecking(true);
            setTimeout(() => { safeCall('update_task_status', task.id, 'Pending'); setChecking(false); }, 350);
        } else {
            setShowCompleteModal(true);
        }
    };
    const confirmComplete = (seconds) => {
        setShowCompleteModal(false);
        setChecking(true);
        if (seconds > 0) safeCall('complete_task_with_time', task.id, seconds);
        else safeCall('update_task_status', task.id, 'Completed');
        setTimeout(() => setChecking(false), 350);
    };
    const handleSave = (td) => {
        safeCall('update_task', td.id, td.content, td.notes, task.links || '', td.tags?.join(',') || '', td.priority, td.due_date || '', td.is_achievement);
    };
    const handleCtx = (e) => {
        e.preventDefault(); e.stopPropagation();
        setCtx({ x: Math.min(e.clientX, window.innerWidth - 230), y: Math.min(e.clientY, window.innerHeight - 300) });
    };

    return (
        <div className={`relative ${depth > 0 ? 'ml-6' : ''}`}>
            {depth > 0 && <div style={{ position: 'absolute', left: -12, top: 0, bottom: 0, width: 1, background: 'var(--border)' }} />}
            <div className={`task-row ${isDone ? 'done' : ''} ${isFocused ? 'focused no-dim' : ''} can-dim`}
                style={isFocused ? { boxShadow: 'var(--shadow-md)' } : {}}
                onContextMenu={handleCtx}>
                {!isDone && <div className="priority-stripe" style={{ background: pc.stripe }} />}
                {selMode && (
                    <button onClick={onSelect} style={{
                        width: 16, height: 16, borderRadius: 4, flexShrink: 0, marginTop: 2,
                        border: `1.5px solid ${isSelected ? 'var(--warning)' : 'var(--border-light)'}`,
                        background: isSelected ? 'var(--warning)' : 'transparent',
                        cursor: 'pointer', transition: 'all 0.15s',
                    }}>
                        {isSelected && <span style={{ color: 'var(--bg-base)', fontSize: 9, display: 'block', textAlign: 'center', fontWeight: 900 }}>✓</span>}
                    </button>
                )}
                <button onClick={handleCheck} className={`check mt-0.5 ${isDone ? 'done' : ''} ${checking ? 'check-pop' : ''}`} style={{ flexShrink: 0 }}>
                    {isDone && <span style={{ color: 'var(--bg-base)', fontSize: 10, fontWeight: 900 }}>✓</span>}
                </button>
                <div className="flex-1 min-w-0 space-y-1.5">
                    <div className="flex items-start gap-3">
                        <span className="task-title text-sm font-medium leading-snug cursor-default flex-1"
                            style={{ color: 'var(--text-primary)' }}
                            onClick={() => setExpanded(!expanded)}
                            onDoubleClick={() => setShowEdit(true)}>
                            {task.is_achievement && <span style={{ color: 'var(--warning)', marginRight: 4 }}>★</span>}
                            {task.content}
                        </span>
                        <div className="flex items-center gap-2 flex-shrink-0 mt-0.5">
                            {(timers[task.id] > 0 || task.time_spent > 0) && (
                                <span className={`mono text-xs font-semibold px-2 py-0.5 rounded-lg ${timerOn ? 'breathe' : ''}`}
                                    style={{
                                        background: timerOn ? 'var(--accent-hover-dim)' : 'var(--bg-overlay)',
                                        color: timerOn ? 'var(--accent-hover)' : 'var(--text-disabled)',
                                        border: `1px solid ${timerOn ? 'rgba(184,160,232,0.2)' : 'var(--border)'}`,
                                    }}>
                                    {fmt(timers[task.id] || task.time_spent)}
                                </span>
                            )}
                            <div className="task-actions">
                                <button className="action-btn" onClick={() => setTimerOn(!timerOn)}
                                    style={timerOn ? { background: 'var(--accent-hover-dim)', color: 'var(--accent-hover)' } : {}}>⏱</button>
                                {onFocus && !isFocused && !isDone && <button className="action-btn" onClick={onFocus}>⌖</button>}
                                {isFocused && <button className="action-btn" onClick={onFocus} style={{ color: 'var(--warning)' }}>⌖</button>}
                                <button className="action-btn" onClick={handleCtx}>···</button>
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center gap-2.5 flex-wrap">
                        {task.priority && task.priority !== 'Medium' && (
                            <span className="badge" style={{ background: pc.bg, color: pc.color, fontSize: 9 }}>{pc.label}</span>
                        )}
                        {due && (
                            <span className="text-xs font-semibold flex items-center gap-1"
                                style={{ color: due.cls === 'overdue' ? 'var(--danger)' : due.cls === 'due-soon' ? 'var(--warning)' : 'var(--text-disabled)' }}>
                                {due.label}
                            </span>
                        )}
                        {task.tags && task.tags.filter && task.tags.filter(Boolean).map(tag => (
                            <span key={tag} className="tag">#{tag}</span>
                        ))}
                        {task.children && task.children.length > 0 && (
                            <span className="text-xs mono" style={{ color: 'var(--text-disabled)' }}>
                                {task.children.filter(c => c.status === 'Completed').length}/{task.children.length} done
                            </span>
                        )}
                    </div>
                    {task.children && task.children.length > 0 && (
                        <div className="progress-track" style={{ width: 80 }}>
                            <div className="progress-fill" style={{ width: `${(task.children.filter(c => c.status === 'Completed').length / task.children.length) * 100}%`, background: 'var(--success)' }} />
                        </div>
                    )}
                    <AnimatePresence>
                        {expanded && (
                            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} style={{ overflow: 'hidden' }}>
                                <div className="pt-3 space-y-3">
                                    {task.notes && <div className="md" dangerouslySetInnerHTML={{ __html: md(task.notes) }} />}
                                    <textarea value={localNotes} onChange={e => setLocalNotes(e.target.value)}
                                        onBlur={() => safeCall('update_task', task.id, task.content, localNotes, task.links || '', task.tags?.join(',') || '', task.priority, task.due_date || '', task.is_achievement)}
                                        className="w-full resize-none rounded-xl p-3 text-xs mono"
                                        style={{ background: 'var(--bg-overlay)', border: '1px solid var(--border)', color: 'var(--text-primary)', minHeight: 70, lineHeight: 1.8 }}
                                        placeholder="Add notes... (Markdown supported)" />
                                    <div className="flex items-center gap-2">
                                        <button onClick={() => onAddSub(task.id)} className="btn btn-ghost" style={{ fontSize: 11, padding: '6px 12px' }}>+ Subtask</button>
                                        <button onClick={() => setShowEdit(true)} className="btn btn-ghost" style={{ fontSize: 11, padding: '6px 12px' }}>Edit</button>
                                        <button onClick={() => safeCall('delete_task', task.id)} className="btn btn-danger ml-auto" style={{ fontSize: 11, padding: '6px 12px' }}>Delete</button>
                                    </div>
                                </div>
                            </motion.div>
                        )}
                    </AnimatePresence>
                    {task.children && task.children.length > 0 && (
                        <div className="space-y-0.5 mt-1">
                            {task.children.map(c => (
                                <TaskNode key={c.id} task={c} depth={depth + 1} safeCall={safeCall}
                                    timers={timers} setTimers={setTimers} onAddSub={onAddSub} onAskAI={onAskAI} />
                            ))}
                        </div>
                    )}
                </div>
            </div>
            {ctx && <CtxMenu pos={ctx} onClose={() => setCtx(null)} items={[
                { heading: 'Actions' },
                { icon: '✏', label: 'Edit task', action: () => setShowEdit(true) },
                { icon: '↳', label: 'Add subtask', action: () => onAddSub(task.id) },
                { icon: isDone ? '↩' : '✓', label: isDone ? 'Mark pending' : 'Mark complete', action: () => isDone ? safeCall('update_task_status', task.id, 'Pending') : setShowCompleteModal(true) },
                'sep',
                { icon: task.is_achievement ? '★' : '☆', label: task.is_achievement ? 'Remove achievement' : 'Mark as achievement', action: () => safeCall('update_task_achievement', task.id, !task.is_achievement) },
                { icon: '⌖', label: isFocused ? 'Exit focus' : 'Focus mode', action: onFocus || (() => { }) },
                { icon: '⏱', label: timerOn ? 'Stop timer' : 'Start timer', action: () => setTimerOn(!timerOn) },
                { icon: '◇', label: 'Ask AI about this', action: () => onAskAI?.(task.id) },
                'sep',
                { icon: '✕', label: 'Delete task', danger: true, action: () => safeCall('delete_task', task.id) },
            ]} />}
            {showCompleteModal && <CompleteTaskModal task={task} onConfirm={confirmComplete} onClose={() => setShowCompleteModal(false)} />}
            <AnimatePresence>
                {showEdit && <TaskModal initialTask={task} onClose={() => setShowEdit(false)} onSave={handleSave} />}
            </AnimatePresence>
        </div>
    );
});

// ─── QUICK CAPTURE ───────────────────────────────────────────────────────────
const QuickCapture = ({ onAdd, onClose }) => {
    const [val, setVal] = useState('');
    const [hint, setHint] = useState('');
    const ref = useRef(null);
    useEffect(() => { ref.current?.focus(); }, []);
    const parseQuick = (text) => {
        let content = text, priority = 'Medium', tags = [], due = '', isAch = false;
        const pM = text.match(/!(?:high|h)\b/i); if (pM) { priority = 'High'; content = content.replace(pM[0], ''); }
        const pL = text.match(/!(?:low|l)\b/i); if (pL) { priority = 'Low'; content = content.replace(pL[0], ''); }
        const wM = text.match(/!(?:win|achievement|ach)\b/i); if (wM) { isAch = true; content = content.replace(wM[0], ''); }
        const tagMs = [...text.matchAll(/#(\w+)/g)]; tagMs.forEach(m => { tags.push(m[1]); content = content.replace(m[0], ''); });
        const dM = text.match(/due:(\S+)/i);
        if (dM) {
            const dv = dM[1].toLowerCase();
            const d = new Date();
            if (dv === 'today') due = d.toISOString().slice(0, 10);
            else if (dv === 'tomorrow') { d.setDate(d.getDate() + 1); due = d.toISOString().slice(0, 10); }
            else if (dv.match(/\d{4}-\d{2}-\d{2}/)) due = dv;
            content = content.replace(dM[0], '');
        }
        return { content: content.trim(), priority, tags, due_date: due, is_achievement: isAch };
    };
    useEffect(() => {
        const p = parseQuick(val);
        const hints = [];
        if (p.priority !== 'Medium') hints.push(`${p.priority} priority`);
        if (p.is_achievement) hints.push('achievement');
        if (p.tags.length) hints.push(p.tags.map(t => `#${t}`).join(' '));
        if (p.due_date) hints.push(`due ${p.due_date}`);
        setHint(hints.join(' · '));
    }, [val]);
    const submit = () => { if (!val.trim()) return; onAdd(parseQuick(val)); onClose(); };
    return (
        <div className="modal-overlay" style={{ alignItems: 'flex-end', paddingBottom: '10vh' }} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
            <motion.div initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 20, opacity: 0 }} className="quick-bar">
                <div className="card p-3 space-y-2" style={{ boxShadow: 'var(--shadow-lg)' }}>
                    <div className="flex items-center gap-3">
                        <span style={{ color: 'var(--warning)', fontSize: 18 }}>⚡</span>
                        <input ref={ref} value={val} onChange={e => setVal(e.target.value)}
                            onKeyDown={e => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') onClose(); }}
                            className="flex-1 bg-transparent text-sm font-medium"
                            style={{ color: 'var(--text-primary)' }}
                            placeholder="Quick capture... (!high, #tag, due:tomorrow, !win)" />
                        <kbd className="kbd">↵</kbd>
                    </div>
                    {hint && <div className="text-xs px-7" style={{ color: 'var(--warning)', opacity: 0.7 }}>{hint}</div>}
                    <div className="text-xs px-7" style={{ color: 'var(--text-disabled)' }}>
                        <span className="kbd">!high</span> <span className="kbd">#tag</span> <span className="kbd">due:tomorrow</span> <span className="kbd">!win</span>
                    </div>
                </div>
            </motion.div>
        </div>
    );
};

// ─── MISSIONS PAGE ───────────────────────────────────────────────────────────
const MissionsPage = ({ data, safeCall, focusId, setFocusId, timers, setTimers, onAskAI }) => {
    const [showAdd, setShowAdd] = useState(false);
    const [showQuick, setShowQuick] = useState(false);
    const [addParentId, setAddParentId] = useState(0);
    const [selMode, setSelMode] = useState(false);
    const [selected, setSelected] = useState([]);
    const [view, setView] = useState('list');
    const [filter, setFilter] = useState('all');
    const [showDone, setShowDone] = useState(false);
    const [donePage, setDonePage] = useState(1);
    const [search, setSearch] = useState('');
    const [showSidebar, setShowSidebar] = useState(true);

    useEffect(() => {
        const h = (e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); setShowQuick(true); } };
        window.addEventListener('keydown', h);
        return () => window.removeEventListener('keydown', h);
    }, []);

    const buildTree = (tasks, pid = 0) => tasks.filter(t => t.parent_id === pid).map(t => ({ ...t, children: buildTree(tasks, t.id) }));

    const filtered = useMemo(() => {
        let t = data.tasks.filter(t => {
            if (t.parent_id !== 0) return true;
            return t.status !== 'Completed';
        });
        if (search) {
            const q = search.toLowerCase();
            const matchIds = new Set();
            t.forEach(task => {
                if (task.content.toLowerCase().includes(q) || task.tags?.some(tag => tag.toLowerCase().includes(q))) {
                    matchIds.add(task.id);
                    let pid = task.parent_id;
                    while (pid) { matchIds.add(pid); const p = t.find(x => x.id === pid); pid = p ? p.parent_id : 0; }
                }
            });
            t = t.filter(task => matchIds.has(task.id));
        }
        const now = parseLocal(new Date());
        if (filter === 'today') t = t.filter(t => {
            if (t.parent_id !== 0) return true;
            if (!t.due_date) return false;
            const d = parseLocal(t.due_date);
            return d.getTime() <= now.getTime();
        });
        if (filter === 'high') t = t.filter(t => t.parent_id !== 0 || t.priority === 'High');
        if (filter === 'nodate') t = t.filter(t => t.parent_id !== 0 || !t.due_date);
        return t;
    }, [data.tasks, filter, search]);

    const tree = useMemo(() => buildTree(filtered), [filtered]);
    const groups = useMemo(() => groupByDate(filtered.filter(t => t.parent_id === 0)), [filtered]);
    const done = useMemo(() => [...data.tasks.filter(t => t.status === 'Completed' && t.parent_id === 0)]
        .sort((a, b) => new Date(b.completed_at || 0) - new Date(a.completed_at || 0)), [data.tasks]);
    const pagedDone = done.slice(0, donePage * PAGE_SIZE);

    const stats = useMemo(() => {
        const total = data.tasks.length, comp = data.tasks.filter(t => t.status === 'Completed').length;
        const now = parseLocal(new Date());
        const overdue = data.tasks.filter(t => {
            if (!t.due_date || t.status === 'Completed') return false;
            const d = parseLocal(t.due_date);
            return d.getTime() < now.getTime();
        }).length;
        return { total, comp, active: total - comp, overdue, momentum: total > 0 ? Math.round((comp / total) * 100) : 0 };
    }, [data.tasks]);

    const handleAdd = ({ content, priority, due_date, notes, tags, is_achievement }) => {
        safeCall('add_task', content, 0, notes || '', tags?.join(',') || '', priority, due_date || '', addParentId, is_achievement || false);
    };
    const toggleSel = (id) => setSelected(p => p.includes(id) ? p.filter(x => x !== id) : [...p, id]);
    const bulkAction = (action) => {
        selected.forEach(id => {
            if (action === 'complete') safeCall('update_task_status', id, 'Completed');
            if (action === 'delete') safeCall('delete_task', id);
        });
        setSelected([]); setSelMode(false);
    };

    const FILTERS = [{ id: 'all', l: 'All' }, { id: 'today', l: 'Today' }, { id: 'high', l: 'High' }, { id: 'nodate', l: 'Unscheduled' }];
    const GROUP_COLORS = { Overdue: 'var(--danger)', Today: 'var(--warning)', Tomorrow: 'var(--accent-pressed)', 'This Week': 'var(--success)', Later: 'var(--text-disabled)', 'No Date': 'var(--text-disabled)' };

    return (
        <div className="flex-1 flex overflow-hidden">
            <div className="flex-1 flex flex-col overflow-hidden">
                {/* Header */}
                <div className="flex-shrink-0 px-7 pt-7 pb-4 space-y-4">
                    <div className="flex items-center justify-between gap-4">
                        <div className="flex items-center gap-3">
                            <h2 className="text-xl font-bold tracking-tight" style={{ color: 'var(--text-primary)' }}>Tasks</h2>
                            <span className="section-label">{stats.active} active · {stats.comp} done</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <div className="relative">
                                <span style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-disabled)', fontSize: 13 }}>⌕</span>
                                <input value={search} onChange={e => setSearch(e.target.value)} className="input-field text-sm" style={{ paddingLeft: 30, height: 36, width: 180 }} placeholder="Search..." />
                            </div>
                            <button onClick={() => setShowQuick(true)} className="btn btn-ghost" style={{ fontSize: 11, height: 36, gap: 4 }}>
                                ⚡ Quick <span className="kbd" style={{ fontSize: 9 }}>Ctrl+K</span>
                            </button>
                            <button onClick={() => { setSelMode(!selMode); setSelected([]); }}
                                className="btn btn-ghost" style={{ fontSize: 11, height: 36, background: selMode ? 'var(--warning-dim)' : 'var(--bg-overlay)', color: selMode ? 'var(--warning)' : 'var(--text-secondary)' }}>
                                {selMode ? '✕ Cancel' : '☑ Select'}
                            </button>
                            <button onClick={() => setShowSidebar(!showSidebar)} className="btn btn-ghost" style={{ fontSize: 11, height: 36 }}>⊞</button>
                        </div>
                    </div>
                    {stats.overdue > 0 && (
                        <div className="flex items-center gap-2.5 px-3.5 py-2 rounded-xl text-sm font-semibold pulse-ring"
                            style={{ background: 'var(--danger-dim)', color: 'var(--danger)', border: '1px solid rgba(232,112,112,0.2)' }}>
                            {stats.overdue} overdue {stats.overdue === 1 ? 'task' : 'tasks'}
                        </div>
                    )}
                    <div className="flex items-center gap-2">
                        <div className="flex items-center gap-0.5 p-1 rounded-xl" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}>
                            {FILTERS.map(f => (
                                <button key={f.id} onClick={() => setFilter(f.id)}
                                    className="px-3 py-1.5 rounded-lg text-xs font-bold transition-all"
                                    style={{ background: filter === f.id ? 'var(--bg-base)' : 'transparent', color: filter === f.id ? 'var(--text-primary)' : 'var(--text-disabled)', boxShadow: filter === f.id ? 'var(--shadow-sm)' : 'none' }}>
                                    {f.l}
                                </button>
                            ))}
                        </div>
                        <div className="flex items-center gap-0.5 p-1 rounded-xl ml-auto" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}>
                            {[['list', 'List'], ['grouped', 'Grouped']].map(([v, l]) => (
                                <button key={v} onClick={() => setView(v)}
                                    className="px-3 py-1.5 rounded-lg text-xs font-bold transition-all"
                                    style={{ background: view === v ? 'var(--bg-base)' : 'transparent', color: view === v ? 'var(--text-primary)' : 'var(--text-disabled)' }}>
                                    {l}
                                </button>
                            ))}
                        </div>
                    </div>
                    <div className="space-y-1.5">
                        <div className="flex justify-between text-xs" style={{ color: 'var(--text-disabled)' }}>
                            <span>Momentum</span><span className="mono font-bold" style={{ color: 'var(--warning)' }}>{stats.momentum}%</span>
                        </div>
                        <div className="progress-track" style={{ height: 4 }}>
                            <div className="progress-fill" style={{ width: `${stats.momentum}%`, background: `linear-gradient(90deg, var(--warning), var(--accent-pressed))` }} />
                        </div>
                    </div>
                </div>

                {/* Task list */}
                <div className="flex-1 overflow-y-auto px-5 pb-28 space-y-0.5">
                    {view === 'grouped' ? (
                        Object.entries(groups).filter(([, t]) => t.length > 0).map(([grp, tasks]) => (
                            <div key={grp} className="mb-5">
                                <div className="flex items-center gap-2 px-3 py-2 section-label">
                                    <div style={{ width: 6, height: 6, borderRadius: '50%', background: GROUP_COLORS[grp] || 'var(--text-disabled)', flexShrink: 0 }} />
                                    {grp} <span className="ml-auto">{tasks.length}</span>
                                </div>
                                {buildTree(tasks.concat(data.tasks.filter(t => t.parent_id !== 0))).map(task => (
                                    <TaskNode key={task.id} task={task} safeCall={safeCall}
                                        isFocused={focusId === task.id} onFocus={() => setFocusId(focusId === task.id ? null : task.id)}
                                        selMode={selMode} isSelected={selected.includes(task.id)} onSelect={() => toggleSel(task.id)}
                                        timers={timers} setTimers={setTimers}
                                        onAddSub={(pid) => { setAddParentId(pid); setShowAdd(true); }} onAskAI={onAskAI} />
                                ))}
                            </div>
                        ))
                    ) : tree.length === 0 ? (
                        <div className="empty">
                            <div style={{ fontSize: 40 }}>✓</div>
                            <div className="text-sm font-bold" style={{ color: 'var(--text-disabled)' }}>Clear queue</div>
                            <div className="text-xs" style={{ color: 'var(--text-disabled)' }}>Use ⚡ quick capture or + below</div>
                        </div>
                    ) : (
                        tree.map(task => (
                            <TaskNode key={task.id} task={task} safeCall={safeCall}
                                isFocused={focusId === task.id} onFocus={() => setFocusId(focusId === task.id ? null : task.id)}
                                selMode={selMode} isSelected={selected.includes(task.id)} onSelect={() => toggleSel(task.id)}
                                timers={timers} setTimers={setTimers}
                                onAddSub={(pid) => { setAddParentId(pid); setShowAdd(true); }} onAskAI={onAskAI} />
                        ))
                    )}

                    {done.length > 0 && (
                        <div className="mt-6 pt-4" style={{ borderTop: '1px solid var(--border)' }}>
                            <button onClick={() => setShowDone(!showDone)}
                                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl section-label hover:bg-bg2 transition-colors">
                                <span style={{ transition: 'transform 0.2s', display: 'inline-block', transform: showDone ? 'rotate(90deg)' : 'rotate(0)' }}>▶</span>
                                Completed
                                <span className="ml-auto font-bold">{done.length}</span>
                            </button>
                            <AnimatePresence>
                                {showDone && (
                                    <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} style={{ overflow: 'hidden' }}>
                                        <div className="mt-2 space-y-0.5 opacity-45">
                                            {pagedDone.map(task => (
                                                <div key={task.id} className="flex items-center gap-3 px-3 py-2 rounded-xl hover:bg-bg2 transition-colors">
                                                    <button onClick={() => safeCall('update_task_status', task.id, 'Pending')}
                                                        className="check done" style={{ width: 16, height: 16 }}>
                                                        <span style={{ color: 'var(--bg-base)', fontSize: 9, fontWeight: 900 }}>✓</span>
                                                    </button>
                                                    <span className="text-sm flex-1 line-through" style={{ color: 'var(--text-disabled)' }}>
                                                        {task.is_achievement && <span style={{ color: 'var(--warning)', marginRight: 4 }}>★</span>}
                                                        {task.content}
                                                    </span>
                                                    {task.completed_at && <span className="text-xs mono" style={{ color: 'var(--text-disabled)' }}>{fmtDate(task.completed_at)}</span>}
                                                    <button onClick={() => safeCall('delete_task', task.id)} className="action-btn">✕</button>
                                                </div>
                                            ))}
                                            {pagedDone.length < done.length && (
                                                <button onClick={() => setDonePage(p => p + 1)} className="btn btn-ghost w-full mt-2" style={{ fontSize: 11 }}>
                                                    Show more ({done.length - pagedDone.length} remaining)
                                                </button>
                                            )}
                                        </div>
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </div>
                    )}
                </div>

                {!selMode && (
                    <motion.button onClick={() => { setAddParentId(0); setShowAdd(true); }}
                        whileHover={{ scale: 1.05, boxShadow: '0 12px 40px var(--warning-glow)' }} whileTap={{ scale: 0.96 }}
                        className="fixed bottom-8 right-8 z-50 flex items-center gap-2 font-bold text-sm rounded-2xl px-5 py-3.5"
                        style={{ background: 'var(--warning)', color: 'var(--bg-base)', boxShadow: '0 8px 32px var(--warning-glow)' }}>
                        + New Task
                    </motion.button>
                )}
            </div>

            {/* Right sidebar */}
            <AnimatePresence>
                {showSidebar && (
                    <motion.div initial={{ width: 0, opacity: 0 }} animate={{ width: 280, opacity: 1 }} exit={{ width: 0, opacity: 0 }}
                        transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
                        className="flex-shrink-0 overflow-y-auto overflow-x-hidden"
                        style={{ borderLeft: '1px solid var(--border)', background: 'var(--bg-base)' }}>
                        <div className="p-4 space-y-4 w-[280px]">
                            <DailyFocusWidget tasks={data.tasks} safeCall={safeCall} />
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            <AnimatePresence>
                {showAdd && <TaskModal onClose={() => setShowAdd(false)} parentId={addParentId} onSave={handleAdd} />}
            </AnimatePresence>
            <AnimatePresence>
                {showQuick && <QuickCapture onClose={() => setShowQuick(false)} onAdd={handleAdd} />}
            </AnimatePresence>

            <AnimatePresence>
                {selMode && selected.length > 0 && (
                    <motion.div initial={{ y: 80 }} animate={{ y: 0 }} exit={{ y: 80 }}
                        className="fixed bottom-6 left-1/2 -translate-x-1/2 flex items-center gap-4 px-5 py-3 rounded-2xl z-50"
                        style={{ background: 'var(--bg-base)', border: '1px solid var(--border-light)', boxShadow: 'var(--shadow-lg)' }}>
                        <span className="text-sm font-bold" style={{ color: 'var(--warning)' }}>{selected.length} selected</span>
                        <div style={{ width: 1, height: 18, background: 'var(--border)' }} />
                        <button onClick={() => bulkAction('complete')} className="btn" style={{ background: 'var(--success-dim)', color: 'var(--success)', padding: '7px 14px', fontSize: 11 }}>✓ Complete</button>
                        <button onClick={() => bulkAction('delete')} className="btn" style={{ background: 'var(--danger-dim)', color: 'var(--danger)', padding: '7px 14px', fontSize: 11 }}>✕ Delete</button>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

// ─── EXPORTS ─────────────────────────────────────────────────────────────────
Object.assign(window, { DailyFocusWidget, TaskModal, TaskNode, QuickCapture, MissionsPage, PAGE_SIZE });
