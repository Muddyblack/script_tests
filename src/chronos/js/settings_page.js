// ─── SETTINGS PAGE ───────────────────────────────────────────────────────────
// Requires: utils.js (window.showToast)

const { useState, useEffect } = React;
const { showToast } = window;

const SettingsPage = ({ data, safeCall }) => {
    const [s, setS] = useState({});
    const [models, setModels] = useState([]);

    useEffect(() => {
        if (data.settings) setS({ ai_provider: 'openai_compat', ...data.settings });
    }, [data.settings]);

    const fetchModels = async () => {
        const r = await safeCall('get_ai_models');
        if (r) { try { setModels(JSON.parse(r)); } catch (e) { } }
    };

    const doExport = async () => {
        const d = await safeCall('export_data');
        if (d) {
            const blob = new Blob([d], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `chronos_export_${new Date().toISOString().slice(0, 10)}.json`;
            a.click();
            URL.revokeObjectURL(url);
        }
    };

    const doClear = async () => {
        if (confirm('Delete all completed tasks? This cannot be undone.')) {
            await safeCall('clear_completed');
        }
    };

    return (
        <div className="flex-1 overflow-y-auto px-7 py-7 max-w-xl">
            <h2 className="text-xl font-bold tracking-tight mb-8" style={{ color: 'var(--text-primary)' }}>Settings</h2>
            <div className="space-y-4">
                {/* Obsidian */}
                <div className="card p-5">
                    <div className="section-label mb-4">Obsidian Sync</div>
                    <div className="settings-row">
                        <div>
                            <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Vault Path</div>
                            <div className="text-xs mt-0.5" style={{ color: 'var(--text-disabled)' }}>{s.obsidian_path || 'No vault linked'}</div>
                        </div>
                        <button onClick={() => safeCall('select_obsidian_path')} className="btn btn-ghost" style={{ fontSize: 11 }}>Browse</button>
                    </div>
                    <div className="settings-row">
                        <div>
                            <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Auto Sync</div>
                            <div className="text-xs mt-0.5" style={{ color: 'var(--text-disabled)' }}>Sync tasks on every change</div>
                        </div>
                        <button onClick={() => setS({ ...s, sync_enabled: !s.sync_enabled })}
                            className="btn btn-ghost"
                            style={{ fontSize: 11, background: s.sync_enabled ? 'var(--success-dim)' : 'var(--bg-overlay)', color: s.sync_enabled ? 'var(--success)' : 'var(--text-disabled)' }}>
                            {s.sync_enabled ? 'Enabled' : 'Disabled'}
                        </button>
                    </div>
                </div>

                {/* AI */}
                <div className="card p-5">
                    <div className="section-label mb-4">AI Configuration</div>
                    <div className="settings-row">
                        <div><div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Provider</div><div className="text-xs mt-0.5" style={{ color: 'var(--text-disabled)' }}>API format to use</div></div>
                        <select value={s.ai_provider} onChange={e => setS({ ...s, ai_provider: e.target.value, ai_model: '' })}
                            className="input-field py-2 text-sm" style={{ width: 220 }}>
                            <option value="openai_compat">OpenAI-compatible (OpenWebUI, Ollama, llama.cpp…)</option>
                            <option value="google_gemini">Google Gemini</option>
                            <option value="anthropic">Anthropic (Claude)</option>
                        </select>
                    </div>
                    <div className="settings-row">
                        <div>
                            <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>API URL</div>
                            <div className="text-xs mt-0.5" style={{ color: 'var(--text-disabled)' }}>
                                {s.ai_provider === 'google_gemini' || s.ai_provider === 'anthropic' ? 'Leave blank for default' : 'Base URL of your server'}
                            </div>
                        </div>
                        <input value={s.ai_url || ''} onChange={e => setS({ ...s, ai_url: e.target.value })}
                            className="input-field py-2 text-sm" style={{ width: 220 }} placeholder="https://..." />
                    </div>
                    <div className="settings-row">
                        <div><div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>API Key</div></div>
                        <input type="password" value={s.ai_key || ''} onChange={e => setS({ ...s, ai_key: e.target.value })}
                            className="input-field py-2 text-sm" style={{ width: 220 }} placeholder="sk-..." />
                    </div>
                    <div className="settings-row">
                        <div><div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Model</div></div>
                        <div className="flex gap-2 items-center">
                            <select value={s.ai_model || ''} onChange={e => setS({ ...s, ai_model: e.target.value })}
                                className="input-field py-2 text-sm" style={{ width: 160 }}>
                                <option value="">Select model...</option>
                                {models.map(m => <option key={m} value={m}>{m}</option>)}
                            </select>
                            <button onClick={fetchModels} className="btn btn-ghost" style={{ fontSize: 11 }}>Refresh</button>
                        </div>
                    </div>
                    {s.ai_provider === 'openai_compat' && (
                        <div className="settings-row">
                            <div>
                                <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>CA Certificate</div>
                                <div className="text-xs mt-0.5" style={{ color: 'var(--text-disabled)' }}>{s.ai_cert_path || 'System default'}</div>
                            </div>
                            <div className="flex gap-2">
                                <button onClick={async () => { const p = await safeCall('select_cert_path'); if (p) setS({ ...s, ai_cert_path: p }); }}
                                    className="btn btn-ghost" style={{ fontSize: 11 }}>Browse</button>
                                {s.ai_cert_path && <button onClick={() => setS({ ...s, ai_cert_path: '' })} className="btn btn-ghost" style={{ fontSize: 11 }}>Clear</button>}
                            </div>
                        </div>
                    )}
                    <div className="settings-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 8 }}>
                        <div>
                            <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>System Prompt</div>
                            <div className="text-xs mt-0.5" style={{ color: 'var(--text-disabled)' }}>Custom instructions for the AI (used in chat &amp; insights)</div>
                        </div>
                        <textarea value={s.ai_system_prompt || ''} onChange={e => setS({ ...s, ai_system_prompt: e.target.value })}
                            className="input-field text-sm resize-none" rows={3} style={{ width: '100%' }}
                            placeholder="e.g. You are a strict productivity coach. Be brief and direct..." />
                    </div>
                </div>

                {/* Data */}
                <div className="card p-5">
                    <div className="section-label mb-4">Data</div>
                    <div className="settings-row">
                        <div><div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Export</div><div className="text-xs mt-0.5" style={{ color: 'var(--text-disabled)' }}>Download all data as JSON</div></div>
                        <button onClick={doExport} className="btn btn-ghost" style={{ fontSize: 11 }}>Export</button>
                    </div>
                    <div className="settings-row">
                        <div><div className="text-sm font-semibold" style={{ color: 'var(--danger)' }}>Clear Completed</div><div className="text-xs mt-0.5" style={{ color: 'var(--text-disabled)' }}>Remove all completed tasks</div></div>
                        <button onClick={doClear} className="btn btn-danger" style={{ fontSize: 11 }}>Clear</button>
                    </div>
                </div>

                <button onClick={async () => {
                        await safeCall('save_settings', JSON.stringify(s));
                        showToast('Settings saved' + (s.ai_model ? ` — model: ${s.ai_model}` : ''));
                    }}
                    className="btn btn-gold w-full" style={{ fontSize: 13, padding: '12px' }}>
                    Save Settings
                </button>
            </div>
        </div>
    );
};

// ─── EXPORTS ─────────────────────────────────────────────────────────────────
window.SettingsPage = SettingsPage;
