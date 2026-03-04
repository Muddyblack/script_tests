// Hash Tool — single-file React app (QWebChannel / pyBridge)
const { useState, useEffect, useCallback, useRef } = React;
const { motion, AnimatePresence } = window.Motion;
const Icons = window.lucide;

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
let _bridge = null,
  _bridgeReady = false,
  _bridgeCbs = [];
function getBridge(cb) {
  _bridgeReady ? cb(_bridge) : _bridgeCbs.push(cb);
}
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
const ALGS = ["MD5", "SHA-1", "SHA-256", "SHA-512"];
const EMPTY_HASHES = Object.fromEntries(ALGS.map((a) => [a, ""]));
const _enc = new TextEncoder(),
  _dec = new TextDecoder("utf-8"),
  _CHUNK = 0x8000;

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
  if (!text) return Promise.resolve();
  if (navigator.clipboard?.writeText)
    return navigator.clipboard.writeText(text);
  return new Promise((res) => {
    const ta = Object.assign(document.createElement("textarea"), {
      value: text,
    });
    ta.style.cssText = "position:absolute;left:-9999px";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    res();
  });
}
function useCopyFeedback() {
  const [copied, setCopied] = useState(null);
  const copy = useCallback((alg, text) => {
    if (!text) return;
    copyText(text);
    setCopied(alg);
    setTimeout(() => setCopied(null), 1600);
  }, []);
  return [copied, copy];
}

// ── HashRows ──────────────────────────────────────────────────────────────────
function HashRows({ hashes, matchedAlgs }) {
  const [copied, copy] = useCopyFeedback();
  return (
    <div className="hash-rows">
      {ALGS.map((alg) => {
        const value = hashes[alg] || "";
        const isCopied = copied === alg;
        return (
          <div key={alg} className="hash-row float-in">
            <span className="hash-alg-label">{alg}</span>
            <div
              className={`hash-value ${value ? "filled" : ""} ${matchedAlgs?.includes(alg) ? "matched" : ""}`}
              title={value || "—"}
            >
              {value || "—"}
            </div>
            <button
              className={`btn-copy ${isCopied ? "copied" : ""}`}
              onClick={() => copy(alg, value)}
              disabled={!value}
              title={`Copy ${alg}`}
            >
              {isCopied ? "✓ OK" : "COPY"}
            </button>
          </div>
        );
      })}
    </div>
  );
}

// ── DropZone ──────────────────────────────────────────────────────────────────
function DropZone({ fileInfo, isHashing, onFile, onBrowse }) {
  const [drag, setDrag] = useState(false);
  const onDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDrag(true);
  };
  const onDragLeave = (e) => {
    e.preventDefault();
    setDrag(false);
  };
  const onDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDrag(false);
    const f = e.dataTransfer.files?.[0];
    if (f) onFile(f.path || f.name);
  };
  const cls = ["drop-zone", drag && "active", fileInfo && "has-file"]
    .filter(Boolean)
    .join(" ");
  return (
    <div
      className={cls}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      onClick={onBrowse}
    >
      {isHashing ? (
        <>
          <div
            className="drop-zone-icon pulsing"
            style={{ color: "var(--accent)" }}
          >
            <Icon
              icon={Icons.Loader2}
              size={28}
              style={{ animation: "spin 1s linear infinite" }}
            />
          </div>
          <div className="drop-zone-hint">Hashing…</div>
          {fileInfo && <div className="drop-zone-sub">{fileInfo.name}</div>}
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
          <div className="drop-zone-sub">
            {fileInfo.size_str} · click or drop to change
          </div>
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

// ── FileTab ───────────────────────────────────────────────────────────────────
function FileTab({
  fileInfo,
  fileHashes,
  progress,
  isHashing,
  matchedAlgs,
  onFile,
}) {
  const pathRef = useRef(null);
  const browse = () =>
    getBridge((b) =>
      Promise.resolve(b.browse_file()).then((p) => p && onFile(p)),
    );
  return (
    <div className="tab-content">
      <DropZone
        fileInfo={fileInfo}
        isHashing={isHashing}
        onFile={onFile}
        onBrowse={browse}
      />
      <div className="input-row">
        <input
          ref={pathRef}
          className="input-field"
          placeholder="File path — paste or drag above"
          defaultValue={fileInfo?.path || ""}
          onKeyDown={(e) =>
            e.key === "Enter" &&
            pathRef.current?.value?.trim() &&
            onFile(pathRef.current.value.trim())
          }
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
        <div className="section-label">Hashes</div>
        <HashRows hashes={fileHashes} matchedAlgs={matchedAlgs} />
      </div>
    </div>
  );
}

// ── TextTab ───────────────────────────────────────────────────────────────────
function TextTab({ textHashes, matchedAlgs, onTextChange }) {
  const [text, setText] = useState("");
  const [hmacKey, setHmacKey] = useState("");
  const [showHmac, setShowHmac] = useState(false);
  useEffect(() => {
    onTextChange(text, hmacKey);
  }, [text, hmacKey]);
  return (
    <div className="tab-content">
      <div className="card">
        <div className="section-label">Input text</div>
        <textarea
          className="input-field"
          placeholder="Type or paste text here…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          style={{
            resize: "vertical",
            minHeight: 80,
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 12,
            lineHeight: 1.6,
            background: "var(--bg-control, var(--bg-elevated))",
          }}
        />
      </div>
      <div className="card">
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: showHmac ? 8 : 0,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div className="section-label" style={{ marginBottom: 0 }}>
              HMAC Key
            </div>
            {hmacKey && (
              <div className="hmac-badge">
                <Icon icon={Icons.KeyRound} size={9} /> Active
              </div>
            )}
          </div>
          <button
            className="btn btn-ghost"
            style={{ padding: "4px 12px", fontSize: 10 }}
            onClick={() => setShowHmac((v) => !v)}
          >
            {showHmac ? "Hide" : "Set HMAC Key"}
          </button>
        </div>
        {showHmac && (
          <input
            className="input-field"
            placeholder="Leave empty for plain hash…"
            value={hmacKey}
            onChange={(e) => setHmacKey(e.target.value)}
            autoComplete="off"
          />
        )}
      </div>
      <div className="card">
        <div className="section-label">Hashes</div>
        <HashRows hashes={textHashes} matchedAlgs={matchedAlgs} />
      </div>
    </div>
  );
}

// ── Base64Tab ─────────────────────────────────────────────────────────────────
function Base64Tab({
  input,
  output,
  error,
  onInputChange,
  onEncode,
  onDecode,
  onCopy,
  onClear,
  copied,
}) {
  return (
    <div className="tab-content">
      <div className="card b64-card">
        <div className="section-label">Input</div>
        <textarea
          className="input-field b64-textarea"
          placeholder="Type text or paste Base64…"
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          spellCheck={false}
        />
        <div className="b64-actions">
          <button className="btn btn-primary" onClick={onEncode}>
            <Icon
              icon={Icons.ArrowRight}
              size={13}
              style={{
                display: "inline",
                marginRight: 5,
                verticalAlign: "middle",
              }}
            />{" "}
            Encode
          </button>
          <button className="btn btn-primary" onClick={onDecode}>
            <Icon
              icon={Icons.ArrowLeft}
              size={13}
              style={{
                display: "inline",
                marginRight: 5,
                verticalAlign: "middle",
              }}
            />{" "}
            Decode
          </button>
          <div className="b64-spacer" />
          <button className="btn btn-ghost" onClick={onClear}>
            Clear
          </button>
        </div>
        {error && (
          <div className="verify-status mismatch" style={{ marginBottom: 6 }}>
            {error}
          </div>
        )}
        <div className="section-label">Output</div>
        <textarea
          className="input-field b64-textarea"
          placeholder="Result appears here…"
          value={output}
          readOnly
        />
        <div
          style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}
        >
          <button
            className={`btn-copy ${copied ? "copied" : ""}`}
            onClick={onCopy}
            disabled={!output}
          >
            {copied ? "✓ COPIED" : "COPY"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── VerifyBar ─────────────────────────────────────────────────────────────────
function VerifyBar({ allHashes }) {
  const [input, setInput] = useState("");
  const check = input.trim().toLowerCase();
  let matchedAlg = check
    ? ALGS.find((a) => allHashes[a] && allHashes[a].toLowerCase() === check)
    : null;
  const status = check ? (matchedAlg ? "match" : "mismatch") : null;
  return (
    <div className="verify-section">
      <div className="section-label">Verify hash</div>
      <div className="verify-input-wrap">
        <input
          className={[
            "input-field",
            status === "match" && "verify-ok",
            status === "mismatch" && "verify-err",
          ]
            .filter(Boolean)
            .join(" ")}
          placeholder="Paste expected hash here to verify…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          spellCheck={false}
          style={{ paddingRight: status ? 36 : 12 }}
        />
        {status && (
          <span className="verify-badge">
            {status === "match" ? "✅" : "❌"}
          </span>
        )}
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
  const [b64In, setB64In] = useState(""),
    [b64Out, setB64Out] = useState(""),
    [b64Error, setB64Error] = useState(""),
    [b64Copied, setB64Copied] = useState(false);
  const [fileInfo, setFileInfo] = useState(null),
    [fileHashes, setFileHashes] = useState(EMPTY_HASHES),
    [progress, setProgress] = useState(0),
    [isHashing, setIsHashing] = useState(false);
  const [textHashes, setTextHashes] = useState(EMPTY_HASHES);

  const handleEncode = useCallback(() => {
    try {
      setB64Out(encodeBase64(b64In));
      setB64Error("");
    } catch (e) {
      setB64Out("");
      setB64Error(e?.message || "Encoding failed");
    }
  }, [b64In]);
  const handleDecode = useCallback(() => {
    try {
      setB64Out(decodeBase64(b64In));
      setB64Error("");
    } catch (e) {
      setB64Out("");
      setB64Error(e?.message || "Invalid Base64");
    }
  }, [b64In]);
  const handleB64Copy = useCallback(() => {
    if (!b64Out) return;
    copyText(b64Out);
    setB64Copied(true);
    setTimeout(() => setB64Copied(false), 1400);
  }, [b64Out]);
  const handleB64Clear = useCallback(() => {
    setB64In("");
    setB64Out("");
    setB64Error("");
    setB64Copied(false);
  }, []);

  useEffect(() => {
    getBridge((b) => {
      b.hash_progress.connect((p) => setProgress(p));
      b.hash_complete.connect((json) => {
        const r = JSON.parse(json);
        setIsHashing(false);
        if (r.error) {
          setFileHashes(EMPTY_HASHES);
          setFileInfo((fi) =>
            fi ? { ...fi, name: `Error: ${r.error}` } : null,
          );
        } else setFileHashes(r);
      });
    });
  }, []);

  const handleFile = useCallback((path) => {
    getBridge((b) => {
      Promise.resolve(b.file_info(path))
        .then((infoJson) => {
          const info = JSON.parse(infoJson);
          if (!info.name) return;
          setFileInfo(info);
          setFileHashes(EMPTY_HASHES);
          setProgress(0);
          setIsHashing(true);
          b.hash_file(path);
          setTab("file");
        })
        .catch(() => setFileInfo(null));
    });
  }, []);

  const handleTextChange = useCallback((text, hmacKey) => {
    if (!text) {
      setTextHashes(EMPTY_HASHES);
      return;
    }
    getBridge((b) =>
      Promise.resolve(b.hash_text(text, hmacKey))
        .then((json) => setTextHashes(JSON.parse(json)))
        .catch(() => setTextHashes(EMPTY_HASHES)),
    );
  }, []);

  const tabMotion = {
    initial: { opacity: 0, y: 6 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, y: -4 },
    transition: { duration: 0.14 },
  };
  const tabStyle = {
    flex: 1,
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
  };
  const TABS = [
    ["file", Icons.File, "File"],
    ["text", Icons.Type, "Text"],
    ["base64", Icons.Code, "Base64"],
  ];

  return (
    <div className="app-shell">
      <div className="app-header">
        <div className="app-header-icon">
          <Icon icon={Icons.Hash} size={16} />
        </div>
        <div>
          <div className="app-header-title">Hash Tool</div>
          <div className="app-header-sub">MD5 · SHA-1 · SHA-256 · SHA-512</div>
        </div>
      </div>
      <div className="tab-bar">
        {TABS.map(([t, ico, label]) => (
          <button
            key={t}
            className={`tab-btn ${tab === t ? "active" : ""}`}
            onClick={() => setTab(t)}
          >
            <Icon
              icon={ico}
              size={11}
              style={{
                display: "inline",
                marginRight: 5,
                verticalAlign: "middle",
              }}
            />
            {label}
          </button>
        ))}
      </div>
      <AnimatePresence mode="wait">
        {tab === "file" && (
          <motion.div key="file" style={tabStyle} {...tabMotion}>
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
        {tab === "text" && (
          <motion.div key="text" style={tabStyle} {...tabMotion}>
            <TextTab
              textHashes={textHashes}
              matchedAlgs={null}
              onTextChange={handleTextChange}
            />
          </motion.div>
        )}
        {tab === "base64" && (
          <motion.div key="base64" style={tabStyle} {...tabMotion}>
            <Base64Tab
              input={b64In}
              output={b64Out}
              error={b64Error}
              copied={b64Copied}
              onInputChange={(v) => {
                setB64In(v);
                setB64Error("");
              }}
              onEncode={handleEncode}
              onDecode={handleDecode}
              onCopy={handleB64Copy}
              onClear={handleB64Clear}
            />
          </motion.div>
        )}
      </AnimatePresence>
      <VerifyBar allHashes={tab === "file" ? fileHashes : textHashes} />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  React.createElement(App),
);
