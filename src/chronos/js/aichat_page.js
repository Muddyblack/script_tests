// ─── AI CHAT PAGE ────────────────────────────────────────────────────────────
// Requires: utils.js (window.aiListeners, window.md, window.PC)

const { useState, useEffect, useRef, useCallback } = React;
const { motion, AnimatePresence } = window.Motion;
const { aiListeners, md, PC } = window;

const CHAT_SK = 'chronos_chat_sessions';
const loadStoredSessions = () => {
    try { return JSON.parse(localStorage.getItem(CHAT_SK) || '[]'); }
    catch { return []; }
};

const LoadTasksModal = ({ tasks, onLoad, onClose }) => {
    const pending = tasks.filter(t => t.status !== 'Completed' && t.parent_id === 0);
    const [sel, setSel] = useState([]);
    const toggle = (id) => setSel(p => p.includes(id) ? p.filter(x => x !== id) : [...p, id]);
    const loadSel = () => { onLoad(pending.filter(t => sel.includes(t.id))); onClose(); };
    const loadAll = () => { onLoad(pending); onClose(); };
    return (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
            <motion.div initial={{ y: 20, opacity: 0, scale: 0.97 }} animate={{ y: 0, opacity: 1, scale: 1 }}
                className="card p-5 space-y-4 w-full max-w-md"
                style={{ boxShadow: 'var(--shadow-lg)', maxHeight: '70vh', display: 'flex', flexDirection: 'column' }}>
                <div className="flex items-center justify-between flex-shrink-0">
                    <h3 className="font-bold text-sm" style={{ color: 'var(--text-primary)' }}>Load Tasks into Chat</h3>
                    <button onClick={onClose} className="action-btn">✕</button>
                </div>
                <div className="flex-1 overflow-y-auto space-y-1">
                    {pending.length === 0 && <div className="text-xs text-center py-4" style={{ color: 'var(--text-disabled)' }}>No active tasks</div>}
                    {pending.map(t => (
                        <div key={t.id} onClick={() => toggle(t.id)}
                            className="flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer transition-colors"
                            style={{ background: sel.includes(t.id) ? 'var(--warning-dim)' : 'var(--bg-elevated)', border: `1px solid ${sel.includes(t.id) ? 'var(--warning)' : 'transparent'}` }}>
                            <div style={{ width: 14, height: 14, borderRadius: 4, flexShrink: 0, border: `1.5px solid ${sel.includes(t.id) ? 'var(--warning)' : 'var(--border-light)'}`, background: sel.includes(t.id) ? 'var(--warning)' : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                {sel.includes(t.id) && <span style={{ color: 'var(--bg-base)', fontSize: 9, fontWeight: 900 }}>✓</span>}
                            </div>
                            <span className="text-xs font-medium flex-1 truncate" style={{ color: 'var(--text-primary)' }}>{t.content}</span>
                            <span className="text-xs font-bold" style={{ color: PC[t.priority]?.color, fontSize: 9 }}>{t.priority}</span>
                        </div>
                    ))}
                </div>
                <div className="flex gap-2 flex-shrink-0">
                    <button onClick={loadAll} className="btn btn-ghost flex-1" style={{ fontSize: 11 }}>Load All ({pending.length})</button>
                    <button onClick={loadSel} disabled={!sel.length} className="btn btn-gold flex-1" style={{ fontSize: 11, opacity: sel.length ? 1 : 0.4 }}>
                        Load Selected ({sel.length})
                    </button>
                </div>
            </motion.div>
        </div>
    );
};

const AIChatPage = ({ data, safeCall, pendingTaskCtx, clearPendingTaskCtx }) => {
    const [sessions, setSessions] = useState(loadStoredSessions);
    const [curId, setCurId] = useState(null);
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [showHistory, setShowHistory] = useState(true);
    const [showLoadModal, setShowLoadModal] = useState(false);
    const [histSearch, setHistSearch] = useState('');
    const scrollRef = useRef(null);
    const inputRef = useRef(null);

    const persistSession = useCallback((id, msgs) => {
        const visible = msgs.filter(m => m.role !== 'system');
        if (!visible.length) return;
        const firstUser = msgs.find(m => m.role === 'user')?.content || '';
        const title = (firstUser.slice(0, 50) + (firstUser.length > 50 ? '\u2026' : '')) || 'New chat';
        setSessions(prev => {
            const exists = prev.find(s => s.id === id);
            const updated = exists
                ? prev.map(s => s.id === id ? { ...s, messages: msgs, title } : s)
                : [{ id, title, createdAt: new Date().toISOString(), messages: msgs }, ...prev].slice(0, 50);
            localStorage.setItem(CHAT_SK, JSON.stringify(updated));
            return updated;
        });
    }, []);

    const startNew = useCallback(() => { setCurId('c_' + Date.now()); setMessages([]); }, []);
    const openSession = (s) => { setCurId(s.id); setMessages(s.messages); };

    const deleteSession = (id, e) => {
        e.stopPropagation();
        if (!confirm('Delete this chat?')) return;
        setSessions(prev => {
            const updated = prev.filter(s => s.id !== id);
            localStorage.setItem(CHAT_SK, JSON.stringify(updated));
            return updated;
        });
        if (curId === id) startNew();
    };

    // Handle pendingTaskCtx (from right-click "Ask AI")
    useEffect(() => {
        if (!pendingTaskCtx) return;
        const id = 'c_' + Date.now();
        const msgs = [
            { role: 'system', content: `Task context:\n\n${pendingTaskCtx}` },
            { role: 'assistant', content: 'Got it \u2014 task loaded. What do you want to dig into?' }
        ];
        setCurId(id);
        setMessages(msgs);
        clearPendingTaskCtx?.();
    }, [pendingTaskCtx]);

    // Listen for AI responses
    useEffect(() => {
        const handler = (reqId, text) => {
            if (!reqId.startsWith('chat_')) return;
            setMessages(prev => {
                const updated = [...prev, { role: 'assistant', content: text }];
                if (curId) persistSession(curId, updated);
                return updated;
            });
            setLoading(false);
        };
        aiListeners.add(handler);
        return () => aiListeners.delete(handler);
    }, [curId, persistSession]);

    useEffect(() => {
        if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }, [messages]);

    const sendMsg = () => {
        const text = input.trim();
        if (!text || loading) return;
        const id = curId || ('c_' + Date.now());
        if (!curId) setCurId(id);
        const updated = [...messages, { role: 'user', content: text }];
        setMessages(updated);
        setInput('');
        setLoading(true);
        persistSession(id, updated);
        const reqId = 'chat_' + Date.now();
        safeCall('send_ai_chat', JSON.stringify(updated.map(m => ({ role: m.role, content: m.content }))), reqId);
    };

    const handleLoadTasks = async (selectedTasks) => {
        if (!selectedTasks.length) return;
        const lines = ['## Loaded Tasks'];
        for (const t of selectedTasks) {
            const detail = await safeCall('get_task_detail', t.id);
            if (detail) lines.push(detail);
            else {
                const extra = [];
                if (t.due_date) extra.push(`due:${t.due_date}`);
                if (t.tags?.filter(Boolean).length) extra.push(t.tags.filter(Boolean).map(x => `#${x}`).join(' '));
                lines.push(`- [${t.priority}] ${t.content}${extra.length ? ' (' + extra.join(', ') + ')' : ''}`);
            }
        }
        const sysMsg = { role: 'system', content: lines.join('\n\n') };
        const ack = { role: 'assistant', content: `${selectedTasks.length === 1 ? selectedTasks[0].content : `${selectedTasks.length} tasks`} loaded. What do you want to work on?` };
        setMessages(prev => [...prev, sysMsg, ack]);
    };

    const visibleMsgs = messages.filter(m => m.role !== 'system');
    const hasCtx = messages.some(m => m.role === 'system');

    const fmtSessDate = (iso) => {
        if (!iso) return '';
        const d = new Date(iso), now = new Date();
        const diff = Math.floor((now - d) / 86400000);
        if (diff === 0) return 'Today';
        if (diff === 1) return 'Yesterday';
        if (diff < 7) return `${diff}d ago`;
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    };

    const filteredSessions = sessions.filter(s =>
        !histSearch.trim() ||
        s.title.toLowerCase().includes(histSearch.toLowerCase()) ||
        s.messages?.some(m => m.role !== 'system' && m.content?.toLowerCase().includes(histSearch.toLowerCase()))
    );

    return (
        <div className="flex-1 flex overflow-hidden" style={{ maxWidth: '100%' }}>
            {/* Sessions sidebar */}
            <AnimatePresence>
                {showHistory && (
                    <motion.div initial={{ width: 0, opacity: 0 }} animate={{ width: 220, opacity: 1 }} exit={{ width: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="flex-shrink-0 flex flex-col overflow-hidden"
                        style={{ borderRight: '1px solid var(--border)', background: 'var(--bg-base)' }}>
                        <div className="p-3 flex items-center justify-between flex-shrink-0" style={{ borderBottom: '1px solid var(--border)' }}>
                            <span className="text-xs font-bold" style={{ color: 'var(--text-disabled)' }}>CHATS</span>
                            <button onClick={startNew} className="btn" style={{ fontSize: 10, padding: '4px 10px', background: 'var(--warning)', color: 'var(--bg-base)', borderRadius: 8 }}>+ New</button>
                        </div>
                        <div className="px-2 py-1.5 flex-shrink-0" style={{ borderBottom: '1px solid var(--border)' }}>
                            <input value={histSearch} onChange={e => setHistSearch(e.target.value)}
                                className="w-full text-xs rounded-lg px-2.5 py-1.5"
                                style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
                                placeholder="Search chats..." />
                        </div>
                        <div className="flex-1 overflow-y-auto py-1">
                            {sessions.length === 0 && (
                                <div className="text-xs text-center py-6" style={{ color: 'var(--text-disabled)' }}>No chats yet</div>
                            )}
                            {filteredSessions.map(s => (
                                <div key={s.id} onClick={() => openSession(s)}
                                    className="flex items-start gap-2 px-3 py-2.5 cursor-pointer transition-colors"
                                    style={{ background: curId === s.id ? 'var(--bg-elevated)' : 'transparent', borderLeft: curId === s.id ? '2px solid var(--warning)' : '2px solid transparent' }}>
                                    <div className="flex-1 min-w-0">
                                        <div className="text-xs font-medium truncate" style={{ color: curId === s.id ? 'var(--text-primary)' : 'var(--text-secondary)' }}>{s.title}</div>
                                        <div className="text-xs mt-0.5" style={{ color: 'var(--text-disabled)', fontSize: 10 }}>{fmtSessDate(s.createdAt)}</div>
                                    </div>
                                    <button onClick={(e) => deleteSession(s.id, e)}
                                        className="action-btn flex-shrink-0" style={{ fontSize: 9, padding: 2, opacity: 0.4 }}
                                        onMouseEnter={e => e.currentTarget.style.opacity = 1}
                                        onMouseLeave={e => e.currentTarget.style.opacity = 0.4}>✕</button>
                                </div>
                            ))}
                            {histSearch.trim() && filteredSessions.length === 0 && (
                                <div className="text-xs text-center py-4" style={{ color: 'var(--text-disabled)' }}>No results</div>
                            )}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Main chat area */}
            <div className="flex-1 flex flex-col overflow-hidden">
                <header className="flex items-center justify-between px-6 pt-6 pb-3 flex-shrink-0">
                    <div className="flex items-center gap-3">
                        <button onClick={() => setShowHistory(!showHistory)} className="action-btn" style={{ fontSize: 14 }}>☰</button>
                        <div>
                            <h2 className="text-lg font-bold tracking-tight" style={{ color: 'var(--text-primary)' }}>AI Chat</h2>
                            <p className="text-xs mt-0.5" style={{ color: 'var(--text-disabled)' }}>{data.settings?.ai_model || 'Configure AI in Settings'}</p>
                        </div>
                    </div>
                    <div className="flex gap-2">
                        <button onClick={() => setShowLoadModal(true)} className="btn" style={{ background: 'var(--accent-subtle)', color: 'var(--accent)', fontSize: 11, padding: '6px 14px' }}>
                            {hasCtx ? '+ More Tasks' : 'Load Tasks'}
                        </button>
                        {visibleMsgs.length > 0 && (
                            <button onClick={startNew} className="btn btn-ghost" style={{ fontSize: 11 }}>New Chat</button>
                        )}
                    </div>
                </header>

                <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 pb-4 space-y-3">
                    {visibleMsgs.length === 0 && (
                        <div className="empty" style={{ opacity: 0.5 }}>
                            <div style={{ fontSize: 36 }}>◇</div>
                            <div className="text-sm font-bold" style={{ color: 'var(--text-disabled)' }}>Start a conversation</div>
                            <div className="text-xs" style={{ color: 'var(--text-disabled)', maxWidth: 260, textAlign: 'center', lineHeight: 1.5 }}>
                                Load tasks for context, or just start typing.
                            </div>
                        </div>
                    )}
                    {hasCtx && visibleMsgs.length > 0 && (
                        <div className="text-xs px-3 py-1.5 rounded-lg text-center" style={{ background: 'var(--accent-subtle)', color: 'var(--accent)' }}>
                            Task context loaded
                        </div>
                    )}
                    {visibleMsgs.map((m, i) => (
                        <div key={i} className={`chat-msg ${m.role === 'user' ? 'user' : 'ai'}`}>
                            {m.role === 'assistant'
                                ? <div className="md" dangerouslySetInnerHTML={{ __html: md(m.content) }} />
                                : m.content}
                        </div>
                    ))}
                    {loading && (
                        <div className="chat-msg ai">
                            <div className="shimmer rounded" style={{ height: 14, width: 120 }} />
                        </div>
                    )}
                </div>

                <div className="px-6 pb-6 pt-2 flex-shrink-0">
                    <div className="flex gap-2 items-end">
                        <textarea ref={inputRef} value={input} onChange={e => setInput(e.target.value)}
                            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMsg(); } }}
                            className="input-field flex-1 text-sm resize-none"
                            style={{ minHeight: 42, maxHeight: 120, padding: '10px 14px', border: '1px solid var(--border)', borderRadius: 14 }}
                            placeholder="Ask anything..." rows={1} />
                        <button onClick={sendMsg} disabled={loading || !input.trim()}
                            className="btn" style={{
                                background: input.trim() ? 'var(--accent)' : 'var(--bg-overlay)',
                                color: input.trim() ? 'var(--text-on-accent)' : 'var(--text-disabled)',
                                padding: '10px 18px', borderRadius: 14, fontSize: 12, fontWeight: 700, transition: 'all 0.15s'
                            }}>
                            Send
                        </button>
                    </div>
                </div>
            </div>

            {showLoadModal && (
                <LoadTasksModal tasks={data.tasks} onLoad={handleLoadTasks} onClose={() => setShowLoadModal(false)} />
            )}
        </div>
    );
};

// ─── EXPORTS ─────────────────────────────────────────────────────────────────
Object.assign(window, { AIChatPage, LoadTasksModal });
