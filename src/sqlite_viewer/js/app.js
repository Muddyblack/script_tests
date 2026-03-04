// SQLite Viewer — React app (QWebChannel / pyBridge)
const { useState, useEffect, useCallback, useRef, useMemo } = React;
const Icons = window.lucide;

// ── Icon helper ───────────────────────────────────────────────────────────────
function Icon({ icon, size = 14, className, style }) {
  if (!icon || !Array.isArray(icon)) return null;
  return React.createElement("svg", {
    xmlns: "http://www.w3.org/2000/svg",
    width: size, height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    style: { flexShrink: 0, display: "inline-block", verticalAlign: "middle", ...style },
    className,
    "aria-hidden": "true",
  }, ...icon.map(([tag, attrs], i) => React.createElement(tag, { key: i, ...attrs })));
}

// ── Bridge ────────────────────────────────────────────────────────────────────
let _bridge = null, _bridgeReady = false, _bridgeCbs = [];
function getBridge(cb) {
  _bridgeReady ? cb(_bridge) : _bridgeCbs.push(cb);
}
if (typeof QWebChannel !== "undefined") {
  new QWebChannel(qt.webChannelTransport, (ch) => {
    _bridge = ch.objects.pyBridge;
    _bridgeReady = true;
    _bridgeCbs.forEach(fn => fn(_bridge));
    _bridgeCbs.length = 0;
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmtSize(bytes) {
  if (bytes == null) return "?";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1024 / 1024).toFixed(2) + " MB";
}
function fmtCount(n) {
  if (n < 0) return "view";
  if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
  if (n >= 1000) return (n / 1000).toFixed(1) + "K";
  return String(n);
}
function copyText(text) {
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(text);
  const ta = Object.assign(document.createElement("textarea"), { value: text });
  ta.style.cssText = "position:fixed;left:-9999px";
  document.body.appendChild(ta); ta.select(); document.execCommand("copy"); document.body.removeChild(ta);
}

function normalizeFilePath(candidate) {
  if (!candidate) return null;
  const trimmed = candidate.trim();
  if (!trimmed) return null;

  // 1. Direct Windows path (e.g. C:\path or \\server\path)
  if (/^(?:[A-Za-z]:[\\/]|\\\\)/.test(trimmed)) return trimmed;

  const lower = trimmed.toLowerCase();

  // 2. Try to extract URL if embedded (common in some drag sources)
  let maybeUri = trimmed;
  const schemeIdx = lower.indexOf("file://");
  if (schemeIdx >= 0) {
    maybeUri = trimmed.slice(schemeIdx);
  }

  // 3. Robust URL parsing
  try {
    const url = new URL(maybeUri);
    if (url.protocol === "file:") {
      let pathname = decodeURIComponent(url.pathname);
      // Standardize Windows path from URI: /C:/path -> C:/path
      if (/^\/[A-Za-z]:/.test(pathname)) pathname = pathname.slice(1);
      return pathname;
    }
  } catch (e) {
    // 4. Manual fallback for malformed file:// URIs
    if (lower.startsWith("file://")) {
      let stripped = trimmed.replace(/^file:\/\/+/, "");
      // Handle leading slash if present after host: /C:/path -> C:/path
      if (/^\/[A-Za-z]:/.test(stripped)) stripped = stripped.slice(1);
      // Convert backslashes to forward slashes for validation
      const normalized = stripped.replace(/\\/g, "/");
      if (/^[A-Za-z]:\//.test(normalized)) return stripped;
    }
  }

  return null;
}

function extractPathFromData(value) {
  if (!value) return null;
  for (const line of value.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const path = normalizeFilePath(trimmed);
    if (path) return path;
  }
  return null;
}

function resolveDroppedFilePath(event) {
  const dt = event.dataTransfer;
  if (!dt) return null;

  // 1. Try modern DataTransferItemList (often more reliable in Chromium)
  if (dt.items) {
    for (let i = 0; i < dt.items.length; i++) {
      if (dt.items[i].kind === 'file') {
        const file = dt.items[i].getAsFile();
        if (file && file.path) return file.path;
      }
    }
  }

  // 2. Try various MIME types that might contain the path/URI
  const sources = [
    dt.getData("text/uri-list"),
    dt.getData("URL"),
    dt.getData("text/plain"),
    dt.getData("DownloadURL"),
  ];

  for (const source of sources) {
    if (!source) continue;
    const path = extractPathFromData(source);
    if (path) return path;
  }

  // 3. Fallback: check if the environment provides a .path property on File
  const file = dt.files?.[0];
  if (file && file.path) {
    return file.path;
  }

  return null;
}

// Classify SQLite type for styling
function typeClass(t) {
  if (!t) return "type-default";
  const u = t.toUpperCase();
  if (u.includes("INT")) return "type-integer";
  if (u.includes("REAL") || u.includes("FLOAT") || u.includes("DOUBLE") || u.includes("NUMERIC") || u.includes("DECIMAL")) return "type-real";
  if (u.includes("TEXT") || u.includes("CHAR") || u.includes("CLOB")) return "type-text";
  if (u.includes("BLOB") || u === "NONE" || u === "") return "type-blob";
  return "type-default";
}
// Classify cell value
function cellClass(val, colType) {
  if (val === null || val === undefined) return "td-null";
  const u = (colType || "").toUpperCase();
  if (u.includes("INT")) return "td-int";
  if (u.includes("REAL") || u.includes("FLOAT") || u.includes("DOUBLE") || u.includes("NUMERIC")) return "td-real";
  return "";
}

// ── DataTable ─────────────────────────────────────────────────────────────────
function DataTable({ cols, rows, colTypes, sortCol, sortDir, onSort, offsetStart }) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th className="th-rownum" style={{ width: 52, minWidth: 52 }}>
            <div className="th-inner" style={{ cursor: "default", paddingRight: 6 }}>
              <span className="th-name" style={{ textAlign: "right", color: "var(--text-disabled)", fontSize: 10 }}>#</span>
            </div>
          </th>
          {cols.map((col, i) => {
            const isSorted = sortCol === col;
            return (
              <th key={col} onClick={() => onSort(col)}>
                <div className={`th-inner${isSorted ? " sorted" : ""}`}>
                  <span className="th-name">{col}</span>
                  {colTypes && colTypes[i] && (
                    <span className="th-type">{colTypes[i].toUpperCase()}</span>
                  )}
                  <span className="th-sort-icon">
                    {isSorted
                      ? <Icon icon={sortDir === "asc" ? Icons.ArrowUp : Icons.ArrowDown} size={11} />
                      : <Icon icon={Icons.ChevronsUpDown} size={11} />}
                  </span>
                </div>
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 ? (
          <tr>
            <td colSpan={cols.length + 1} style={{ textAlign: "center", padding: "32px", color: "var(--text-disabled)" }}>
              No rows to display
            </td>
          </tr>
        ) : rows.map((row, ri) => (
          <tr key={ri}>
            <td className="td-rownum">{offsetStart + ri + 1}</td>
            {row.map((val, ci) => {
              const cc = cellClass(val, colTypes?.[ci]);
              const isNull = val === null || val === undefined;
              const display = isNull ? "NULL" : String(val);
              return (
                <td key={ci} className={cc} title={display}>
                  {isNull ? <span className="td-null">NULL</span> : display}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── Pagination ────────────────────────────────────────────────────────────────
function Pagination({ page, pageSize, total, onPage }) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const start = page * pageSize + 1;
  const end = Math.min((page + 1) * pageSize, total);

  // Compute page window (up to 7 buttons)
  const pages = useMemo(() => {
    const all = [];
    if (totalPages <= 7) {
      for (let i = 0; i < totalPages; i++) all.push(i);
    } else {
      all.push(0);
      if (page > 2) all.push("...");
      for (let i = Math.max(1, page - 1); i <= Math.min(totalPages - 2, page + 1); i++) all.push(i);
      if (page < totalPages - 3) all.push("...");
      all.push(totalPages - 1);
    }
    return all;
  }, [page, totalPages]);

  return (
    <div className="pagination">
      <button className="page-btn" disabled={page === 0} onClick={() => onPage(0)} title="First">
        <Icon icon={Icons.ChevronsLeft} size={12} />
      </button>
      <button className="page-btn" disabled={page === 0} onClick={() => onPage(page - 1)} title="Prev">
        <Icon icon={Icons.ChevronLeft} size={12} />
      </button>
      {pages.map((p, i) =>
        p === "..." ? (
          <span key={`ellipsis-${i}`} className="page-info">…</span>
        ) : (
          <button
            key={p}
            className={`page-btn${p === page ? " active" : ""}`}
            onClick={() => onPage(p)}
          >
            {p + 1}
          </button>
        )
      )}
      <button className="page-btn" disabled={page >= totalPages - 1} onClick={() => onPage(page + 1)} title="Next">
        <Icon icon={Icons.ChevronRight} size={12} />
      </button>
      <button className="page-btn" disabled={page >= totalPages - 1} onClick={() => onPage(totalPages - 1)} title="Last">
        <Icon icon={Icons.ChevronsRight} size={12} />
      </button>
      <span className="page-spacer" />
      <span className="page-info">
        {total === 0 ? "0 rows" : `${start}–${end} of ${total.toLocaleString()} rows`}
      </span>
    </div>
  );
}

// ── DataTab ───────────────────────────────────────────────────────────────────
function DataTab({ tableName, colTypes }) {
  const [rows, setRows] = useState([]);
  const [cols, setCols] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [sortCol, setSortCol] = useState("");
  const [sortDir, setSortDir] = useState("asc");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const debounceRef = useRef(null);

  // Debounce search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(0);
    }, 350);
  }, [search]);

  const fetchRows = useCallback(() => {
    if (!tableName) return;
    setLoading(true);
    setError(null);
    getBridge(b => {
      b.get_rows(tableName, page, pageSize, debouncedSearch, sortCol, sortDir, result => {
        setLoading(false);
        try {
          const data = JSON.parse(result);
          if (!data.ok) { setError(data.error); return; }
          setCols(data.cols);
          setRows(data.rows);
          setTotal(data.total);
        } catch (e) { setError(String(e)); }
      });
    });
  }, [tableName, page, pageSize, debouncedSearch, sortCol, sortDir]);

  useEffect(() => { fetchRows(); }, [fetchRows]);

  // Reset page on table change
  useEffect(() => { setPage(0); setSearch(""); setDebouncedSearch(""); setSortCol(""); setSortDir("asc"); }, [tableName]);

  const handleSort = (col) => {
    if (sortCol === col) {
      setSortDir(d => d === "asc" ? "desc" : "asc");
    } else {
      setSortCol(col);
      setSortDir("asc");
    }
    setPage(0);
  };

  const exportCSV = () => {
    if (!cols.length) return;
    const lines = [cols.join(",")];
    rows.forEach(r => lines.push(r.map(v => v === null ? "" : `"${String(v).replace(/"/g, '""')}"`).join(",")));
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: `${tableName}.csv` });
    a.click();
  };

  return (
    <div className="data-tab">
      <div className="data-toolbar">
        <div className="search-input-wrap">
          <Icon icon={Icons.Search} size={13} />
          <input
            className="search-input"
            placeholder="Search all columns…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        {loading && <Icon icon={Icons.Loader2} size={14} className="spinning" style={{ color: "var(--accent)" }} />}
        <span className="page-spacer" />
        <span className="row-count-label">
          {total.toLocaleString()} rows
        </span>
        <select
          className="page-size-select"
          value={pageSize}
          onChange={e => { setPageSize(Number(e.target.value)); setPage(0); }}
        >
          {[25, 50, 100, 200].map(n => <option key={n} value={n}>{n} per page</option>)}
        </select>
        <button className="btn btn-ghost btn-sm" onClick={exportCSV} title="Export current page as CSV">
          <Icon icon={Icons.Download} size={12} /> CSV
        </button>
        <button className="btn btn-ghost btn-sm" onClick={fetchRows} title="Refresh">
          <Icon icon={Icons.RefreshCw} size={12} />
        </button>
      </div>

      {error && (
        <div className="notice notice-error">
          <Icon icon={Icons.AlertCircle} size={13} /> {error}
        </div>
      )}

      <div className="table-scroll">
        <DataTable
          cols={cols}
          rows={rows}
          colTypes={colTypes}
          sortCol={sortCol}
          sortDir={sortDir}
          onSort={handleSort}
          offsetStart={page * pageSize}
        />
      </div>

      <Pagination
        page={page}
        pageSize={pageSize}
        total={total}
        onPage={setPage}
      />
    </div>
  );
}

// ── StructureTab ──────────────────────────────────────────────────────────────
function StructureTab({ tableName, schema }) {
  if (!schema) return (
    <div className="structure-tab">
      <div className="notice notice-info"><Icon icon={Icons.Loader2} size={13} className="spinning" /> Loading schema…</div>
    </div>
  );

  const { columns = [], fks = [], indexes = [] } = schema;

  return (
    <div className="structure-tab">
      {/* Columns */}
      <div className="struct-card">
        <div className="struct-card-header">
          <Icon icon={Icons.Columns3} size={13} />
          Columns ({columns.length})
        </div>
        <table className="schema-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Name</th>
              <th>Type</th>
              <th>Constraints</th>
              <th>Default</th>
            </tr>
          </thead>
          <tbody>
            {columns.map(col => (
              <tr key={col.cid}>
                <td style={{ color: "var(--text-disabled)", fontFamily: "monospace", fontSize: 11 }}>{col.cid}</td>
                <td style={{ fontWeight: 600 }}>
                  {col.name}
                  {col.pk > 0 && <span className="pk-badge" style={{ marginLeft: 6 }}>PK</span>}
                </td>
                <td>
                  <span className={`type-badge ${typeClass(col.type)}`}>{col.type || "TEXT"}</span>
                </td>
                <td>
                  {col.notnull && <span className="notnull-badge">NOT NULL</span>}
                </td>
                <td style={{ fontFamily: "monospace", fontSize: 11, color: "var(--text-disabled)" }}>
                  {col.default ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Indexes */}
      {indexes.length > 0 && (
        <div className="struct-card">
          <div className="struct-card-header">
            <Icon icon={Icons.Zap} size={13} />
            Indexes ({indexes.length})
          </div>
          <table className="schema-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Unique</th>
              </tr>
            </thead>
            <tbody>
              {indexes.map((idx, i) => (
                <tr key={i}>
                  <td style={{ fontFamily: "monospace", fontSize: 11.5 }}>{idx.name}</td>
                  <td>
                    {idx.unique
                      ? <span className="pk-badge">UNIQUE</span>
                      : <span style={{ color: "var(--text-disabled)", fontSize: 11 }}>—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Foreign keys */}
      {fks.length > 0 && (
        <div className="struct-card">
          <div className="struct-card-header">
            <Icon icon={Icons.Link} size={13} />
            Foreign Keys ({fks.length})
          </div>
          <table className="schema-table">
            <thead>
              <tr>
                <th>Column</th>
                <th>References</th>
              </tr>
            </thead>
            <tbody>
              {fks.map((fk, i) => (
                <tr key={i}>
                  <td style={{ fontFamily: "monospace", fontSize: 11.5, fontWeight: 600 }}>{fk.from}</td>
                  <td style={{ fontFamily: "monospace", fontSize: 11.5, color: "var(--accent)" }}>
                    {fk.table}.{fk.to}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── SqlTab ────────────────────────────────────────────────────────────────────
function SqlTab({ onQueryResult, queryResult, queryLoading }) {
  const [sql, setSql] = useState("SELECT * FROM sqlite_master ORDER BY type, name;");
  const textRef = useRef(null);

  const run = useCallback(() => {
    const q = (textRef.current?.value || sql).trim();
    if (!q) return;
    onQueryResult(q);
  }, [sql, onQueryResult]);

  const handleKeyDown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      run();
    }
    // Tab → insert spaces
    if (e.key === "Tab") {
      e.preventDefault();
      const ta = e.target;
      const s = ta.selectionStart, end = ta.selectionEnd;
      const val = ta.value;
      ta.value = val.slice(0, s) + "    " + val.slice(end);
      ta.selectionStart = ta.selectionEnd = s + 4;
      setSql(ta.value);
    }
  };

  // Preset queries
  const presets = [
    { label: "All tables", sql: "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name;" },
    { label: "DB info", sql: "PRAGMA database_list; SELECT * FROM sqlite_master ORDER BY type, name;" },
    { label: "Table info", sql: "PRAGMA table_info('TABLE_NAME');" },
    { label: "Count rows", sql: "SELECT COUNT(*) as rows FROM TABLE_NAME;" },
  ];

  return (
    <div className="sql-tab">
      <div className="sql-editor-wrap">
        <textarea
          ref={textRef}
          className="sql-textarea"
          value={sql}
          onChange={e => setSql(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Enter SQL… (Ctrl+Enter to run)"
          spellCheck={false}
        />
        <div className="sql-footer">
          <button className="btn btn-primary btn-sm" onClick={run} disabled={queryLoading}>
            {queryLoading
              ? <><Icon icon={Icons.Loader2} size={11} className="spinning" /> Running…</>
              : <><Icon icon={Icons.Play} size={11} /> Run  <kbd style={{ fontSize: 9, opacity: 0.7 }}>Ctrl+↵</kbd></>}
          </button>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => { setSql(""); if (textRef.current) textRef.current.value = ""; }}
          >
            Clear
          </button>
          <span style={{ flex: 1 }} />
          {presets.map(p => (
            <button
              key={p.label}
              className="btn btn-ghost btn-sm"
              onClick={() => { setSql(p.sql); if (textRef.current) textRef.current.value = p.sql; }}
              style={{ fontSize: 10.5 }}
            >
              {p.label}
            </button>
          ))}
        </div>
        <span className="sql-hint">Queries are read-only. Results capped at 2 000 rows.</span>
      </div>

      {queryResult && (
        <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, overflow: "hidden" }}>
          <div className="sql-result-meta">
            {queryResult.ok ? (
              <>
                <span className="sql-ok"><Icon icon={Icons.CheckCircle2} size={12} /> OK</span>
                <span>{queryResult.row_count?.toLocaleString()} rows</span>
                <span>{queryResult.elapsed_ms} ms</span>
                {queryResult.truncated && (
                  <span style={{ color: "#fbbf24" }}>
                    <Icon icon={Icons.AlertTriangle} size={11} /> truncated at 2 000
                  </span>
                )}
                {queryResult.cols?.length > 0 && (
                  <button
                    className="btn btn-ghost btn-sm"
                    style={{ marginLeft: "auto" }}
                    onClick={() => {
                      const lines = [queryResult.cols.join(",")];
                      queryResult.rows?.forEach(r => lines.push(r.map(v => v === null ? "" : `"${String(v).replace(/"/g, '""')}"`).join(",")));
                      const blob = new Blob([lines.join("\n")], { type: "text/csv" });
                      const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: "query_result.csv" });
                      a.click();
                    }}
                  >
                    <Icon icon={Icons.Download} size={11} /> CSV
                  </button>
                )}
              </>
            ) : (
              <span className="sql-err"><Icon icon={Icons.XCircle} size={12} /> {queryResult.error}</span>
            )}
          </div>
          {queryResult.ok && queryResult.cols?.length > 0 && (
            <div className="sql-result-table-wrap">
              <DataTable
                cols={queryResult.cols}
                rows={queryResult.rows || []}
                colTypes={null}
                sortCol=""
                sortDir="asc"
                onSort={() => { }}
                offsetStart={0}
              />
            </div>
          )}
        </div>
      )}

      {!queryResult && (
        <div className="welcome-state" style={{ opacity: 0.6 }}>
          <Icon icon={Icons.Terminal} size={32} style={{ color: "var(--accent)" }} />
          <span style={{ fontSize: 12 }}>Results appear here after running a query</span>
        </div>
      )}
    </div>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────
function Sidebar({ tables, views, selectedTable, onSelect, isOpen }) {
  const [filter, setFilter] = useState("");
  const allItems = useMemo(() => [
    ...tables.map(t => ({ ...t, is_view: false })),
    ...views.map(v => ({ ...v, is_view: true })),
  ], [tables, views]);

  const filtered = useMemo(() => {
    if (!filter) return allItems;
    const f = filter.toLowerCase();
    return allItems.filter(t => t.name.toLowerCase().includes(f));
  }, [allItems, filter]);

  const tableItems = filtered.filter(t => !t.is_view);
  const viewItems = filtered.filter(t => t.is_view);

  if (!isOpen) return null;

  return (
    <div className="sidebar">
      <div className="sidebar-search">
        <input
          placeholder="Filter tables…"
          value={filter}
          onChange={e => setFilter(e.target.value)}
        />
      </div>

      <div className="sidebar-list">
        {tableItems.length > 0 && (
          <>
            <div className="sidebar-section-label">
              <span>Tables</span>
              <span>{tableItems.length}</span>
            </div>
            {tableItems.map(t => (
              <div
                key={t.name}
                className={`table-item${selectedTable === t.name ? " active" : ""}`}
                onClick={() => onSelect(t.name)}
              >
                <Icon
                  icon={Icons.Table2}
                  size={13}
                  style={{ flexShrink: 0, opacity: selectedTable === t.name ? 1 : 0.5 }}
                />
                <span className="table-item-name">{t.name}</span>
                <span className="table-item-count">{fmtCount(t.row_count)}</span>
              </div>
            ))}
          </>
        )}

        {viewItems.length > 0 && (
          <>
            <div className="sidebar-section-label" style={{ marginTop: 8 }}>
              <span>Views</span>
              <span>{viewItems.length}</span>
            </div>
            {viewItems.map(t => (
              <div
                key={t.name}
                className={`table-item${selectedTable === t.name ? " active" : ""}`}
                onClick={() => onSelect(t.name)}
              >
                <Icon
                  icon={Icons.Eye}
                  size={13}
                  style={{ flexShrink: 0, opacity: selectedTable === t.name ? 1 : 0.5 }}
                />
                <span className="table-item-name">{t.name}</span>
                <span className="table-item-count">view</span>
              </div>
            ))}
          </>
        )}

        {filtered.length === 0 && (
          <div className="sidebar-empty">
            {filter ? `No tables matching "${filter}"` : "No tables found"}
          </div>
        )}
      </div>
    </div>
  );
}

// ── WelcomeState ──────────────────────────────────────────────────────────────
function WelcomeState({ onOpen }) {
  return (
    <div className="welcome-state" style={{ flex: 1 }}>
      <div className="welcome-icon">
        <Icon icon={Icons.Database} size={32} />
      </div>
      <div className="welcome-title">SQLite Viewer</div>
      <div className="welcome-sub">
        Open a <strong>.db</strong>, <strong>.sqlite</strong>, or <strong>.sqlite3</strong> file
        to browse its tables, inspect schemas, and run queries.
      </div>
      <button className="btn btn-primary" onClick={onOpen}>
        <Icon icon={Icons.FolderOpen} size={13} /> Open Database
      </button>
      <div className="welcome-drop-hint">
        <Icon icon={Icons.MousePointerClick} size={11} /> Or drop a file anywhere in the window
      </div>
    </div>
  );
}

// ── App ───────────────────────────────────────────────────────────────────────
function App() {
  const [dbInfo, setDbInfo] = useState(null);       // {path, name, file_size, tables, views, …}
  const [tables, setTables] = useState([]);
  const [views, setViews] = useState([]);
  const [selectedTable, setSelectedTable] = useState(null);
  const [activeTab, setActiveTab] = useState("data");
  const [schema, setSchema] = useState(null);
  const [colTypes, setColTypes] = useState([]);
  const [queryResult, setQueryResult] = useState(null);
  const [queryLoading, setQueryLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [dragOver, setDragOver] = useState(false);

  // Connect signals
  useEffect(() => {
    getBridge(b => {
      // Background query results
      const onQueryResult = (json) => {
        setQueryLoading(false);
        try { setQueryResult(JSON.parse(json)); } catch { setQueryResult({ ok: false, error: json }); }
      };

      // External DB open (e.g. from Python-side drop)
      const onDbOpened = (json) => {
        try {
          const data = JSON.parse(json);
          if (!data.ok) { setError(data.error); return; }
          setDbInfo(data);
          setTables(data.tables || []);
          setViews(data.views || []);
          const first = (data.tables || [])[0]?.name || (data.views || [])[0]?.name || null;
          setSelectedTable(first);
          setActiveTab("data");
          setSchema(null);
          setQueryResult(null);
          setError(null);
          setDragOver(false); // Reset drag state if Python-side drop happened
        } catch (e) { console.error("Signal error:", e); }
      };

      b.query_result.connect(onQueryResult);
      b.db_opened.connect(onDbOpened);

      return () => {
        b.query_result.disconnect(onQueryResult);
        b.db_opened.disconnect(onDbOpened);
      };
    });
  }, []);

  const openDb = useCallback((path) => {
    if (!path) return;
    setError(null);
    getBridge(b => {
      b.open_db(path, result => {
        try {
          const data = JSON.parse(result);
          if (!data.ok) { setError(data.error); return; }
          setDbInfo(data);
          setTables(data.tables || []);
          setViews(data.views || []);
          const first = (data.tables || [])[0]?.name || (data.views || [])[0]?.name || null;
          setSelectedTable(first);
          setActiveTab("data");
          setSchema(null);
          setQueryResult(null);
        } catch (e) { setError(String(e)); }
      });
    });
  }, []);

  const handleBrowse = useCallback(() => {
    getBridge(b => b.browse_db(path => path && openDb(path)));
  }, [openDb]);

  // Load schema whenever table changes
  useEffect(() => {
    if (!selectedTable) return;
    setSchema(null);
    setColTypes([]);
    getBridge(b => {
      b.get_schema(selectedTable, result => {
        try {
          const data = JSON.parse(result);
          if (data.ok) {
            setSchema(data);
            setColTypes(data.columns.map(c => c.type));
          }
        } catch { }
      });
    });
  }, [selectedTable]);

  // Drag-and-drop
  const handleDragOver = (e) => { e.preventDefault(); setDragOver(true); };
  const handleDragLeave = () => setDragOver(false);
  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);

    const dropPath = resolveDroppedFilePath(e);
    if (dropPath) {
      openDb(dropPath);
    } else {
      // If we couldn't resolve a full path, explain why instead of passing a raw filename
      const hasFile = e.dataTransfer.files?.length > 0;
      if (hasFile) {
        setError("Could not resolve the absolute path of the dropped file. This is often due to browser security restrictions. Please use the 'Open' button instead.");
      }
    }
  };

  const handleRunQuery = (sql) => {
    setQueryLoading(true);
    getBridge(b => b.run_query(sql));
  };

  const handleSelectTable = (name) => {
    setSelectedTable(name);
    if (activeTab === "sql") setActiveTab("data");
  };

  const TABS = [
    { id: "data", label: "Data", icon: Icons.Table2 },
    { id: "structure", label: "Structure", icon: Icons.Columns3 },
    { id: "sql", label: "SQL", icon: Icons.Terminal },
  ];

  return (
    <div
      className={`app-shell${dragOver ? " drag-over" : ""}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Header */}
      <div className="app-header">
        <div className="app-header-icon">
          <Icon icon={Icons.Database} size={16} />
        </div>
        <span className="app-header-title">SQLite</span>

        <div
          className={`app-header-path${dbInfo ? "" : " empty"}`}
          title={dbInfo?.path || ""}
        >
          {dbInfo ? dbInfo.path : "No database open — click Open or drop a file"}
        </div>

        {dbInfo && (
          <div className="app-header-stats">
            <div className="stat-badge">
              <Icon icon={Icons.HardDrive} size={11} />
              {fmtSize(dbInfo.file_size)}
            </div>
            <div className="stat-badge">
              <Icon icon={Icons.Table2} size={11} />
              {tables.length} tables
            </div>
          </div>
        )}

        <div className="app-header-actions">
          {dbInfo && (
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setSidebarOpen(v => !v)}
              title="Toggle sidebar"
            >
              <Icon icon={Icons.PanelLeft} size={13} />
            </button>
          )}
          <button className="btn btn-primary btn-sm" onClick={handleBrowse}>
            <Icon icon={Icons.FolderOpen} size={13} /> Open
          </button>
        </div>
      </div>

      {error && (
        <div className="notice notice-error" style={{ margin: "8px 16px" }}>
          <Icon icon={Icons.AlertCircle} size={13} /> {error}
          <button className="btn btn-ghost btn-sm" style={{ marginLeft: "auto" }} onClick={() => setError(null)}>✕</button>
        </div>
      )}

      {!dbInfo ? (
        <WelcomeState onOpen={handleBrowse} />
      ) : (
        <div className="main-layout">
          <Sidebar
            tables={tables}
            views={views}
            selectedTable={selectedTable}
            onSelect={handleSelectTable}
            isOpen={sidebarOpen}
          />

          <div className="content-area">
            {selectedTable ? (
              <>
                {/* Content header: table name + tabs */}
                <div className="content-header">
                  <span className="content-header-name">
                    <Icon icon={Icons.Table2} size={13} style={{ marginRight: 6, verticalAlign: "middle" }} />
                    {selectedTable}
                  </span>
                  <div className="tab-bar">
                    {TABS.map(t => (
                      <button
                        key={t.id}
                        className={`tab-btn${activeTab === t.id ? " active" : ""}`}
                        onClick={() => setActiveTab(t.id)}
                      >
                        <Icon icon={t.icon} size={12} />
                        {t.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Tab content */}
                {activeTab === "data" && (
                  <DataTab key={selectedTable} tableName={selectedTable} colTypes={colTypes} />
                )}
                {activeTab === "structure" && (
                  <StructureTab tableName={selectedTable} schema={schema} />
                )}
                {activeTab === "sql" && (
                  <SqlTab
                    onQueryResult={handleRunQuery}
                    queryResult={queryResult}
                    queryLoading={queryLoading}
                  />
                )}
              </>
            ) : (
              <>
                {/* No table — show SQL tab accessible */}
                <div className="content-header">
                  <span className="content-header-name" style={{ color: "var(--text-disabled)" }}>
                    No table selected
                  </span>
                  <div className="tab-bar">
                    <button className="tab-btn active">
                      <Icon icon={Icons.Terminal} size={12} /> SQL
                    </button>
                  </div>
                </div>
                <SqlTab
                  onQueryResult={handleRunQuery}
                  queryResult={queryResult}
                  queryLoading={queryLoading}
                />
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

ReactDOM.render(<App />, document.getElementById("root"));
