// Nexus File Tools — React/JSX single-file app (QWebChannel bridge)
// FILE OPS tab: copy · move · delete
// ARCHIVER tab: compress (zip/7z/tar.*) · extract · archive preview

const { useState, useEffect, useCallback, useRef } = React;
const { motion, AnimatePresence } = window.Motion;
const Icons = window.lucide;

// ── SVG Icon helper ───────────────────────────────────────────────────────────
function Icon({ icon, size = 16, style, className }) {
  if (!icon || !Array.isArray(icon)) return null;
  return React.createElement(
    "svg",
    {
      xmlns: "http://www.w3.org/2000/svg",
      width: size, height: size,
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
    ...icon.map(([tag, attrs], i) => React.createElement(tag, { key: i, ...attrs })),
  );
}

// ── Bridge singleton ──────────────────────────────────────────────────────────
let _bridge = null, _ready = false, _queue = [];
function getBridge(cb) { _ready ? cb(_bridge) : _queue.push(cb); }
if (typeof QWebChannel !== "undefined") {
  new QWebChannel(qt.webChannelTransport, ch => {
    _bridge = ch.objects.pyBridge;
    _ready  = true;
    _queue.forEach(fn => fn(_bridge));
    _queue.length = 0;
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function call(slot, ...args) {
  return new Promise(resolve =>
    getBridge(b => resolve(typeof b[slot] === "function" ? b[slot](...args) : b[slot]))
  );
}
function pathsFromEvent(e) {
  return Array.from(e.dataTransfer.files || []).map(f => f.path || f.name).filter(Boolean);
}

// ── DropZone ──────────────────────────────────────────────────────────────────
function DropZone({ hint, subhint, onPaths, visible }) {
  const [drag, setDrag] = useState(false);
  if (!visible) return null;
  return (
    <div
      className={`drop-zone ${drag ? "active" : ""}`}
      onDragOver={e => { e.preventDefault(); e.stopPropagation(); setDrag(true); }}
      onDragLeave={e => { e.preventDefault(); setDrag(false); }}
      onDrop={e => { e.preventDefault(); setDrag(false); const p = pathsFromEvent(e); if (p.length) onPaths(p); }}
    >
      <div className="drop-zone-icon"><Icon icon={Icons.Upload} size={24} /></div>
      <div className="drop-zone-hint">{hint}</div>
      <div className="drop-zone-sub">{subhint}</div>
    </div>
  );
}

// ── QueueItem ─────────────────────────────────────────────────────────────────
function QueueItem({ item, onRemove }) {
  const isArc   = item.is_archive;
  const isDir   = item.is_dir;
  const warn    = isArc && item.caps && !item.caps.can_extract;
  const needs7z = isArc && item.caps && item.caps.needs_7z && item.caps.can_extract;

  const iconEl = isArc
    ? <Icon icon={Icons.Archive} size={13} />
    : isDir
      ? <Icon icon={Icons.Folder} size={13} style={{ color: "var(--success, #22c55e)" }} />
      : <Icon icon={Icons.File} size={13} />;

  return (
    <div className="queue-item float-in">
      <span className="queue-item-icon">{iconEl}</span>
      <span className="queue-item-name" title={item.path}>{item.name}</span>
      {item.size_str && <span className="queue-item-size">{item.size_str}</span>}
      {isArc && !warn && (
        <span className={`queue-item-badge ${needs7z ? "badge-needs7z" : "badge-archive"}`}>
          {item.fmt}
        </span>
      )}
      {isDir && <span className="queue-item-badge badge-dir">DIR</span>}
      {warn && <span className="queue-item-badge badge-warn">NEEDS 7Z</span>}
      <button className="queue-item-remove" onClick={onRemove} title="Remove">
        <Icon icon={Icons.X} size={11} />
      </button>
    </div>
  );
}

// ── QueueSection ──────────────────────────────────────────────────────────────
function QueueSection({ items, onPaths, onRemove, onClear, onAddFiles, onAddFolder,
                        dropHint, dropSub, noun }) {
  const hasItems = items.length > 0;
  return (
    <div className="card">
      <div className="section-label">{noun} QUEUE · {items.length} item{items.length !== 1 ? "s" : ""}</div>
      <DropZone hint={dropHint} subhint={dropSub} onPaths={onPaths} visible={!hasItems} />
      {hasItems && (
        <div className="queue-list">
          {items.map((item, i) => (
            <QueueItem key={item.path + i} item={item} onRemove={() => onRemove(i)} />
          ))}
        </div>
      )}
      <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
        <button className="btn btn-ghost" onClick={onAddFiles}>
          <Icon icon={Icons.FilePlus} size={12} /> Add Files
        </button>
        <button className="btn btn-ghost" onClick={onAddFolder}>
          <Icon icon={Icons.FolderPlus} size={12} /> Add Folder
        </button>
        {hasItems && (
          <button className="btn btn-ghost" onClick={onClear} style={{ marginLeft: "auto" }}>
            <Icon icon={Icons.Trash2} size={12} /> Clear
          </button>
        )}
      </div>
    </div>
  );
}

// ── DestRow ───────────────────────────────────────────────────────────────────
function DestRow({ label, value, placeholder, onChange, onSave }) {
  return (
    <div className="card">
      <div className="section-label">{label}</div>
      <div className="input-row">
        <input
          className="input-field"
          placeholder={placeholder}
          value={value}
          onChange={e => onChange(e.target.value)}
          onBlur={onSave}
        />
        <button
          className="btn btn-ghost"
          onClick={() => call("browse_folder").then(p => { if (p) { onChange(p); onSave(); } })}
        >
          <Icon icon={Icons.FolderOpen} size={13} /> Browse
        </button>
      </div>
    </div>
  );
}

// ── AdvancedPanel ─────────────────────────────────────────────────────────────
function AdvancedPanel({ info, opts, onChange }) {
  if (!info) return null;
  return (
    <div className="adv-panel float-in">
      <div className="adv-grid">
        {[
          ["level",     "LEVEL",     info.levels],
          ["dict_size", "DICT SIZE", info.dict_sizes],
          ["threads",   "THREADS",   info.threads],
        ].map(([key, lbl, items]) => (
          <div className="adv-col" key={key}>
            <div className="section-label">{lbl}</div>
            <select
              className="adv-select"
              value={opts[key]}
              onChange={e => onChange({ ...opts, [key]: e.target.value })}
            >
              {items.map(v => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
        ))}
      </div>
      <div className="adv-grid">
        <div className="adv-col">
          <div className="section-label">SPLIT VOLUMES</div>
          <select
            className="adv-select"
            value={opts.split}
            onChange={e => onChange({ ...opts, split: e.target.value })}
          >
            {info.split_sizes.map(v => <option key={v} value={v}>{v}</option>)}
          </select>
        </div>
        <div className="adv-col" style={{ justifyContent: "flex-end", paddingBottom: 2 }}>
          <label className="adv-checkbox-row">
            <input
              type="checkbox"
              checked={opts.solid}
              onChange={e => onChange({ ...opts, solid: e.target.checked })}
            />
            Solid archive (better ratio)
          </label>
          <label className="adv-checkbox-row" style={{ marginTop: 8 }}>
            <input
              type="checkbox"
              checked={opts.encrypt_names}
              onChange={e => onChange({ ...opts, encrypt_names: e.target.checked })}
            />
            Encrypt file names (7z only)
          </label>
        </div>
      </div>
    </div>
  );
}

// ── PreviewModal ──────────────────────────────────────────────────────────────
function PreviewModal({ archivePath, onClose }) {
  const [contents, setContents] = useState(null);
  useEffect(() => {
    call("list_archive", archivePath).then(res => {
      try {
        const arr = JSON.parse(res);
        setContents(Array.isArray(arr) ? arr : arr.error ? [`Error: ${arr.error}`] : []);
      } catch { setContents([]); }
    });
  }, [archivePath]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <motion.div
        className="modal-box"
        initial={{ opacity: 0, scale: 0.94 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.94 }}
        transition={{ duration: 0.14 }}
        onClick={e => e.stopPropagation()}
      >
        <div className="modal-header">
          <span className="modal-title">
            <Icon icon={Icons.Archive} size={12} style={{ marginRight: 6, verticalAlign: "middle" }} />
            {archivePath.split(/[/\\]/).pop()} — contents
          </span>
          <button className="btn btn-ghost" style={{ padding: "4px 10px" }} onClick={onClose}>
            <Icon icon={Icons.X} size={13} />
          </button>
        </div>
        {contents === null ? (
          <div style={{ color: "var(--text-disabled)", textAlign: "center", padding: 20 }}>
            <Icon icon={Icons.Loader2} size={20} style={{ animation: "spin 1s linear infinite" }} />
          </div>
        ) : (
          <div className="modal-list">
            {contents.length === 0 ? (
              <div style={{ color: "var(--text-disabled)" }}>Empty archive</div>
            ) : (
              contents.map((name, i) => (
                <div key={i} className="modal-list-item" title={name}>{name}</div>
              ))
            )}
          </div>
        )}
        <div style={{ color: "var(--text-disabled)", fontSize: 10, fontFamily: "monospace" }}>
          {contents !== null && `${contents.length} items`}
        </div>
      </motion.div>
    </div>
  );
}

// ── FILE OPS TAB ──────────────────────────────────────────────────────────────
function FileOpsTab({ items, dest, busy, onPaths, onRemove, onClear,
                      onAddFiles, onAddFolder, onDestChange, onSaveSettings,
                      onRun }) {
  const hasItems = items.length > 0;
  const noMoves  = !hasItems || busy;
  return (
    <div className="tab-content">
      <QueueSection
        items={items}
        onPaths={onPaths}
        onRemove={onRemove}
        onClear={onClear}
        onAddFiles={onAddFiles}
        onAddFolder={onAddFolder}
        dropHint="Drop files or folders here"
        dropSub="Files will be queued for copy · move · delete"
        noun="FILE"
      />
      <DestRow
        label="DESTINATION"
        value={dest}
        placeholder="Select destination folder…"
        onChange={onDestChange}
        onSave={onSaveSettings}
      />
      <div className="card">
        <div className="section-label">OPERATION</div>
        <div className="action-row" style={{ justifyContent: "flex-end" }}>
          {[
            ["copy",   "COPY",   "btn-copy-action",  Icons.Copy],
            ["move",   "MOVE",   "btn-move",          Icons.MoveRight],
            ["delete", "DELETE", "btn-delete",        Icons.Trash2],
          ].map(([op, label, cls, ico]) => (
            <button
              key={op}
              className={`btn ${cls}`}
              disabled={noMoves}
              onClick={() => onRun(op)}
            >
              <Icon icon={ico} size={13} /> {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── ARCHIVER TAB ──────────────────────────────────────────────────────────────
function ArchiverTab({ items, dest, pwd, showPwd, fmt, advOpen, advOpts, info, busy,
                       onPaths, onRemove, onClear, onAddFiles, onAddFolder,
                       onDestChange, onSaveSettings, onPwdChange, onTogglePwd,
                       onFmtChange, onAdvToggle, onAdvOpts, onCompress, onExtract,
                       onPreview }) {
  const hasItems    = items.length > 0;
  const archives    = items.filter(i => i.is_archive);
  const nonArchives = items.filter(i => !i.is_archive);
  const canExtract  = archives.length > 0 && archives.every(i => i.caps && i.caps.can_extract);
  const canCompress = nonArchives.length > 0 || (hasItems && !archives.some(i => i.caps && !i.caps.can_extract));
  const disabled    = !hasItems || busy;

  return (
    <div className="tab-content">
      <QueueSection
        items={items}
        onPaths={onPaths}
        onRemove={onRemove}
        onClear={onClear}
        onAddFiles={onAddFiles}
        onAddFolder={onAddFolder}
        dropHint="Drop archives to extract · or files/folders to compress"
        dropSub={info?.has_7z ? "7-Zip detected — all formats supported" : "Install 7-Zip for .7z · .rar · .iso and more"}
        noun="ARC"
      />
      {/* Preview button row */}
      {archives.length > 0 && (
        <div style={{ display: "flex", gap: 6, marginTop: -4, paddingLeft: 2 }}>
          {archives.slice(0, 3).map((arc, i) => (
            <button
              key={i}
              className="btn btn-ghost"
              style={{ fontSize: 9, padding: "4px 10px" }}
              onClick={() => onPreview(arc.path)}
            >
              <Icon icon={Icons.List} size={11} /> {arc.name.length > 22 ? arc.name.slice(0,22)+"…" : arc.name}
            </button>
          ))}
        </div>
      )}

      <DestRow
        label="OUTPUT FOLDER"
        value={dest}
        placeholder="Leave blank — save next to source"
        onChange={onDestChange}
        onSave={onSaveSettings}
      />

      {/* Password row */}
      <div className="card">
        <div className="section-label">PASSWORD / OPTIONS</div>
        <div className="input-row">
          <input
            className={`input-field pw-field`}
            type={showPwd ? "text" : "password"}
            placeholder="Password (optional)"
            value={pwd}
            onChange={e => onPwdChange(e.target.value)}
          />
          <button className="btn btn-pw-toggle" onClick={onTogglePwd} title="Toggle visibility">
            {showPwd ? "🙈" : "👁"}
          </button>
        </div>

        {/* Advanced options */}
        <div className="adv-toggle-row" style={{ marginTop: 10 }}>
          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--text-disabled)" }}>
            ⚙ Advanced options
          </span>
          <button
            className="btn btn-ghost"
            style={{ padding: "3px 10px", fontSize: 9 }}
            onClick={onAdvToggle}
          >
            {advOpen ? "Hide" : "Show"}
          </button>
        </div>
        <AnimatePresence>
          {advOpen && (
            <motion.div
              key="adv"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.18 }}
              style={{ overflow: "hidden", marginTop: 10 }}
            >
              <AdvancedPanel info={info} opts={advOpts} onChange={onAdvOpts} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Action row */}
      <div className="card">
        <div className="action-row">
          <select className="fmt-select" value={fmt} onChange={e => onFmtChange(e.target.value)}>
            {(info?.formats || ["zip"]).map(f => <option key={f} value={f}>{f}</option>)}
          </select>
          <div style={{ flex: 1 }} />
          <button
            className="btn btn-compress"
            disabled={disabled || !canCompress}
            onClick={onCompress}
          >
            <Icon icon={Icons.Package} size={13} /> Compress
          </button>
          <button
            className="btn btn-extract"
            disabled={disabled || !canExtract}
            onClick={onExtract}
          >
            <Icon icon={Icons.PackageOpen} size={13} /> Extract
          </button>
        </div>
      </div>
    </div>
  );
}

// ── App ───────────────────────────────────────────────────────────────────────
function App() {
  // ── UI state
  const [tab, setTab]           = useState("fileops");
  const [info, setInfo]         = useState(null);  // bridge capabilities

  // ── File ops
  const [foItems, setFoItems]   = useState([]);
  const [foDest,  setFoDest]    = useState("");

  // ── Archiver
  const [arcItems, setArcItems] = useState([]);
  const [arcDest,  setArcDest]  = useState("");
  const [arcPwd,   setArcPwd]   = useState("");
  const [showPwd,  setShowPwd]  = useState(false);
  const [arcFmt,   setArcFmt]   = useState("zip");
  const [advOpen,  setAdvOpen]  = useState(false);
  const [advOpts,  setAdvOpts]  = useState({
    level: "Normal", dict_size: "16 MB", threads: "Auto",
    solid: true, split: "None", encrypt_names: false,
  });

  // ── Preview modal
  const [previewPath, setPreviewPath] = useState(null);

  // ── Progress / status
  const [busy,        setBusy]   = useState(false);
  const [progress,    setProgress] = useState({ value: 0, max: 100 });
  const [statusText,  setStatus] = useState("READY");
  const [statusType,  setStType] = useState("idle"); // idle | working | done | error

  // ── On mount: connect bridge
  useEffect(() => {
    getBridge(b => {
      // Load capabilities
      Promise.resolve(b.get_info()).then(json => {
        try {
          const d = JSON.parse(json);
          setInfo(d);
          // Default fmt — prefer 7z if available
          if (d.formats && d.formats.length) setArcFmt(d.formats[0]);
        } catch {}
      });

      // Load saved settings
      Promise.resolve(b.load_settings()).then(json => {
        try {
          const s = JSON.parse(json);
          if (s.fo_dest)  setFoDest(s.fo_dest);
          if (s.arc_dest) setArcDest(s.arc_dest);
        } catch {}
      });

      // Load initial state (pre-populated from launcher)
      Promise.resolve(b.get_initial_state()).then(json => {
        try {
          const s = JSON.parse(json);
          if (s.tab) setTab(s.tab);
          if (s.fo_sources  && s.fo_sources.length)  resolveAndAdd(s.fo_sources,  setFoItems);
          if (s.arc_sources && s.arc_sources.length) resolveAndAdd(s.arc_sources, setArcItems);
        } catch {}
      });

      // Wire progress/done signals
      b.ops_progress.connect((done, total, name) => {
        setProgress({ value: done, max: total });
        setStatus(`${name}  [${done}/${total}]`);
      });
      b.ops_done.connect(json => {
        try {
          const r = JSON.parse(json);
          setBusy(false);
          if (r.errors && r.errors.length) {
            setStatus(`${r.errors.length} error(s) — ${r.errors[0].slice(0, 60)}`);
            setStType("error");
          } else {
            setStatus("ALL DONE ✓");
            setStType("done");
            setFoItems([]);
          }
        } catch {}
        setTimeout(() => { setStatus("READY"); setStType("idle"); }, 4000);
      });

      b.arc_progress.connect((done, total) => {
        setProgress({ value: done, max: total });
        setStatus(`Processing…  [${done}/${total}]`);
      });
      b.arc_done.connect(json => {
        try {
          const r = JSON.parse(json);
          setBusy(false);
          if (r.errors && r.errors.length) {
            setStatus(`Error: ${r.errors[0].slice(0, 70)}`);
            setStType("error");
          } else {
            setStatus(`${r.message}  ✓`);
            setStType("done");
            setArcItems([]);
          }
        } catch {}
        setTimeout(() => { setStatus("READY"); setStType("idle"); }, 4000);
      });
    });
  }, []);

  // ── Resolve paths → item info from bridge
  function resolveAndAdd(paths, setter) {
    paths.forEach(path => {
      call("get_item_info", path).then(json => {
        try {
          const item = JSON.parse(json);
          if (!item.error) {
            setter(prev => prev.some(i => i.path === item.path) ? prev : [...prev, item]);
          }
        } catch {}
      });
    });
  }

  function addPaths(paths, setter) { resolveAndAdd(paths, setter); }

  // ── Browse handlers
  function browseFiles(setter) {
    call("browse_files").then(json => {
      try { const paths = JSON.parse(json); if (paths.length) resolveAndAdd(paths, setter); } catch {}
    });
  }
  function browseFolder(setter) {
    call("browse_folder").then(p => {
      if (p) {
        call("get_item_info", p).then(json => {
          try {
            const item = JSON.parse(json);
            if (!item.error) setter(prev => prev.some(i => i.path === item.path) ? prev : [...prev, item]);
          } catch {}
        });
      }
    });
  }

  // ── Settings save
  const saveSettings = useCallback((foDestVal, arcDestVal) => {
    getBridge(b => {
      Promise.resolve(b.save_settings(JSON.stringify({ fo_dest: foDestVal, arc_dest: arcDestVal })));
    });
  }, []);

  // ── FILE OPS run
  function runFileOp(op) {
    if (!foItems.length) return;
    if (op !== "delete" && !foDest.trim()) { setStatus("SELECT A DESTINATION FIRST"); setStType("error"); return; }
    setBusy(true);
    setProgress({ value: 0, max: foItems.length });
    setStatus("WORKING…");
    setStType("working");
    getBridge(b => b.run_file_ops(JSON.stringify({
      op,
      sources: foItems.map(i => i.path),
      dest: foDest.trim(),
    })));
  }

  // ── ARCHIVER compress
  function runCompress() {
    if (!arcItems.length) return;
    const dst = arcDest.trim() || (arcItems[0] ? physDirOf(arcItems[0].path, arcItems[0].is_dir) : "");
    const extMap = { zip:".zip","7z":".7z",tar:".tar","tar.gz":".tar.gz",
                     "tar.bz2":".tar.bz2","tar.xz":".tar.xz",gz:".gz" };
    const ext  = extMap[arcFmt] || `.${arcFmt}`;
    let   base = (arcItems.length === 1
      ? arcItems[0].name.replace(/\.[^/.]+$/, "").replace(/\.tar$/, "")
      : "archive");
    const output = dst + (dst.endsWith("\\") || dst.endsWith("/") ? "" : "/") + base + ext;

    setBusy(true);
    setProgress({ value: 0, max: 100 });
    setStatus("COMPRESSING…");
    setStType("working");
    getBridge(b => b.run_compress(JSON.stringify({
      sources: arcItems.map(i => i.path),
      output,
      fmt: arcFmt,
      password: arcPwd,
      ...advOpts,
    })));
  }

  function physDirOf(path, isDir) {
    if (isDir) return path;
    const sep = path.includes("\\") ? "\\" : "/";
    return path.slice(0, path.lastIndexOf(sep) + 1);
  }

  // ── ARCHIVER extract
  function runExtract() {
    const archives = arcItems.filter(i => i.is_archive && i.caps && i.caps.can_extract);
    if (!archives.length) return;
    setBusy(true);
    setProgress({ value: 0, max: 100 });
    setStatus("EXTRACTING…");
    setStType("working");
    getBridge(b => b.run_extract(JSON.stringify({
      archives: archives.map(i => i.path),
      dest: arcDest.trim(),
      password: arcPwd,
    })));
  }

  // ── Status dot color
  const dotColor = { idle: "var(--success, #22c55e)", working: "var(--accent)",
                     done: "var(--success, #22c55e)", error: "var(--danger)" }[statusType];
  const statusColor = { idle: "var(--text-secondary)", working: "var(--accent)",
                        done: "var(--success, #22c55e)", error: "var(--danger)" }[statusType];

  const tabMotion = {
    initial: { opacity: 0, y: 6 },
    animate: { opacity: 1, y: 0 },
    exit:    { opacity: 0, y: -5 },
    transition: { duration: 0.14 },
  };
  const tabStyle = { flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" };

  return (
    <div className="app-shell">
      {/* Header */}
      <div className="app-header">
        <div className="app-header-icon">
          <Icon icon={Icons.FolderCog} size={16} />
        </div>
        <div>
          <div className="app-header-title">Nexus File Tools</div>
          <div className="app-header-sub">
            {info?.has_7z ? "7-Zip detected · all formats supported" : "Copy · Move · Delete · Archive"}
          </div>
        </div>
        <div className="status-badge" style={{ color: statusColor }}>
          <div className="status-dot" style={{ background: dotColor }} />
          {statusText}
        </div>
      </div>

      {/* Tab bar */}
      <div className="tab-bar">
        {[["fileops", Icons.Files, "File Ops"], ["archiver", Icons.Archive, "Archiver"]].map(([t, ico, lbl]) => (
          <button key={t} className={`tab-btn ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>
            <Icon icon={ico} size={11} style={{ marginRight: 5, verticalAlign: "middle" }} />
            {lbl}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <AnimatePresence mode="wait">
        {tab === "fileops" && (
          <motion.div key="fo" style={tabStyle} {...tabMotion}>
            <FileOpsTab
              items={foItems}
              dest={foDest}
              busy={busy}
              onPaths={p => addPaths(p, setFoItems)}
              onRemove={i => setFoItems(prev => prev.filter((_, idx) => idx !== i))}
              onClear={() => setFoItems([])}
              onAddFiles={() => browseFiles(setFoItems)}
              onAddFolder={() => browseFolder(setFoItems)}
              onDestChange={v => setFoDest(v)}
              onSaveSettings={() => saveSettings(foDest, arcDest)}
              onRun={runFileOp}
            />
          </motion.div>
        )}
        {tab === "archiver" && (
          <motion.div key="arc" style={tabStyle} {...tabMotion}>
            <ArchiverTab
              items={arcItems}
              dest={arcDest}
              pwd={arcPwd}
              showPwd={showPwd}
              fmt={arcFmt}
              advOpen={advOpen}
              advOpts={advOpts}
              info={info}
              busy={busy}
              onPaths={p => addPaths(p, setArcItems)}
              onRemove={i => setArcItems(prev => prev.filter((_, idx) => idx !== i))}
              onClear={() => setArcItems([])}
              onAddFiles={() => browseFiles(setArcItems)}
              onAddFolder={() => browseFolder(setArcItems)}
              onDestChange={v => setArcDest(v)}
              onSaveSettings={() => saveSettings(foDest, arcDest)}
              onPwdChange={setArcPwd}
              onTogglePwd={() => setShowPwd(v => !v)}
              onFmtChange={setArcFmt}
              onAdvToggle={() => setAdvOpen(v => !v)}
              onAdvOpts={setAdvOpts}
              onCompress={runCompress}
              onExtract={runExtract}
              onPreview={setPreviewPath}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Progress area */}
      <div className="progress-area">
        <div className="progress-wrap">
          <div
            className="progress-bar"
            style={{ width: busy && progress.max > 0 ? `${Math.round(progress.value / progress.max * 100)}%` : "0%" }}
          />
        </div>
        <div className="progress-label" style={{ color: statusColor }}>
          {busy
            ? `${progress.value} / ${progress.max}`
            : statusType === "error" || statusType === "done" ? statusText : ""}
        </div>
      </div>

      {/* Archive preview modal */}
      <AnimatePresence>
        {previewPath && (
          <PreviewModal
            key="preview"
            archivePath={previewPath}
            onClose={() => setPreviewPath(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  React.createElement(App)
);
