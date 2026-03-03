// Hash Tool — single-file React app
// Communicates with Python via QWebChannel (pyBridge)

const { useState, useEffect, useCallback, useRef } = React;
const { motion, AnimatePresence } = window.Motion;
const Icons = window.lucide;

// ── Icon wrapper for vanilla lucide (non-React build) ─────────────────────────
// Each icon is a flat array of [tagName, attrs] child pairs.
// SVG wrapper attrs are fixed (viewBox="0 0 24 24", stroke-based).
function Icon({ icon, size = 16, style, className }) {
    if (!icon || !Array.isArray(icon)) return null;
    return React.createElement(
        'svg',
        {
            xmlns: 'http://www.w3.org/2000/svg',
            width: size,
            height: size,
            viewBox: '0 0 24 24',
            fill: 'none',
            stroke: 'currentColor',
            strokeWidth: 2,
            strokeLinecap: 'round',
            strokeLinejoin: 'round',
            style: { flexShrink: 0, display: 'inline-block', ...style },
            className,
            'aria-hidden': 'true',
        },
        ...icon.map(([tag, attrs], i) =>
            React.createElement(tag, { key: i, ...attrs })
        )
    );
}

// ── Bridge (QWebChannel) ─────────────────────────────────────────────────────
let _bridge = null;
let _bridgeReady = false;
const _bridgeCbs = [];

function getBridge(cb) {
    if (_bridgeReady) { cb(_bridge); return; }
    _bridgeCbs.push(cb);
}

if (typeof QWebChannel !== 'undefined') {
    new QWebChannel(qt.webChannelTransport, ch => {
        _bridge = ch.objects.pyBridge;
        _bridgeReady = true;
        _bridgeCbs.forEach(fn => fn(_bridge));
        _bridgeCbs.length = 0;
    });
} else {
    // Browser / dev-mode mock
    setTimeout(() => {
        const MOCK_HASHES = {
            'MD5':    'a87ff679a2f3e71d9181a67b7542122c',
            'SHA-1':  '1b6453892473a467d07372d45eb05abc2031647a',
            'SHA-256': '4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb264bd1566508ef10f',
            'SHA-512': '4dff4ea340f0a823f15d3f4f01ab62eae0e5da579ccb851f8db9dfe84c58b2b37b89903a740e1ee172da793a6e79d560e5f7f9bd058a12a280433ed6fa4609',
        };
        _bridge = {
            hash_file: (p) => { },
            hash_text: (t, k) => JSON.stringify(MOCK_HASHES),
            browse_file: () => 'C:\\mock\\example.txt',
            file_info: (p) => JSON.stringify({ name: 'example.txt', size_str: '1.4 MB', path: p }),
            hash_progress: { connect: () => {} },
            hash_complete: { connect: () => {} },
        };
        _bridgeReady = true;
        _bridgeCbs.forEach(fn => fn(_bridge));
        _bridgeCbs.length = 0;
    }, 50);
}

// ── Constants ─────────────────────────────────────────────────────────────────
const ALGS = ['MD5', 'SHA-1', 'SHA-256', 'SHA-512'];
const EMPTY_HASHES = Object.fromEntries(ALGS.map(a => [a, '']));

const _textEncoder = new TextEncoder();
const _textDecoder = new TextDecoder('utf-8');
const _BASE64_CHUNK = 0x8000;

function encodeBase64(text) {
    if (!text) return '';
    const bytes = _textEncoder.encode(text);
    let binary = '';
    for (let i = 0; i < bytes.length; i += _BASE64_CHUNK) {
        const chunk = bytes.subarray(i, i + _BASE64_CHUNK);
        binary += String.fromCharCode(...chunk);
    }
    return btoa(binary);
}

function decodeBase64(text) {
    if (!text) return '';
    const cleaned = text.replace(/\s+/g, '');
    if (!cleaned) return '';
    const binary = atob(cleaned);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
        bytes[i] = binary.charCodeAt(i);
    }
    return _textDecoder.decode(bytes);
}

function copyText(text) {
    if (!text) return Promise.resolve();
    if (navigator.clipboard?.writeText) {
        return navigator.clipboard.writeText(text);
    }
    return new Promise(resolve => {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', '');
        ta.style.position = 'absolute';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        resolve();
    });
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function useCopyFeedback() {
    const [copied, setCopied] = useState(null);
    const copy = useCallback((alg, text) => {
        if (!text) return;
        navigator.clipboard.writeText(text).catch(() => {
            const ta = document.createElement('textarea');
            ta.value = text;
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
        });
        setCopied(alg);
        setTimeout(() => setCopied(null), 1600);
    }, []);
    return [copied, copy];
}

// ── HashRow ────────────────────────────────────────────────────────────────────
function HashRow({ alg, value, matched, onCopy, isCopied }) {
    const hasValue = Boolean(value);
    return (
        <div className="hash-row float-in">
            <span className="hash-alg-label">{alg}</span>
            <div
                className={`hash-value ${hasValue ? 'filled' : ''} ${matched ? 'matched' : ''}`}
                title={value || '—'}
            >
                {value || '—'}
            </div>
            <button
                className={`btn-copy ${isCopied ? 'copied' : ''}`}
                onClick={() => onCopy(alg, value)}
                disabled={!hasValue}
                title={`Copy ${alg} hash`}
            >
                {isCopied ? '✓ OK' : 'COPY'}
            </button>
        </div>
    );
}

// ── HashRows group ─────────────────────────────────────────────────────────────
function HashRows({ hashes, matchedAlgs }) {
    const [copied, copy] = useCopyFeedback();
    return (
        <div className="hash-rows">
            {ALGS.map(alg => (
                <HashRow
                    key={alg}
                    alg={alg}
                    value={hashes[alg] || ''}
                    matched={matchedAlgs && matchedAlgs.includes(alg)}
                    onCopy={copy}
                    isCopied={copied === alg}
                />
            ))}
        </div>
    );
}

// ── DropZone ───────────────────────────────────────────────────────────────────
function DropZone({ fileInfo, isHashing, onFile, onBrowse }) {
    const [drag, setDrag] = useState(false);

    const handleDragOver = (e) => {
        e.preventDefault();
        e.stopPropagation();
        setDrag(true);
    };
    const handleDragLeave = (e) => {
        e.preventDefault();
        setDrag(false);
    };
    const handleDrop = (e) => {
        e.preventDefault();
        e.stopPropagation();
        setDrag(false);
        const files = e.dataTransfer.files;
        if (files && files[0]) {
            // Chromium / QtWebEngine exposes .path for local files
            const path = files[0].path || files[0].name;
            if (path) onFile(path);
        }
    };

    const zoneClass = [
        'drop-zone',
        drag ? 'active' : '',
        fileInfo ? 'has-file' : '',
    ].filter(Boolean).join(' ');

    return (
        <div
            className={zoneClass}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={onBrowse}
        >
            {isHashing ? (
                <>
                    <div className="drop-zone-icon pulsing" style={{ color: 'var(--accent)' }}>
                        <Icon icon={Icons.Loader2} size={28} style={{ animation: 'spin 1s linear infinite' }} />
                    </div>
                    <div className="drop-zone-hint">Hashing…</div>
                    {fileInfo && (
                        <div className="drop-zone-sub">{fileInfo.name}</div>
                    )}
                </>
            ) : fileInfo ? (
                <>
                    <div className="drop-zone-icon">
                        <Icon icon={Icons.FileCheck2} size={28} />
                    </div>
                    <div className="file-chip">
                        <Icon icon={Icons.File} size={12} />
                        {fileInfo.name}
                    </div>
                    <div className="drop-zone-sub">{fileInfo.size_str} · click or drop to change</div>
                </>
            ) : (
                <>
                    <div className="drop-zone-icon">
                        <Icon icon={Icons.Upload} size={28} />
                    </div>
                    <div className="drop-zone-hint">Drop a file here</div>
                    <div className="drop-zone-sub">or click to browse</div>
                </>
            )}
        </div>
    );
}

// ── File Tab ───────────────────────────────────────────────────────────────────
function FileTab({ fileInfo, fileHashes, progress, isHashing, matchedAlgs, onFile }) {
    const pathRef = useRef(null);

    const handleBrowse = () => {
        getBridge(b => {
            Promise.resolve(b.browse_file()).then(path => {
                if (path) {
                    onFile(path);
                }
            });
        });
    };

    const handlePathEnter = () => {
        const v = pathRef.current?.value?.trim();
        if (v) onFile(v);
    };

    return (
        <div className="tab-content">
            <DropZone
                fileInfo={fileInfo}
                isHashing={isHashing}
                onFile={onFile}
                onBrowse={handleBrowse}
            />

            {/* Path input */}
            <div className="input-row">
                <input
                    ref={pathRef}
                    className="input-field"
                    placeholder="File path — paste or drag above"
                    defaultValue={fileInfo?.path || ''}
                    onKeyDown={e => e.key === 'Enter' && handlePathEnter()}
                    style={{ flex: 1 }}
                />
                <button className="btn btn-primary" onClick={handleBrowse}>
                    <Icon icon={Icons.FolderOpen} size={14} />
                    Browse
                </button>
            </div>

            {/* Progress */}
            {isHashing && (
                <div className="progress-wrap">
                    <div className="progress-bar" style={{ width: `${progress}%` }} />
                </div>
            )}

            {/* Hashes */}
            <div className="card">
                <div className="section-label">Hashes</div>
                <HashRows hashes={fileHashes} matchedAlgs={matchedAlgs} />
            </div>
        </div>
    );
}

// ── Text Tab ───────────────────────────────────────────────────────────────────
function TextTab({ textHashes, matchedAlgs, onTextChange }) {
    const [text, setText] = useState('');
    const [hmacKey, setHmacKey] = useState('');
    const [showHmac, setShowHmac] = useState(false);

    useEffect(() => {
        onTextChange(text, hmacKey);
    }, [text, hmacKey]);

    return (
        <div className="tab-content">
            {/* Text input */}
            <div className="card">
                <div className="section-label">Input text</div>
                <textarea
                    className="input-field"
                    placeholder="Type or paste text here…"
                    value={text}
                    onChange={e => setText(e.target.value)}
                    style={{
                        resize: 'vertical',
                        minHeight: 80,
                        fontFamily: "'JetBrains Mono', monospace",
                        fontSize: 12,
                        lineHeight: 1.6,
                        background: 'var(--bg-control, var(--bg-elevated))',
                    }}
                />
            </div>

            {/* HMAC section */}
            <div className="card">
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: showHmac ? 8 : 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div className="section-label" style={{ marginBottom: 0 }}>HMAC Key</div>
                        {hmacKey && (
                            <div className="hmac-badge">
                                <Icon icon={Icons.KeyRound} size={9} />
                                Active
                            </div>
                        )}
                    </div>
                    <button
                        className="btn btn-ghost"
                        style={{ padding: '4px 12px', fontSize: 10 }}
                        onClick={() => setShowHmac(v => !v)}
                    >
                        {showHmac ? 'Hide' : 'Set HMAC Key'}
                    </button>
                </div>
                {showHmac && (
                    <input
                        className="input-field"
                        placeholder="Leave empty for plain hash…"
                        value={hmacKey}
                        onChange={e => setHmacKey(e.target.value)}
                        type="text"
                        autoComplete="off"
                    />
                )}
            </div>

            {/* Hashes */}
            <div className="card">
                <div className="section-label">Hashes</div>
                <HashRows hashes={textHashes} matchedAlgs={matchedAlgs} />
            </div>
        </div>
    );
}

function Base64Tab({ input, output, error, onInputChange, onEncode, onDecode, onCopy, onClear, copied }) {
    return (
        <div className="tab-content">
            <div className="card b64-card">
                <div className="section-label">Input</div>
                <textarea
                    className="input-field b64-textarea"
                    placeholder="Type text or paste Base64…"
                    value={input}
                    onChange={e => onInputChange(e.target.value)}
                    spellCheck={false}
                />

                <div className="b64-actions">
                    <button className="btn btn-primary" onClick={onEncode}>
                        <Icon icon={Icons.ArrowRight} size={13} style={{ display:'inline', marginRight:5, verticalAlign:'middle' }} />
                        Encode
                    </button>
                    <button className="btn btn-primary" onClick={onDecode}>
                        <Icon icon={Icons.ArrowLeft} size={13} style={{ display:'inline', marginRight:5, verticalAlign:'middle' }} />
                        Decode
                    </button>
                    <div className="b64-spacer" />
                    <button className="btn btn-ghost" onClick={onClear}>
                        Clear
                    </button>
                </div>

                {error && (
                    <div className="verify-status mismatch" style={{ marginBottom: 6 }}>{error}</div>
                )}

                <div className="section-label">Output</div>
                <textarea
                    className="input-field b64-textarea"
                    placeholder="Result appears here…"
                    value={output}
                    readOnly
                />

                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
                    <button
                        className={`btn-copy ${copied ? 'copied' : ''}`}
                        onClick={onCopy}
                        disabled={!output}
                    >
                        {copied ? '✓ COPIED' : 'COPY'}
                    </button>
                </div>
            </div>
        </div>
    );
}

// ── Verify Bar ─────────────────────────────────────────────────────────────────
function VerifyBar({ allHashes }) {
    const [input, setInput] = useState('');

    const check = input.trim().toLowerCase();
    let status = null;
    let matchedAlg = null;

    if (check) {
        for (const alg of ALGS) {
            if (allHashes[alg] && allHashes[alg].toLowerCase() === check) {
                matchedAlg = alg;
                break;
            }
        }
        status = matchedAlg ? 'match' : 'mismatch';
    }

    const inputClass = [
        'input-field',
        status === 'match' ? 'verify-ok' : '',
        status === 'mismatch' ? 'verify-err' : '',
    ].filter(Boolean).join(' ');

    return (
        <div className="verify-section">
            <div className="section-label">Verify hash</div>
            <div className="verify-input-wrap">
                <input
                    className={inputClass}
                    placeholder="Paste expected hash here to verify…"
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    spellCheck={false}
                    style={{ paddingRight: status ? 36 : 12 }}
                />
                {status && (
                    <span className="verify-badge">
                        {status === 'match' ? '✅' : '❌'}
                    </span>
                )}
            </div>
            <div className={`verify-status ${status || ''}`}>
                {status === 'match' && `✓  MATCH — ${matchedAlg}`}
                {status === 'mismatch' && '✗  No match found'}
            </div>
        </div>
    );
}

// ── App ────────────────────────────────────────────────────────────────────────
function App() {
    const [tab, setTab] = useState('file');
    const TAB_ORDER = ['file', 'text', 'base64'];

    const [b64In, setB64In] = useState('');
    const [b64Out, setB64Out] = useState('');
    const [b64Error, setB64Error] = useState('');
    const [b64Copied, setB64Copied] = useState(false);

    const handleB64Change = useCallback(val => {
        setB64In(val);
        setB64Error('');
    }, []);

    const handleEncode = useCallback(() => {
        try {
            setB64Out(encodeBase64(b64In));
            setB64Error('');
        } catch (err) {
            setB64Out('');
            setB64Error(err?.message || 'Encoding failed');
        }
    }, [b64In]);

    const handleDecode = useCallback(() => {
        try {
            setB64Out(decodeBase64(b64In));
            setB64Error('');
        } catch (err) {
            setB64Out('');
            setB64Error(err?.message || 'Invalid Base64 string');
        }
    }, [b64In]);

    const handleB64Copy = useCallback(() => {
        if (!b64Out) return;
        copyText(b64Out);
        setB64Copied(true);
        setTimeout(() => setB64Copied(false), 1400);
    }, [b64Out]);

    const handleB64Clear = useCallback(() => {
        setB64In('');
        setB64Out('');
        setB64Error('');
        setB64Copied(false);
    }, []);

    // File state
    const [fileInfo, setFileInfo] = useState(null);
    const [fileHashes, setFileHashes] = useState(EMPTY_HASHES);
    const [progress, setProgress] = useState(0);
    const [isHashing, setIsHashing] = useState(false);

    // Text state
    const [textHashes, setTextHashes] = useState(EMPTY_HASHES);

    // Verify — combine hashes from the active tab
    const activeHashes = tab === 'file' ? fileHashes : textHashes;

    // Connect bridge signals on mount
    useEffect(() => {
        getBridge(b => {
            b.hash_progress.connect(p => setProgress(p));
            b.hash_complete.connect(json => {
                const result = JSON.parse(json);
                setIsHashing(false);
                if (result.error) {
                    // Show error in drop-zone hint — reset hashes
                    setFileHashes(EMPTY_HASHES);
                    setFileInfo(fi => fi ? { ...fi, name: `Error: ${result.error}` } : null);
                } else {
                    setFileHashes(result);
                }
            });
        });
    }, []);

    // ── File hashing ────────────────────────────────────────────────────────
    const handleFile = useCallback((path) => {
        getBridge(b => {
            // Fetch file metadata first
            Promise.resolve(b.file_info(path))
                .then(infoJson => {
                    const info = JSON.parse(infoJson);
                    if (!info.name) return;  // not a valid file
                    setFileInfo(info);
                    setFileHashes(EMPTY_HASHES);
                    setProgress(0);
                    setIsHashing(true);
                    b.hash_file(path);
                    setTab('file');
                })
                .catch(() => {
                    setFileInfo(null);
                });
        });
    }, []);

    // ── Text hashing ────────────────────────────────────────────────────────
    const handleTextChange = useCallback((text, hmacKey) => {
        if (!text) { setTextHashes(EMPTY_HASHES); return; }
        getBridge(b => {
            Promise.resolve(b.hash_text(text, hmacKey))
                .then(json => {
                    setTextHashes(JSON.parse(json));
                })
                .catch(() => {
                    setTextHashes(EMPTY_HASHES);
                });
        });
    }, []);

    return (
        <div className="app-shell">
            {/* Header */}
            <div className="app-header">
                <div className="app-header-icon">
                    <Icon icon={Icons.Hash} size={16} />
                </div>
                <div>
                    <div className="app-header-title">Hash Tool</div>
                    <div className="app-header-sub">MD5 · SHA-1 · SHA-256 · SHA-512</div>
                </div>
            </div>

            {/* Tab bar */}
            <div className="tab-bar">
                {TAB_ORDER.map(t => (
                    <button
                        key={t}
                        className={`tab-btn ${tab === t ? 'active' : ''}`}
                        onClick={() => setTab(t)}
                    >
                        {t === 'file' && <Icon icon={Icons.File} size={11} style={{ display: 'inline', marginRight: 5, verticalAlign: 'middle' }} />}
                        {t === 'text' && <Icon icon={Icons.Type} size={11} style={{ display: 'inline', marginRight: 5, verticalAlign: 'middle' }} />}
                        {t === 'base64' && <Icon icon={Icons.Code} size={11} style={{ display: 'inline', marginRight: 5, verticalAlign: 'middle' }} />}
                        {t === 'file' ? 'File' : t === 'text' ? 'Text' : 'Base64'}
                    </button>
                ))}
            </div>

            {/* Tab content */}
            <AnimatePresence mode="wait">
                {tab === 'file' && (
                    <motion.div
                        key="file"
                        style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        transition={{ duration: 0.14 }}
                    >
                        <FileTab
                            fileInfo={fileInfo}
                            fileHashes={fileHashes}
                            progress={progress}
                            isHashing={isHashing}
                            matchedAlgs={null}
                            onFile={handleFile}
                        />
                    </motion.div>
                )}
                {tab === 'text' && (
                    <motion.div
                        key="text"
                        style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        transition={{ duration: 0.14 }}
                    >
                        <TextTab
                            textHashes={textHashes}
                            matchedAlgs={null}
                            onTextChange={handleTextChange}
                        />
                    </motion.div>
                )}
                {tab === 'base64' && (
                    <motion.div
                        key="base64"
                        style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        transition={{ duration: 0.14 }}
                    >
                        <Base64Tab
                            input={b64In}
                            output={b64Out}
                            error={b64Error}
                            copied={b64Copied}
                            onInputChange={handleB64Change}
                            onEncode={handleEncode}
                            onDecode={handleDecode}
                            onCopy={handleB64Copy}
                            onClear={handleB64Clear}
                        />
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Verify bar — always visible */}
            <VerifyBar allHashes={activeHashes} />
        </div>
    );
}

// ── Mount ──────────────────────────────────────────────────────────────────────
const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(React.createElement(App));
