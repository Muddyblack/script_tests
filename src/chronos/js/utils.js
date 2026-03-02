// ─── UTILS & SHARED STATE ────────────────────────────────────────────────────
// All symbols are placed on `window` so Babel-eval'd files can access them.
// This file uses no JSX — it can be loaded as a plain <script> or text/babel.

const { useState, useEffect, useCallback, useRef } = React;

const parseLocal = (iso) => {
    if (!iso) return null;
    const d = new Date(iso);
    if (iso.length === 10) {
        const [y, m, day] = iso.split('-').map(Number);
        d.setFullYear(y, m - 1, day);
    }
    d.setHours(0, 0, 0, 0, 0);
    return d;
};

tailwind.config = {
    theme: {
        extend: {
            colors: {
                bg: 'var(--bg-base)', bg1: 'var(--bg-base)', bg2: 'var(--bg-elevated)', bg3: 'var(--bg-overlay)',
                text1: 'var(--text-primary)', text2: 'var(--text-secondary)', text3: 'var(--text-disabled)',
                gold: 'var(--warning)', teal: 'var(--accent-pressed)', rose: 'var(--danger)',
                sage: 'var(--success)', lav: 'var(--accent-hover)', sky: 'var(--accent-pressed)',
            }
        }
    }
};

// ─── FORMATTERS ──────────────────────────────────────────────────────────────
const fmt = (s) => {
    if (!s) return '0:00';
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return `${h > 0 ? h + ':' : ''}${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
};
const fmtHuman = (s) => {
    if (!s) return '';
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
};
const fmtDate = (iso) => {
    if (!iso) return null;
    return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};
const fmtRelDate = (iso) => {
    if (!iso) return null;
    const d = parseLocal(iso);
    const now = parseLocal(new Date());
    const diff = Math.round((d - now) / 86400000);
    if (diff < 0) return { label: `${Math.abs(diff)}d overdue`, cls: 'overdue' };
    if (diff === 0) return { label: 'Today', cls: 'due-soon' };
    if (diff === 1) return { label: 'Tomorrow', cls: 'due-soon' };
    if (diff <= 7) return { label: `${diff}d`, cls: '' };
    return { label: fmtDate(iso), cls: '' };
};

// ─── CONSTANTS ────────────────────────────────────────────────────────────────
const PC = {
    High: { color: 'var(--danger)', bg: 'var(--danger-dim)', label: 'High', stripe: 'var(--danger)' },
    Medium: { color: 'var(--warning)', bg: 'var(--warning-dim)', label: 'Med', stripe: 'var(--warning)' },
    Low: { color: 'var(--text-disabled)', bg: 'var(--bg-overlay)', label: 'Low', stripe: 'var(--border-light)' },
};

const groupByDate = (tasks) => {
    const now = parseLocal(new Date());
    const G = { Overdue: [], Today: [], Tomorrow: [], 'This Week': [], Later: [], 'No Date': [] };
    tasks.forEach(t => {
        if (!t.due_date) { G['No Date'].push(t); return; }
        const d = parseLocal(t.due_date);
        const diff = Math.round((d - now) / 86400000);
        if (diff < 0) G.Overdue.push(t);
        else if (diff === 0) G.Today.push(t);
        else if (diff === 1) G.Tomorrow.push(t);
        else if (diff <= 7) G['This Week'].push(t);
        else G.Later.push(t);
    });
    return G;
};

// ─── MARKDOWN RENDERER ───────────────────────────────────────────────────────
const md = (text) => {
    if (!text) return '';
    let h = text
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/^### (.+)/gm, '<h3>$1</h3>').replace(/^## (.+)/gm, '<h2>$1</h2>').replace(/^# (.+)/gm, '<h1>$1</h1>')
        .replace(/^> (.+)/gm, '<blockquote>$1</blockquote>')
        .replace(/^\d+\.\s+(.+)/gm, '<li>$1</li>')
        .replace(/^[-*] (.+)/gm, '<li>$1</li>')
        .replace(/\n\n/g, '</p><p>')
        .replace(/(obsidian:\/\/open\?[^\s<]+)/g, '<a href="$1" class="obsidian-link">Obsidian</a>');
    if (!h.match(/^<[hublp]/)) h = '<p>' + h + '</p>';
    return h;
};

const greet = () => {
    const h = new Date().getHours();
    if (h < 5) return 'Still up?';
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    if (h < 21) return 'Good evening';
    return 'Good night';
};

// ─── TOAST ───────────────────────────────────────────────────────────────────
const showToast = (msg, isError) => {
    const el = document.createElement('div');
    el.className = 'toast' + (isError ? ' error' : '');
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => {
        el.style.opacity = '0';
        el.style.transition = 'opacity 0.3s';
        setTimeout(() => el.remove(), 300);
    }, 2000);
};

// ─── AI LISTENER BUS ─────────────────────────────────────────────────────────
const aiListeners = new Set();

// ─── BRIDGE HOOK ─────────────────────────────────────────────────────────────
const useBridge = () => {
    const [ready, setReady] = useState(false);
    const [data, setData] = useState({ tasks: [], settings: {} });
    const ref = useRef(null);
    const refresh = useCallback(async () => {
        if (!ref.current) return;
        try {
            const r = await ref.current.get_all_data();
            if (r) setData(JSON.parse(r));
        } catch (e) { }
    }, []);
    useEffect(() => {
        const setup = () => {
            if (typeof QWebChannel !== 'undefined' && typeof qt !== 'undefined') {
                new QWebChannel(qt.webChannelTransport, (c) => {
                    ref.current = c.objects.pyBridge;
                    setReady(true);
                    refresh();
                    ref.current.data_updated.connect(refresh);
                    ref.current.ai_response.connect((reqId, text) => {
                        aiListeners.forEach(fn => fn(reqId, text));
                    });
                });
            } else setTimeout(setup, 200);
        };
        setup();
    }, []);
    const call = useCallback(
        async (m, ...a) => { if (ready && ref.current) { try { return await ref.current[m](...a); } catch (e) { } } },
        [ready]
    );
    return { ready, data, refresh, call };
};

// ─── EXPORTS ─────────────────────────────────────────────────────────────────
Object.assign(window, {
    parseLocal,
    fmt, fmtHuman, fmtDate, fmtRelDate,
    PC, groupByDate, md, greet,
    showToast, aiListeners, useBridge,
});
