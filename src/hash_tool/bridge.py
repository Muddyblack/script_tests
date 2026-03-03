"""Hash Tool — PyQt/JS bridge exposed to the WebEngine page."""

import hashlib
import hmac as _hmac
import json
import os

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication, QFileDialog

CHUNK = 8 * 1024 * 1024  # 8 MB

ALGORITHMS = ["MD5", "SHA-1", "SHA-256", "SHA-512"]


# ── Background worker ─────────────────────────────────────────────────────────

class _FileHashWorker(QThread):
    progress = pyqtSignal(int)
    result   = pyqtSignal(str)   # JSON

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._path = path

    def run(self):
        try:
            size = os.path.getsize(self._path)
            algos = {
                "MD5":    hashlib.md5(),
                "SHA-1":  hashlib.sha1(),
                "SHA-256": hashlib.sha256(),
                "SHA-512": hashlib.sha512(),
            }
            done = 0
            with open(self._path, "rb") as f:
                while chunk := f.read(CHUNK):
                    for h in algos.values():
                        h.update(chunk)
                    done += len(chunk)
                    if size:
                        self.progress.emit(int(done * 100 / size))
            self.result.emit(json.dumps({k: v.hexdigest() for k, v in algos.items()}))
        except Exception as exc:
            self.result.emit(json.dumps({"error": str(exc)}))


# ── Bridge ────────────────────────────────────────────────────────────────────

class HashToolBridge(QObject):
    """Singleton object registered as ``pyBridge`` in the QWebChannel."""

    # Pushed to JS
    hash_progress = pyqtSignal(int)   # 0-100
    hash_complete = pyqtSignal(str)   # JSON {"MD5":..., "SHA-1":..., ...}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: _FileHashWorker | None = None

    # ── File hashing ──────────────────────────────────────────────────────────

    @pyqtSlot(str)
    def hash_file(self, path: str) -> None:
        """Start async file hashing; result arrives via *hash_complete* signal."""
        path = path.strip().strip('"')
        if not os.path.isfile(path):
            self.hash_complete.emit(json.dumps({"error": f"File not found: {path}"}))
            return

        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(500)

        self._worker = _FileHashWorker(path, self)
        self._worker.progress.connect(self.hash_progress)
        self._worker.result.connect(self.hash_complete)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    # ── Text hashing ──────────────────────────────────────────────────────────

    @pyqtSlot(str, str, result=str)
    def hash_text(self, text: str, hmac_key: str) -> str:
        """Return JSON with all four hashes for *text* (optionally HMAC-keyed)."""
        data = text.encode()
        key  = hmac_key.encode() if hmac_key else None
        algos = {
            "MD5":    (hashlib.md5,    "md5"),
            "SHA-1":  (hashlib.sha1,   "sha1"),
            "SHA-256": (hashlib.sha256, "sha256"),
            "SHA-512": (hashlib.sha512, "sha512"),
        }
        out: dict[str, str] = {}
        for label, (fn, _) in algos.items():
            out[label] = (
                _hmac.new(key, data, fn).hexdigest() if key else fn(data).hexdigest()
            )
        return json.dumps(out)

    # ── File dialog ───────────────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def browse_file(self) -> str:
        """Open a native file-picker dialog and return the chosen path (or "")."""
        path, _ = QFileDialog.getOpenFileName(None, "Select File")
        return path or ""

    # ── File info ─────────────────────────────────────────────────────────────

    @pyqtSlot(str, result=str)
    def file_info(self, path: str) -> str:
        """Return JSON with name, size_bytes, size_str for *path*."""
        path = path.strip().strip('"')
        if not os.path.isfile(path):
            return json.dumps({})
        size = os.path.getsize(path)
        if size < 1024:
            size_str = f"{size} B"
        elif size < 1024 ** 2:
            size_str = f"{size/1024:.1f} KB"
        elif size < 1024 ** 3:
            size_str = f"{size/1024**2:.2f} MB"
        else:
            size_str = f"{size/1024**3:.2f} GB"
        return json.dumps({
            "name":       os.path.basename(path),
            "size_bytes": size,
            "size_str":   size_str,
            "path":       path,
        })
