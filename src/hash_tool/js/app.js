// Hash Tool — single-file React app (QWebChannel / pyBridge)
const { useState, useEffect, useCallback, useRef, useMemo } = React;
const { motion, AnimatePresence } = window.Motion;
const Icons = window.lucide;

// ── Persistence (via Python bridge → data/nexus_hash_tool.json) ───────────────
function savePrefs(prefs) {
  getBridge((b) => { b.save_settings(JSON.stringify(prefs)); });
}

// ── Icon ──────────────────────────────────────────────────────────────────────
function Icon({ icon, size = 16, style, className }) {
  if (!icon || !Array.isArray(icon)) return null;
  return React.createElement(
    "svg",
    {
      xmlns: "http://www.w3.org/2000/svg",
      width: size,
      height: size,
      viewBox: "0 0 24 24",
      fill: "none",
      stroke: "currentColor",
      strokeWidth: 2,
      strokeLinecap: "round",
      strokeLinejoin: "round",
      style: { flexShrink: 0, display: "inline-block", ...style },
      className,
      "aria-hidden": "true",
    },
    ...icon.map(([tag, attrs], i) =>
      React.createElement(tag, { key: i, ...attrs }),
    ),
  );
}

// ── Bridge ────────────────────────────────────────────────────────────────────
let _bridge = null, _bridgeReady = false, _bridgeCbs = [];
function getBridge(cb) { _bridgeReady ? cb(_bridge) : _bridgeCbs.push(cb); }
if (typeof QWebChannel !== "undefined") {
  new QWebChannel(qt.webChannelTransport, (ch) => {
    _bridge = ch.objects.pyBridge;
    _bridgeReady = true;
    _bridgeCbs.forEach((fn) => fn(_bridge));
    _bridgeCbs.length = 0;
  });
} else {
  console.warn("QWebChannel not available");
}

// ── Constants & utils ─────────────────────────────────────────────────────────
const DEFAULT_ALGS = ["MD5", "SHA-1", "SHA-256", "SHA-512"];
const ALL_ALGS = [
  "MD5", "SHA-1", "SHA-224", "SHA-256", "SHA-384", "SHA-512",
  "SHA3-256", "SHA3-512", "BLAKE2b", "BLAKE2s", "RIPEMD-160",
];

const _enc = new TextEncoder(), _dec = new TextDecoder("utf-8"), _CHUNK = 0x8000;
function encodeBase64(text) {
  if (!text) return "";
  const bytes = _enc.encode(text);
  let bin = "";
  for (let i = 0; i < bytes.length; i += _CHUNK)
    bin += String.fromCharCode(...bytes.subarray(i, i + _CHUNK));
  return btoa(bin);
}
function decodeBase64(text) {
  if (!text) return "";
  const bin = atob(text.replace(/\s+/g, ""));
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return _dec.decode(bytes);
}
function copyText(text) {
  if (!text) return;
  getBridge((b) => {
    if (b && typeof b.copy_to_clipboard === "function") {
      b.copy_to_clipboard(text);
    } else if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text);
    } else {
      const ta = Object.assign(document.createElement("textarea"), { value: text });
      ta.style.cssText = "position:absolute;left:-9999px";
      document.body.appendChild(ta); ta.select();
      document.execCommand("copy"); document.body.removeChild(ta);
    }
  });
}
function useCopyFeedback() {
  const [copied, setCopied] = useState(null);
  const copy = useCallback((key, text) => {
    if (!text) return;
    copyText(text); setCopied(key);
    setTimeout(() => setCopied(null), 1600);
  }, []);
  return [copied, copy];
}

// ── AlgoSelector ──────────────────────────────────────────────────────────────
function AlgoSelector({ selected, onChange }) {
  return (
    <div className="algo-selector">
      <div className="section-label" style={{ marginBottom: 6 }}>Algorithms</div>
      <div className="algo-chips">
        {ALL_ALGS.map((alg) => {
          const on = selected.includes(alg);
          return (
            <button
              key={alg}
              className={`algo-chip ${on ? "active" : ""}`}
              onClick={() => {
                if (on && selected.length === 1) return; // keep at least one
                onChange(on ? selected.filter((a) => a !== alg) : [...selected, alg]);
              }}
            >
              {alg}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── HashRows ──────────────────────────────────────────────────────────────────
function HashRows({ hashes, selected, matchedAlgs }) {
  const [copied, copy] = useCopyFeedback();
  return (
    <div className="hash-rows">
      {selected.map((alg) => {
        const value = hashes[alg] || "";
        return (
          <div key={alg} className="hash-row float-in">
            <span className="hash-alg-label">{alg}</span>
            <div
              className={`hash-value ${value ? "filled" : ""} ${matchedAlgs?.includes(alg) ? "matched" : ""}`}
              title={value || "—"}
            >{value || "—"}</div>
            <button
              className={`btn-copy ${copied === alg ? "copied" : ""}`}
              onClick={() => copy(alg, value)}
              disabled={!value}
              title={`Copy ${alg}`}
            >{copied === alg ? "✓ OK" : "COPY"}</button>
          </div>
        );
      })}
    </div>
  );
}

// ── DropZone ──────────────────────────────────────────────────────────────────
function DropZone({ fileInfo, isHashing, onFile, onBrowse }) {
  const [drag, setDrag] = useState(false);
  const onDragOver = (e) => { e.preventDefault(); e.stopPropagation(); setDrag(true); };
  const onDragLeave = (e) => { e.preventDefault(); setDrag(false); };
  const onDrop = (e) => {
    e.preventDefault(); e.stopPropagation(); setDrag(false);
    const f = e.dataTransfer.files?.[0];
    if (f) onFile(f.path || f.name);
  };
  const cls = ["drop-zone", drag && "active", fileInfo && "has-file"].filter(Boolean).join(" ");
  return (
    <div className={cls} onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop} onClick={onBrowse}>
      {isHashing ? (
        <>
          <div className="drop-zone-icon pulsing" style={{ color: "var(--accent)" }}>
            <Icon icon={Icons.Loader2} size={28} style={{ animation: "spin 1s linear infinite" }} />
          </div>
          <div className="drop-zone-hint">Hashing…</div>
          {fileInfo && <div className="drop-zone-sub">{fileInfo.name}</div>}
        </>
      ) : fileInfo ? (
        <>
          <div className="drop-zone-icon"><Icon icon={Icons.FileCheck2} size={28} /></div>
          <div className="file-chip"><Icon icon={Icons.File} size={12} />{fileInfo.name}</div>
          <div className="drop-zone-sub">{fileInfo.size_str} · click or drop to change</div>
        </>
      ) : (
        <>
          <div className="drop-zone-icon"><Icon icon={Icons.Upload} size={28} /></div>
          <div className="drop-zone-hint">Drop a file here</div>
          <div className="drop-zone-sub">or click to browse</div>
        </>
      )}
    </div>
  );
}

// ── FileTab ───────────────────────────────────────────────────────────────────
function FileTab({ fileInfo, fileHashes, progress, isHashing, matchedAlgs, onFile, selectedAlgs, onAlgsChange }) {
  const pathRef = useRef(null);
  const browse = () => getBridge((b) => Promise.resolve(b.browse_file()).then((p) => p && onFile(p)));
  return (
    <div className="tab-content">
      <DropZone fileInfo={fileInfo} isHashing={isHashing} onFile={onFile} onBrowse={browse} />
      <div className="input-row">
        <input
          ref={pathRef}
          className="input-field"
          placeholder="File path — paste or drag above"
          defaultValue={fileInfo?.path || ""}
          onKeyDown={(e) => e.key === "Enter" && pathRef.current?.value?.trim() && onFile(pathRef.current.value.trim())}
          style={{ flex: 1 }}
        />
        <button className="btn btn-primary" onClick={browse}>
          <Icon icon={Icons.FolderOpen} size={14} /> Browse
        </button>
      </div>
      {isHashing && (
        <div className="progress-wrap">
          <div className="progress-bar" style={{ width: `${progress}%` }} />
        </div>
      )}
      <div className="card">
        <AlgoSelector selected={selectedAlgs} onChange={onAlgsChange} />
      </div>
      <div className="card">
        <div className="section-label">Hashes</div>
        <HashRows hashes={fileHashes} selected={selectedAlgs} matchedAlgs={matchedAlgs} />
      </div>
    </div>
  );
}

// ── TextTab ───────────────────────────────────────────────────────────────────
function TextTab({ textHashes, matchedAlgs, onTextChange, selectedAlgs, onAlgsChange }) {
  const [text, setText] = useState("");
  const [hmacKey, setHmacKey] = useState("");
  const [showHmac, setShowHmac] = useState(false);
  useEffect(() => { onTextChange(text, hmacKey); }, [text, hmacKey]);
  return (
    <div className="tab-content">
      <div className="card">
        <div className="section-label">Input text</div>
        <textarea
          className="input-field"
          placeholder="Type or paste text here…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          style={{ resize: "vertical", minHeight: 80, fontFamily: "'JetBrains Mono', monospace", fontSize: 12, lineHeight: 1.6, background: "var(--bg-control, var(--bg-elevated))" }}
        />
      </div>
      <div className="card">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: showHmac ? 8 : 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div className="section-label" style={{ marginBottom: 0 }}>HMAC Key</div>
            {hmacKey && <div className="hmac-badge"><Icon icon={Icons.KeyRound} size={9} /> Active</div>}
          </div>
          <button className="btn btn-ghost" style={{ padding: "4px 12px", fontSize: 10 }} onClick={() => setShowHmac((v) => !v)}>
            {showHmac ? "Hide" : "Set HMAC Key"}
          </button>
        </div>
        {showHmac && (
          <input className="input-field" placeholder="Leave empty for plain hash…" value={hmacKey} onChange={(e) => setHmacKey(e.target.value)} autoComplete="off" />
        )}
      </div>
      <div className="card">
        <AlgoSelector selected={selectedAlgs} onChange={onAlgsChange} />
      </div>
      <div className="card">
        <div className="section-label">Hashes</div>
        <HashRows hashes={textHashes} selected={selectedAlgs} matchedAlgs={matchedAlgs} />
      </div>
    </div>
  );
}

// ── Base64Tab ─────────────────────────────────────────────────────────────────
function Base64Tab({ input, output, error, onInputChange, onEncode, onDecode, onCopy, onClear, copied }) {
  return (
    <div className="tab-content">
      <div className="card b64-card">
        <div className="section-label">Input</div>
        <textarea className="input-field b64-textarea" placeholder="Type text or paste Base64…" value={input} onChange={(e) => onInputChange(e.target.value)} spellCheck={false} />
        <div className="b64-actions">
          <button className="btn btn-primary" onClick={onEncode}><Icon icon={Icons.ArrowRight} size={13} style={{ display: "inline", marginRight: 5, verticalAlign: "middle" }} /> Encode</button>
          <button className="btn btn-primary" onClick={onDecode}><Icon icon={Icons.ArrowLeft} size={13} style={{ display: "inline", marginRight: 5, verticalAlign: "middle" }} /> Decode</button>
          <div className="b64-spacer" />
          <button className="btn btn-ghost" onClick={onClear}>Clear</button>
        </div>
        {error && <div className="verify-status mismatch" style={{ marginBottom: 6 }}>{error}</div>}
        <div className="section-label">Output</div>
        <textarea className="input-field b64-textarea" placeholder="Result appears here…" value={output} readOnly />
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
          <button className={`btn-copy ${copied ? "copied" : ""}`} onClick={onCopy} disabled={!output}>{copied ? "✓ COPIED" : "COPY"}</button>
        </div>
      </div>
    </div>
  );
}

// ── PwGenTab ──────────────────────────────────────────────────────────────────
const PW_MODES = [
  { id: "random", label: "Random", desc: "KeePass-style, full charset" },
  { id: "leet", label: "Leet", desc: "L0tus_3lum$ style — memorable" },
  { id: "passphrase", label: "Passphrase", desc: "Word-Word-Word style" },
  { id: "pattern", label: "Pattern", desc: "Custom pattern (u l d s w *)" },
];

const DEFAULT_PW_PREFS = {
  mode: "leet",
  length: 20,
  min_length: 0,
  max_length: 0,
  use_upper: true, use_lower: true, use_digits: true, use_symbols: true,
  exclude_ambiguous: false,
  extra_chars: "",
  exclude_chars: "",
  custom_chars: "",
  word_count: 4,
  separator: "-",
  pattern: "wldws",
  custom_words_text: "",
  bundled_words_enabled: false,
  show_hash: false,
  hash_alg: "SHA-256",
  show_b64: false,
};

function PwGenTab({ prefs, onPrefsChange }) {
  const [password, setPassword] = useState("");
  const [entropy, setEntropy] = useState("");
  const [pwHash, setPwHash] = useState("");
  const [generating, setGenerating] = useState(false);
  const [bundledCount, setBundledCount] = useState(0);
  const [copied, copy] = useCopyFeedback();
  const [copiedHash, copyHash] = useCopyFeedback();
  const [copiedB64, copyB64] = useCopyFeedback();
  const pwRef = useRef(null);

  const set = (key, val) => onPrefsChange({ ...prefs, [key]: val });

  // Custom words typed by user (small list, passed to bridge; bundled wordlist is read by bridge directly)
  const customWords = useMemo(() => {
    return prefs.custom_words_text.split(/[\n,]+/).map((w) => w.trim()).filter(Boolean);
  }, [prefs.custom_words_text]);

  const generate = useCallback(() => {
    setGenerating(true);
    const opts = {
      mode: prefs.mode,
      length: prefs.length,
      use_upper: prefs.use_upper,
      use_lower: prefs.use_lower,
      use_digits: prefs.use_digits,
      use_symbols: prefs.use_symbols,
      custom_chars: prefs.custom_chars,
      exclude_ambiguous: prefs.exclude_ambiguous,
      extra_chars: prefs.extra_chars,
      exclude_chars: prefs.exclude_chars,
      word_count: prefs.word_count,
      separator: prefs.separator,
      pattern: prefs.pattern,
      custom_words: customWords,
      use_bundled: prefs.bundled_words_enabled,
      min_length: prefs.min_length,
      max_length: prefs.max_length,
    };
    getBridge((b) => {
      Promise.resolve(b.generate_password(JSON.stringify(opts))).then((json) => {
        const r = JSON.parse(json);
        setGenerating(false);
        if (r.error) { setPassword("Error: " + r.error); setEntropy(""); setPwHash(""); return; }
        setPassword(r.password);
        setEntropy(r.entropy_bits);
        if (pwRef.current) pwRef.current.value = r.password;
        if (prefs.show_hash && r.password) {
          Promise.resolve(b.hash_text(r.password, "", JSON.stringify([prefs.hash_alg]))).then((hj) => {
            const hr = JSON.parse(hj);
            setPwHash(hr[prefs.hash_alg] || "");
          });
        } else {
          setPwHash("");
        }
      });
    });
  }, [prefs, customWords]);


  // Recalculate entropy locally when user edits the password manually
  const onPwEdit = useCallback((e) => {
    const val = e.target.value;
    setPassword(val);
    if (!val) { setEntropy(""); setPwHash(""); return; }
    // Shannon-style: log2(unique_charset_size) * length — honest for manual edits
    const charsets = [
      /[a-z]/.test(val) ? 26 : 0,
      /[A-Z]/.test(val) ? 26 : 0,
      /[0-9]/.test(val) ? 10 : 0,
      /[^a-zA-Z0-9]/.test(val) ? 32 : 0,
    ];
    const poolSize = charsets.reduce((a, b) => a + b, 0) || 1;
    setEntropy((Math.log2(poolSize) * val.length).toFixed(1));
    if (prefs.show_hash) {
      getBridge((b) => {
        Promise.resolve(b.hash_text(val, "", JSON.stringify([prefs.hash_alg]))).then((hj) => {
          const hr = JSON.parse(hj);
          setPwHash(hr[prefs.hash_alg] || "");
        });
      });
    } else {
      setPwHash("");
    }
  }, [prefs.show_hash, prefs.hash_alg]);

  // Auto-generate on mount + fetch bundled word count
  useEffect(() => {
    generate();
    getBridge((b) => {
      Promise.resolve(b.bundled_wordlist_count()).then((n) => setBundledCount(n));
    });
  }, []);

  const entropyColor = !entropy ? "var(--text-disabled)"
    : parseFloat(entropy) >= 80 ? "var(--success, #22c55e)"
      : parseFloat(entropy) >= 50 ? "#f59e0b"
        : "var(--danger, #ef4444)";
  const entropyLabel = !entropy ? "" :
    parseFloat(entropy) >= 80 ? "Strong" :
      parseFloat(entropy) >= 50 ? "Fair" : "Weak";

  const b64pw = useMemo(() => password ? encodeBase64(password) : "", [password]);

  // Contextual tip based on current mode + settings
  const tip = useMemo(() => {
    const bits = parseFloat(entropy) || 0;
    if (bits >= 80) return null; // already strong, no tip needed
    if (prefs.mode === "random") {
      const len = prefs.length;
      // full charset = 95 printable chars → log2(95)≈6.57
      const fullBits = 6.57 * len;
      if (!prefs.use_symbols) return `Enable symbols → +${((6.57 - 5.95) * len).toFixed(0)} bits`;
      if (!prefs.use_upper || !prefs.lower) return "Enable all charsets for full ~6.6 bits/char";
      if (prefs.exclude_ambiguous) return "Disabling 'no ambiguous' adds ~5 more chars to pool";
      const needed = Math.ceil((80 - bits) / 6.57);
      return `+${needed} chars → 80+ bits (try length ${len + needed})`;
    }
    if (prefs.mode === "leet" || prefs.mode === "passphrase") {
      if (!prefs.bundled_words_enabled && bundledCount > 0) {
        const bitsWithBundled = Math.log2(bundledCount) * prefs.word_count;
        return `Enable bundled wordlist → ~${bitsWithBundled.toFixed(0)} bits (${bundledCount.toLocaleString()} words)`;
      }
      const wl = prefs.bundled_words_enabled ? bundledCount : 900;
      const bitsPerWord = wl > 1 ? Math.log2(wl) : 1;
      const needed = Math.ceil((80 - bits) / bitsPerWord);
      if (needed > 0) return `+${needed} word${needed > 1 ? "s" : ""} → 80+ bits`;
      return null;
    }
    if (prefs.mode === "pattern") {
      const wl = prefs.bundled_words_enabled ? bundledCount : 900;
      const bitsPerWord = wl > 1 ? Math.log2(wl) : 1;
      const wCount = (prefs.pattern.match(/w/g) || []).length;
      const needed = Math.ceil((80 - bits) / bitsPerWord);
      return wCount > 0
        ? `Add ${needed} more 'w' token${needed > 1 ? "s" : ""} to pattern → 80+ bits`
        : `Add 'w' tokens to pattern for word entropy (~${bitsPerWord.toFixed(0)} bits each)`;
    }
    return null;
  }, [entropy, prefs, bundledCount]);

  return (
    <div className="tab-content">
      <div className="card pw-compact-card">

        {/* ── Row 1: mode dropdown + entropy + copy + regenerate ── */}
        <div className="pw-topbar">
          <select className="pw-mode-select" value={prefs.mode} onChange={(e) => set("mode", e.target.value)}>
            {PW_MODES.map((m) => <option key={m.id} value={m.id}>{m.label} — {m.desc}</option>)}
          </select>
          {entropy && <span className="pw-entropy" style={{ color: entropyColor, flexShrink: 0 }}>{entropy} bits — {entropyLabel}</span>}
        </div>

        {/* ── Row 2: password output (editable) ── */}
        <div className="pw-result-row" style={{ marginTop: 8 }}>
          <input ref={pwRef} className="pw-result" defaultValue={password} onChange={onPwEdit} spellCheck={false} autoComplete="off" />
          <button className={`btn-copy ${copied === "pw" ? "copied" : ""}`} onClick={() => copy("pw", pwRef.current ? pwRef.current.value : password)} disabled={!password}>
            {copied === "pw" ? "✓ OK" : "COPY"}
          </button>
          <button className="btn btn-primary" style={{ padding: "6px 14px", fontSize: 11, flexShrink: 0 }} onClick={generate} disabled={generating}>
            <Icon icon={generating ? Icons.Loader2 : Icons.RefreshCw} size={12} style={{ display: "inline", marginRight: 5, verticalAlign: "middle", animation: generating ? "spin 1s linear infinite" : "none" }} />
            {generating ? "…" : "New"}
          </button>
        </div>

        {/* ── Hash / B64 outputs (inline, shown when toggled) ── */}
        {prefs.show_hash && pwHash && (
          <div className="pw-result-row" style={{ marginTop: 6 }}>
            <div className="hash-value filled" style={{ fontSize: 10, flex: 1 }}>{prefs.hash_alg}: {pwHash}</div>
            <button className={`btn-copy ${copiedHash === "hash" ? "copied" : ""}`} onClick={() => copyHash("hash", pwHash)}>
              {copiedHash === "hash" ? "✓ OK" : "COPY"}
            </button>
          </div>
        )}
        {prefs.show_b64 && b64pw && (
          <div className="pw-result-row" style={{ marginTop: 6 }}>
            <div className="hash-value filled" style={{ fontSize: 10, flex: 1 }}>b64: {b64pw}</div>
            <button className={`btn-copy ${copiedB64 === "b64" ? "copied" : ""}`} onClick={() => copyB64("b64", b64pw)}>
              {copiedB64 === "b64" ? "✓ OK" : "COPY"}
            </button>
          </div>
        )}

        {tip && (
          <div className="pw-tip">
            <span className="pw-tip-icon">💡</span>{tip}
          </div>
        )}

        <div className="pw-divider" />

        {/* ── Options (mode-specific) ── */}
        <div className="pw-options">

          {prefs.mode === "random" && <>
            <div className="pw-option-row">
              <label className="pw-label">Length</label>
              <input type="range" min={4} max={128} value={prefs.length} onChange={(e) => set("length", parseInt(e.target.value))} className="pw-slider" />
              <span className="pw-val">{prefs.length}</span>
            </div>
            <div className="pw-option-row pw-checks">
              {[["use_upper", "A–Z"], ["use_lower", "a–z"], ["use_digits", "0–9"], ["use_symbols", "!@#…"]].map(([k, l]) => (
                <label key={k} className="pw-check-label"><input type="checkbox" checked={prefs[k]} onChange={(e) => set(k, e.target.checked)} /><span>{l}</span></label>
              ))}
              <label className="pw-check-label"><input type="checkbox" checked={prefs.exclude_ambiguous} onChange={(e) => set("exclude_ambiguous", e.target.checked)} /><span>No ambiguous</span></label>
            </div>
            <div className="pw-option-row">
              <label className="pw-label">Extra</label>
              <input className="input-field" style={{ flex: 1, fontSize: 11 }} placeholder="Extra chars (e.g. €£)" value={prefs.extra_chars} onChange={(e) => set("extra_chars", e.target.value)} />
              <label className="pw-label" style={{ width: "auto", marginLeft: 8 }}>Exclude</label>
              <input className="input-field" style={{ flex: 1, fontSize: 11 }} placeholder="Chars to exclude" value={prefs.exclude_chars} onChange={(e) => set("exclude_chars", e.target.value)} />
            </div>
            <div className="pw-option-row">
              <label className="pw-label">Override</label>
              <input className="input-field" style={{ flex: 1, fontSize: 11 }} placeholder="Use only these chars (overrides above)" value={prefs.custom_chars} onChange={(e) => set("custom_chars", e.target.value)} />
            </div>
          </>}

          {(prefs.mode === "leet" || prefs.mode === "passphrase") && <>
            <div className="pw-option-row">
              <label className="pw-label">Words</label>
              <input type="range" min={2} max={8} value={prefs.word_count} onChange={(e) => set("word_count", parseInt(e.target.value))} className="pw-slider" />
              <span className="pw-val">{prefs.word_count}</span>
              {prefs.mode === "passphrase" && <>
                <label className="pw-label" style={{ width: "auto", marginLeft: 8 }}>Sep</label>
                <input className="input-field" style={{ width: 44, fontSize: 11, textAlign: "center" }} maxLength={3} value={prefs.separator} onChange={(e) => set("separator", e.target.value)} />
              </>}
              {prefs.mode === "leet" && (
                <div className="pw-checks" style={{ marginLeft: 8 }}>
                  {[["use_digits", "+digit"], ["use_symbols", "+sym"]].map(([k, l]) => (
                    <label key={k} className="pw-check-label"><input type="checkbox" checked={prefs[k]} onChange={(e) => set(k, e.target.checked)} /><span>{l}</span></label>
                  ))}
                </div>
              )}
            </div>
          </>}

          {prefs.mode === "pattern" && <>
            <div className="pw-option-row">
              <label className="pw-label">Pattern</label>
              <input className="input-field" style={{ flex: 1, fontSize: 11 }} placeholder="e.g. wdws" value={prefs.pattern} onChange={(e) => set("pattern", e.target.value)} />
            </div>
            <div className="pw-hint">u=upper  l=lower  d=digit  s=symbol  w=word  *=any  · other=literal</div>
          </>}

          {/* Min/Max + words (non-random) */}
          {prefs.mode !== "random" && <>
            <div className="pw-option-row">
              <label className="pw-label">Min len</label>
              <input type="range" min={0} max={128} value={prefs.min_length} onChange={(e) => set("min_length", parseInt(e.target.value))} className="pw-slider" />
              <span className="pw-val">{prefs.min_length > 0 ? prefs.min_length : "off"}</span>
              <label className="pw-label" style={{ width: "auto", marginLeft: 8 }}>Max</label>
              <input type="range" min={0} max={128} value={prefs.max_length} onChange={(e) => set("max_length", parseInt(e.target.value))} className="pw-slider" />
              <span className="pw-val">{prefs.max_length > 0 ? prefs.max_length : "off"}</span>
            </div>
            <div className="pw-option-row" style={{ alignItems: "flex-start" }}>
              <label className="pw-label" style={{ paddingTop: 4 }}>Words+</label>
              <textarea className="input-field" style={{ flex: 1, minHeight: 40, maxHeight: 80, fontSize: 11, resize: "vertical" }}
                placeholder="Extra words (one per line or comma-sep)"
                value={prefs.custom_words_text} onChange={(e) => set("custom_words_text", e.target.value)} />
              <label className="pw-check-label" style={{ flexShrink: 0, marginLeft: 8, alignSelf: "center" }}>
                <input type="checkbox" checked={prefs.bundled_words_enabled} onChange={(e) => set("bundled_words_enabled", e.target.checked)} />
                <span style={{ whiteSpace: "nowrap" }}>{bundledCount > 0 ? `+${bundledCount.toLocaleString()}` : "bundled"}</span>
              </label>
            </div>
          </>}

        </div>

        {/* ── Toggle row: hash + b64 ── */}
        <div className="pw-toggle-row">
          <label className="pw-check-label">
            <input type="checkbox" checked={prefs.show_hash} onChange={(e) => set("show_hash", e.target.checked)} />
            <span>Show hash</span>
          </label>
          {prefs.show_hash && (
            <div className="algo-chips" style={{ flex: 1 }}>
              {ALL_ALGS.map((a) => (
                <button key={a} className={`algo-chip ${prefs.hash_alg === a ? "active" : ""}`} onClick={() => set("hash_alg", a)}>{a}</button>
              ))}
            </div>
          )}
          <label className="pw-check-label" style={{ marginLeft: prefs.show_hash ? 0 : "auto" }}>
            <input type="checkbox" checked={prefs.show_b64} onChange={(e) => set("show_b64", e.target.checked)} />
            <span>Base64</span>
          </label>
        </div>

      </div>
    </div>
  );
}

// ── VerifyBar ─────────────────────────────────────────────────────────────────
function VerifyBar({ allHashes, selectedAlgs }) {
  const [input, setInput] = useState("");
  const check = input.trim().toLowerCase();
  const matchedAlg = check
    ? selectedAlgs.find((a) => allHashes[a] && allHashes[a].toLowerCase() === check)
    : null;
  const status = check ? (matchedAlg ? "match" : "mismatch") : null;
  return (
    <div className="verify-section">
      <div className="section-label">Verify hash</div>
      <div className="verify-input-wrap">
        <input
          className={["input-field", status === "match" && "verify-ok", status === "mismatch" && "verify-err"].filter(Boolean).join(" ")}
          placeholder="Paste expected hash here to verify…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          spellCheck={false}
          style={{ paddingRight: status ? 36 : 12 }}
        />
        {status && <span className="verify-badge">{status === "match" ? "✅" : "❌"}</span>}
      </div>
      <div className={`verify-status ${status || ""}`}>
        {status === "match" && `✓  MATCH — ${matchedAlg}`}
        {status === "mismatch" && "✗  No match found"}
      </div>
    </div>
  );
}

// ── App ───────────────────────────────────────────────────────────────────────
function App() {
  const [tab, setTab] = useState("file");
  const [fileAlgs, setFileAlgs] = useState(DEFAULT_ALGS);
  const [textAlgs, setTextAlgs] = useState(DEFAULT_ALGS);
  const [pwPrefs, setPwPrefs] = useState(DEFAULT_PW_PREFS);
  const [prefsLoaded, setPrefsLoaded] = useState(false);

  // File tab state
  const [fileInfo, setFileInfo] = useState(null);
  const [fileHashes, setFileHashes] = useState({});
  const [progress, setProgress] = useState(0);
  const [isHashing, setIsHashing] = useState(false);

  // Text tab state
  const [textHashes, setTextHashes] = useState({});

  // Base64
  const [b64In, setB64In] = useState("");
  const [b64Out, setB64Out] = useState("");
  const [b64Error, setB64Error] = useState("");
  const [b64Copied, setB64Copied] = useState(false);

  // Load persisted prefs from bridge on mount
  useEffect(() => {
    getBridge((b) => {
      Promise.resolve(b.load_settings()).then((json) => {
        try {
          const p = JSON.parse(json || "{}");
          if (p.tab) setTab(p.tab);
          if (p.fileAlgs) setFileAlgs(p.fileAlgs);
          if (p.textAlgs) setTextAlgs(p.textAlgs);
          if (p.pwPrefs) setPwPrefs({ ...DEFAULT_PW_PREFS, ...p.pwPrefs });
        } catch { }
        setPrefsLoaded(true);
      });
    });
  }, []);

  // Persist prefs on change (only after initial load to avoid overwriting with defaults)
  useEffect(() => {
    if (!prefsLoaded) return;
    savePrefs({ tab, fileAlgs, textAlgs, pwPrefs });
  }, [tab, fileAlgs, textAlgs, pwPrefs, prefsLoaded]);

  // Bridge signals
  useEffect(() => {
    getBridge((b) => {
      b.hash_progress.connect((p) => setProgress(p));
      b.hash_complete.connect((json) => {
        const r = JSON.parse(json);
        setIsHashing(false);
        if (r.error) {
          setFileHashes({});
          setFileInfo((fi) => fi ? { ...fi, name: `Error: ${r.error}` } : null);
        } else {
          setFileHashes(r);
        }
      });
    });
  }, []);

  const handleFile = useCallback((path) => {
    getBridge((b) => {
      Promise.resolve(b.file_info(path)).then((infoJson) => {
        const info = JSON.parse(infoJson);
        if (!info.name) return;
        setFileInfo(info);
        setFileHashes({});
        setProgress(0);
        setIsHashing(true);
        b.hash_file(path, JSON.stringify(fileAlgs));
        setTab("file");
      }).catch(() => setFileInfo(null));
    });
  }, [fileAlgs]);

  // Re-hash when algorithm selection changes while file is loaded
  useEffect(() => {
    if (!fileInfo?.path) return;
    setFileHashes({});
    setProgress(0);
    setIsHashing(true);
    getBridge((b) => b.hash_file(fileInfo.path, JSON.stringify(fileAlgs)));
  }, [fileAlgs]);

  const handleTextChange = useCallback((text, hmacKey) => {
    if (!text) { setTextHashes({}); return; }
    getBridge((b) =>
      Promise.resolve(b.hash_text(text, hmacKey, JSON.stringify(textAlgs)))
        .then((json) => setTextHashes(JSON.parse(json)))
        .catch(() => setTextHashes({}))
    );
  }, [textAlgs]);

  const handleEncode = useCallback(() => {
    try { setB64Out(encodeBase64(b64In)); setB64Error(""); }
    catch (e) { setB64Out(""); setB64Error(e?.message || "Encoding failed"); }
  }, [b64In]);
  const handleDecode = useCallback(() => {
    try { setB64Out(decodeBase64(b64In)); setB64Error(""); }
    catch (e) { setB64Out(""); setB64Error(e?.message || "Invalid Base64"); }
  }, [b64In]);
  const handleB64Copy = useCallback(() => {
    if (!b64Out) return; copyText(b64Out);
    setB64Copied(true); setTimeout(() => setB64Copied(false), 1400);
  }, [b64Out]);
  const handleB64Clear = useCallback(() => {
    setB64In(""); setB64Out(""); setB64Error(""); setB64Copied(false);
  }, []);

  const tabMotion = { initial: { opacity: 0, y: 6 }, animate: { opacity: 1, y: 0 }, exit: { opacity: 0, y: -4 }, transition: { duration: 0.14 } };
  const tabStyle = { flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" };

  const TABS = [
    ["file", Icons.File, "File"],
    ["text", Icons.Type, "Text"],
    ["base64", Icons.Code, "Base64"],
    ["pwgen", Icons.KeyRound, "PwGen"],
  ];

  const currentHashes = tab === "file" ? fileHashes : textHashes;
  const currentAlgs = tab === "file" ? fileAlgs : textAlgs;

  return (
    <div className="app-shell">
      <div className="app-header">
        <div className="app-header-icon"><Icon icon={Icons.Hash} size={16} /></div>
        <div>
          <div className="app-header-title">Hash Tool</div>
          <div className="app-header-sub">Hashing · Base64 · Password Generator</div>
        </div>
      </div>
      <div className="tab-bar">
        {TABS.map(([t, ico, label]) => (
          <button key={t} className={`tab-btn ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>
            <Icon icon={ico} size={11} style={{ display: "inline", marginRight: 5, verticalAlign: "middle" }} />
            {label}
          </button>
        ))}
      </div>
      <AnimatePresence mode="wait">
        {tab === "file" && (
          <motion.div key="file" style={tabStyle} {...tabMotion}>
            <FileTab
              fileInfo={fileInfo} fileHashes={fileHashes} progress={progress}
              isHashing={isHashing} matchedAlgs={null} onFile={handleFile}
              selectedAlgs={fileAlgs} onAlgsChange={setFileAlgs}
            />
          </motion.div>
        )}
        {tab === "text" && (
          <motion.div key="text" style={tabStyle} {...tabMotion}>
            <TextTab
              textHashes={textHashes} matchedAlgs={null} onTextChange={handleTextChange}
              selectedAlgs={textAlgs} onAlgsChange={setTextAlgs}
            />
          </motion.div>
        )}
        {tab === "base64" && (
          <motion.div key="base64" style={tabStyle} {...tabMotion}>
            <Base64Tab
              input={b64In} output={b64Out} error={b64Error} copied={b64Copied}
              onInputChange={(v) => { setB64In(v); setB64Error(""); }}
              onEncode={handleEncode} onDecode={handleDecode}
              onCopy={handleB64Copy} onClear={handleB64Clear}
            />
          </motion.div>
        )}
        {tab === "pwgen" && (
          <motion.div key="pwgen" style={tabStyle} {...tabMotion}>
            <PwGenTab prefs={pwPrefs} onPrefsChange={setPwPrefs} />
          </motion.div>
        )}
      </AnimatePresence>
      {(tab === "file" || tab === "text") && (
        <VerifyBar allHashes={currentHashes} selectedAlgs={currentAlgs} />
      )}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(React.createElement(App));
