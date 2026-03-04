"""File Tools bridge — Python ↔ JS via QWebChannel.

Exposes:
  get_info()           → JSON capabilities (7z path, format lists, …)
  get_item_info(path)  → JSON per-item metadata for the queue
  list_archive(path)   → JSON array of member names
  browse_files()       → JSON array of chosen paths
  browse_folder()      → chosen folder string
  load_settings()      → JSON {fo_dest, arc_dest}
  save_settings(json)  → persist fo_dest / arc_dest
  run_file_ops(json)   → async copy/move/delete  →  ops_progress / ops_done
  run_compress(json)   → async compress          →  arc_progress / arc_done
  run_extract(json)    → async extract           →  arc_progress / arc_done
"""

from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import subprocess
import tarfile
import threading
import zipfile

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QFileDialog

from src.common.config import ARCHIVER_SETTINGS, FILE_OPS_SETTINGS

# ── Archive constants ─────────────────────────────────────────────────────────

ARCHIVE_EXTENSIONS = {
    ".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2",
    ".tar.xz", ".txz", ".gz", ".7z", ".rar", ".iso", ".cab",
    ".wim", ".arj", ".lzh", ".xz", ".zst",
}

# (can_extract_py, can_create_py, can_extract_7z, can_create_7z, pw_support_7z)
FORMAT_CAPS: dict[str, tuple[bool, bool, bool, bool, bool]] = {
    "zip":     (True,  True,  True,  True,  True ),
    "7z":      (False, False, True,  True,  True ),
    "tar":     (True,  True,  False, False, False),
    "tar.gz":  (True,  True,  False, False, False),
    "tar.bz2": (True,  True,  False, False, False),
    "tar.xz":  (True,  True,  False, False, False),
    "gz":      (True,  True,  False, False, False),
    "rar":     (False, False, True,  False, False),
    "iso":     (False, False, True,  False, False),
    "cab":     (False, False, True,  False, False),
    "wim":     (False, False, True,  False, False),
    "arj":     (False, False, True,  False, False),
    "lzh":     (False, False, True,  False, False),
    "xz":      (False, False, True,  False, False),
    "zst":     (False, False, True,  False, False),
}

CREATABLE_FORMATS = ["zip", "7z", "tar.gz", "tar.bz2", "tar.xz", "tar", "gz"]

MX_MAP = {
    "Store": "-mx0", "Fastest": "-mx1", "Fast": "-mx3",
    "Normal": "-mx5", "Maximum": "-mx7", "Ultra": "-mx9",
}
MD_MAP = {
    "256 KB": "-md256k", "1 MB": "-md1m", "4 MB": "-md4m",
    "16 MB": "-md16m", "32 MB": "-md32m", "64 MB": "-md64m",
    "128 MB": "-md128m", "256 MB": "-md256m", "512 MB": "-md512m", "1 GB": "-md1024m",
}
MT_MAP = {
    "Auto": "-mmt", "1": "-mmt1", "2": "-mmt2",
    "4": "-mmt4", "8": "-mmt8", "16": "-mmt16",
}
SPLIT_MAP = {
    "None": "", "10 MB": "-v10m", "50 MB": "-v50m",
    "100 MB": "-v100m", "700 MB": "-v700m", "1 GB": "-v1024m", "4 GB": "-v4096m",
}

COPY_BUFFER = 8 * 1024 * 1024


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_7z() -> str | None:
    candidates = [
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        "/usr/bin/7z", "/bin/7z", "/usr/local/bin/7z",
        shutil.which("7z") or "",
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def _detect_format(path: str) -> str:
    low = path.lower()
    for ext in (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz"):
        if low.endswith(ext):
            return {"tgz": "tar.gz", "tbz2": "tar.bz2", "txz": "tar.xz"}.get(
                ext.lstrip("."), ext.lstrip(".")
            )
    for ext in (".7z", ".rar", ".iso", ".cab", ".wim", ".arj", ".lzh",
                ".zst", ".xz", ".zip", ".tar", ".gz"):
        if low.endswith(ext):
            return ext.lstrip(".")
    return "zip"


def _is_archive(path: str) -> bool:
    low = path.lower()
    return any(low.endswith(ext) for ext in ARCHIVE_EXTENSIONS)


def _fmt_size(sz: int) -> str:
    if sz >= 1_000_000_000:
        return f"{sz / 1_000_000_000:.1f} GB"
    if sz >= 1_000_000:
        return f"{sz / 1_000_000:.1f} MB"
    if sz >= 1_000:
        return f"{sz / 1_000:.1f} KB"
    return f"{sz} B"


def _run_7z(cmd: list[str], on_progress=None) -> str:
    """Run 7z, parse progress lines, return stderr snippet on failure."""
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )
    last_lines: list[str] = []
    for line in proc.stdout:
        last_lines.append(line)
        m = re.search(r"\b(\d{1,3})%", line)
        if m and on_progress:
            on_progress(int(m.group(1)), 100)
    proc.wait()
    if proc.returncode != 0:
        return "".join(last_lines[-10:]).strip() or "7z operation failed"
    return ""


def _fast_copy(src: str, dst: str) -> None:
    with open(src, "rb") as s, open(dst, "wb") as d:
        while buf := s.read(COPY_BUFFER):
            d.write(buf)
    shutil.copystat(src, dst)


def _collect_zip_files(sources: list[str]) -> list[tuple[str, str]]:
    out = []
    for src in sources:
        if os.path.isdir(src):
            for root, _, files in os.walk(src):
                for fn in files:
                    fp = os.path.join(root, fn)
                    arcname = os.path.join(
                        os.path.basename(src), os.path.relpath(fp, src)
                    )
                    out.append((fp, arcname))
        else:
            out.append((src, os.path.basename(src)))
    return out


# ── Core operations ───────────────────────────────────────────────────────────

def _do_extract(seven_z, archive, dest_dir, password, on_progress=None) -> list[str]:
    errors: list[str] = []
    fmt = _detect_format(archive)
    try:
        os.makedirs(dest_dir, exist_ok=True)
        caps = FORMAT_CAPS.get(fmt, (False,) * 5)
        use_7z = (not caps[0]) or fmt == "7z"
        if use_7z:
            if not seven_z:
                return [f"7-Zip required for .{fmt} — install 7-Zip and restart"]
            cmd = [seven_z, "x", archive, f"-o{dest_dir}", "-y"]
            if password:
                cmd.append(f"-p{password}")
            err = _run_7z(cmd, on_progress)
            if err:
                errors.append(err)
        elif fmt.startswith("tar"):
            mode = {"tar": "r:", "tar.gz": "r:gz", "tar.bz2": "r:bz2", "tar.xz": "r:xz"}
            with tarfile.open(archive, mode.get(fmt, "r:*")) as tf:
                members = tf.getmembers()
                for i, m in enumerate(members):
                    tf.extract(m, dest_dir, filter="data")
                    if on_progress:
                        on_progress(i + 1, len(members))
        elif fmt == "gz":
            base = os.path.basename(archive)
            out_name = base[:-3] if base.endswith(".gz") else base + ".out"
            with gzip.open(archive, "rb") as fin, open(
                os.path.join(dest_dir, out_name), "wb"
            ) as fout:
                shutil.copyfileobj(fin, fout)
            if on_progress:
                on_progress(1, 1)
        else:  # zip (python)
            pwd_bytes = password.encode() if password else None
            with zipfile.ZipFile(archive, "r") as zf:
                members = zf.infolist()
                for i, member in enumerate(members):
                    try:
                        zf.extract(member, dest_dir, pwd=pwd_bytes)
                    except RuntimeError as exc:
                        if "password" in str(exc).lower():
                            errors.append("Invalid or missing password")
                            break
                        raise
                    if on_progress:
                        on_progress(i + 1, len(members))
    except Exception as exc:
        errors.append(str(exc))
    return errors


def _do_compress(
    seven_z, sources, output, fmt, password, level,
    dict_size, threads, solid, split, encrypt_names, on_progress=None
) -> list[str]:
    errors: list[str] = []
    try:
        use_7z = fmt == "7z" or (fmt == "zip" and password)
        if use_7z:
            if not seven_z:
                return ["7-Zip required — install 7-Zip to create .7z or encrypted .zip"]
            cmd = [seven_z, "a", output] + sources
            cmd.append(MX_MAP.get(level, "-mx5"))
            if fmt == "7z":
                if level != "Store":
                    cmd.append(MD_MAP.get(dict_size, "-md16m"))
                cmd.append(MT_MAP.get(threads, "-mmt"))
                cmd.append("-ms=on" if solid else "-ms=off")
            if password:
                cmd.append(f"-p{password}")
                if fmt == "7z":
                    cmd.append("-mhe=on" if encrypt_names else "-mhe=off")
            split_flag = SPLIT_MAP.get(split, "")
            if split_flag:
                cmd.append(split_flag)
            err = _run_7z(cmd, on_progress)
            if err:
                errors.append(err)
        elif fmt.startswith("tar"):
            mode = {"tar": "w:", "tar.gz": "w:gz", "tar.bz2": "w:bz2", "tar.xz": "w:xz"}
            with tarfile.open(output, mode.get(fmt, "w:")) as tf:
                for i, src in enumerate(sources):
                    tf.add(src, arcname=os.path.basename(src))
                    if on_progress:
                        on_progress(i + 1, len(sources))
        elif fmt == "gz":
            if len(sources) != 1 or os.path.isdir(sources[0]):
                return ["gzip supports only single files — use tar.gz for multiple"]
            with open(sources[0], "rb") as fin, gzip.open(output, "wb") as fout:
                shutil.copyfileobj(fin, fout)
            if on_progress:
                on_progress(1, 1)
        else:  # zip (python)
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
                all_files = _collect_zip_files(sources)
                for i, (fp, arcname) in enumerate(all_files):
                    zf.write(fp, arcname)
                    if on_progress:
                        on_progress(i + 1, len(all_files))
    except Exception as exc:
        errors.append(str(exc))
    return errors


# ── Bridge ────────────────────────────────────────────────────────────────────

class FileToolsBridge(QObject):
    """Singleton QObject registered as ``pyBridge`` in QWebChannel."""

    # Python → JS
    ops_progress = pyqtSignal(int, int, str)   # done, total, current_name
    ops_done     = pyqtSignal(str)             # JSON {errors:[...]}
    arc_progress = pyqtSignal(int, int)        # done, total
    arc_done     = pyqtSignal(str)             # JSON {errors:[...], message:"..."}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._7z = _find_7z()
        self._initial_tab: str = "fileops"
        self._initial_fo_sources: list[str] = []
        self._initial_arc_sources: list[str] = []

    # ── Initial state (pre-populated from external callers) ────────────────────

    def set_initial_fo_sources(self, paths: list[str]) -> None:
        self._initial_fo_sources = list(paths)

    def set_initial_arc_sources(self, paths: list[str]) -> None:
        self._initial_arc_sources = list(paths)

    def set_initial_tab(self, tab: str) -> None:
        self._initial_tab = tab

    @pyqtSlot(result=str)
    def get_initial_state(self) -> str:
        """Called by JS on startup to pick up any pre-loaded paths/tab."""
        state = json.dumps({
            "tab":        self._initial_tab,
            "fo_sources": self._initial_fo_sources,
            "arc_sources": self._initial_arc_sources,
        })
        # Consume once
        self._initial_fo_sources = []
        self._initial_arc_sources = []
        return state

    # ── Capabilities & metadata ────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def get_info(self) -> str:
        """Return JSON tool capabilities (7z availability, option lists)."""
        has_7z = bool(self._7z)
        fmts = [f for f in CREATABLE_FORMATS if f != "7z" or has_7z]
        return json.dumps({
            "has_7z":     has_7z,
            "7z_path":    self._7z or "",
            "formats":    fmts,
            "levels":     list(MX_MAP.keys()),
            "dict_sizes": list(MD_MAP.keys()),
            "threads":    list(MT_MAP.keys()),
            "split_sizes": list(SPLIT_MAP.keys()),
        })

    @pyqtSlot(str, result=str)
    def get_item_info(self, path: str) -> str:
        """Return JSON metadata for a single queue item."""
        path = path.strip()
        if not os.path.exists(path):
            return json.dumps({"error": "not found", "path": path})
        is_dir  = os.path.isdir(path)
        is_file = os.path.isfile(path)
        is_arc  = _is_archive(path) and is_file
        size    = os.path.getsize(path) if is_file else 0
        fmt     = _detect_format(path) if is_arc else ""
        caps: dict = {}
        if is_arc:
            ep, cp, e7, c7, pw = FORMAT_CAPS.get(fmt, (False,) * 5)
            caps = {
                "can_extract":      ep or (e7 and bool(self._7z)),
                "can_create":       cp or (c7 and bool(self._7z)),
                "needs_7z":         not ep and e7,
                "supports_password": pw and bool(self._7z),
            }
        return json.dumps({
            "path":       path,
            "name":       os.path.basename(path),
            "size":       size,
            "size_str":   _fmt_size(size) if size else "",
            "is_dir":     is_dir,
            "is_archive": is_arc,
            "fmt":        fmt.upper() if fmt else "",
            "caps":       caps,
        })

    @pyqtSlot(str, result=str)
    def list_archive(self, path: str) -> str:
        """Return JSON array of member paths inside an archive."""
        fmt = _detect_format(path)
        try:
            if fmt == "zip":
                with zipfile.ZipFile(path, "r") as zf:
                    return json.dumps(zf.namelist())
            if fmt.startswith("tar"):
                mode = {"tar": "r:", "tar.gz": "r:gz", "tar.bz2": "r:bz2", "tar.xz": "r:xz"}
                with tarfile.open(path, mode.get(fmt, "r:*")) as tf:
                    return json.dumps(tf.getnames())
            if self._7z:
                r = subprocess.run(
                    [self._7z, "l", "-slt", path],
                    capture_output=True, text=True, timeout=20,
                )
                names = re.findall(r"^Path = (.+)$", r.stdout, re.MULTILINE)[1:]
                return json.dumps(names)
        except Exception as exc:
            return json.dumps({"error": str(exc)})
        return json.dumps([])

    # ── File dialogs ───────────────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def browse_files(self) -> str:
        paths, _ = QFileDialog.getOpenFileNames(None, "Select Files or Archives")
        return json.dumps(paths)

    @pyqtSlot(result=str)
    def browse_folder(self) -> str:
        folder = QFileDialog.getExistingDirectory(None, "Select Folder")
        return folder or ""

    # ── Settings ───────────────────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def load_settings(self) -> str:
        result: dict = {}
        for key, path in [("fo_dest", FILE_OPS_SETTINGS), ("arc_dest", ARCHIVER_SETTINGS)]:
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        result[key] = json.load(f).get("last_dst", "")
                except Exception:
                    pass
        return json.dumps(result)

    @pyqtSlot(str)
    def save_settings(self, data: str) -> None:
        try:
            d = json.loads(data)
            for key, path in [("fo_dest", FILE_OPS_SETTINGS), ("arc_dest", ARCHIVER_SETTINGS)]:
                if key in d:
                    with open(path, "w") as f:
                        json.dump({"last_dst": d[key]}, f)
        except Exception:
            pass

    # ── File operations (async) ────────────────────────────────────────────────

    @pyqtSlot(str)
    def run_file_ops(self, payload: str) -> None:
        """Start async copy / move / delete.

        Payload JSON: {op: "copy"|"move"|"delete", sources: [...], dest: "..."}
        Emits ops_progress(done, total, name) and ops_done(json).
        """
        data    = json.loads(payload)
        op      = data["op"]
        sources = data["sources"]
        dest    = data.get("dest", "")

        ops = [
            (op, src, os.path.join(dest, os.path.basename(src)) if op != "delete" else "")
            for src in sources
        ]

        def worker() -> None:
            errors: list[str] = []
            total = len(ops)
            for i, (o, src, dst) in enumerate(ops):
                name = os.path.basename(src)
                try:
                    if o == "copy":
                        if os.path.isdir(src):
                            shutil.copytree(src, dst)
                        else:
                            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
                            _fast_copy(src, dst)
                    elif o == "move":
                        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
                        shutil.move(src, dst)
                    elif o == "delete":
                        if os.path.isdir(src):
                            shutil.rmtree(src)
                        else:
                            os.remove(src)
                except Exception as exc:
                    errors.append(f"{name}: {exc}")
                self.ops_progress.emit(i + 1, total, name)
            self.ops_done.emit(json.dumps({"errors": errors}))

        threading.Thread(target=worker, daemon=True).start()

    # ── Archive operations (async) ─────────────────────────────────────────────

    @pyqtSlot(str)
    def run_compress(self, payload: str) -> None:
        """Start async compression.

        Payload JSON: {sources, output, fmt, password, level, dict_size,
                       threads, solid, split, encrypt_names}
        Emits arc_progress(done, total) and arc_done(json).
        """
        d = json.loads(payload)

        def worker() -> None:
            errors = _do_compress(
                self._7z,
                sources      = d["sources"],
                output       = d["output"],
                fmt          = d.get("fmt", "zip"),
                password     = d.get("password", ""),
                level        = d.get("level", "Normal"),
                dict_size    = d.get("dict_size", "16 MB"),
                threads      = d.get("threads", "Auto"),
                solid        = d.get("solid", True),
                split        = d.get("split", "None"),
                encrypt_names= d.get("encrypt_names", False),
                on_progress  = lambda done, total: self.arc_progress.emit(done, total),
            )
            msg = f"Created {os.path.basename(d['output'])}"
            self.arc_done.emit(json.dumps({"errors": errors, "message": msg}))

        threading.Thread(target=worker, daemon=True).start()

    @pyqtSlot(str)
    def run_extract(self, payload: str) -> None:
        """Start async extraction.

        Payload JSON: {archives: [...], dest: "...", password: "..."}
        Emits arc_progress(done, total) and arc_done(json).
        """
        d        = json.loads(payload)
        archives = d["archives"]
        dest     = d.get("dest", "")
        password = d.get("password", "")

        def worker() -> None:
            all_errors: list[str] = []
            for arc in archives:
                out_dir = dest or os.path.dirname(arc)
                all_errors.extend(
                    _do_extract(
                        self._7z, arc, out_dir, password,
                        on_progress=lambda done, total: self.arc_progress.emit(done, total),
                    )
                )
            msg = f"Extracted {len(archives)} archive{'s' if len(archives) != 1 else ''}"
            self.arc_done.emit(json.dumps({"errors": all_errors, "message": msg}))

        threading.Thread(target=worker, daemon=True).start()
