"""Archiver backend: format detection, capabilities, extraction and creation."""

import gzip
import os
import re
import shutil
import subprocess
import tarfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass

# All extensions we can at least extract
ARCHIVE_EXTENSIONS = {
    ".zip",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".tar.bz2",
    ".tbz2",
    ".tar.xz",
    ".txz",
    ".gz",
    ".7z",
    ".rar",
    ".iso",
    ".cab",
    ".wim",
    ".arj",
    ".lzh",
    ".xz",
    ".zst",
}

# (can_extract_python, can_create_python, can_extract_7z, can_create_7z, supports_password_7z)
# fmt: off
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
# fmt: on

# Formats that can be created (shown in the format combo)
CREATABLE_FORMATS = ["zip", "7z", "tar.gz", "tar.bz2", "tar.xz", "tar", "gz"]

# Compression level → 7z -mx flag
MX_MAP = {
    "Store": "-mx0",
    "Fastest": "-mx1",
    "Fast": "-mx3",
    "Normal": "-mx5",
    "Maximum": "-mx7",
    "Ultra": "-mx9",
}

# Dictionary size → 7z -md flag
MD_MAP = {
    "256 KB": "-md256k",
    "1 MB": "-md1m",
    "4 MB": "-md4m",
    "16 MB": "-md16m",
    "32 MB": "-md32m",
    "64 MB": "-md64m",
    "128 MB": "-md128m",
    "256 MB": "-md256m",
    "512 MB": "-md512m",
    "1 GB": "-md1024m",
}

# Thread count → 7z -mmt flag
MT_MAP = {
    "Auto": "-mmt",
    "1": "-mmt1",
    "2": "-mmt2",
    "4": "-mmt4",
    "8": "-mmt8",
    "16": "-mmt16",
}


ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class ArchiveCapabilities:
    fmt: str
    can_extract: bool
    can_create: bool
    needs_7z: bool
    supports_password: bool
    has_7z: bool

    def as_dict(self) -> dict:
        return {
            "fmt": self.fmt,
            "can_extract": self.can_extract,
            "can_create": self.can_create,
            "needs_7z": self.needs_7z,
            "supports_password": self.supports_password,
            "has_7z": self.has_7z,
        }


@dataclass(frozen=True)
class CreateOptions:
    fmt: str = "zip"
    password: str = ""
    level: str = "Normal"
    dict_size: str = "16 MB"
    threads: str = "Auto"
    solid: bool = True


class ArchiverBackend:
    def __init__(self):
        self._seven_zip_path = self.find_7z()

    @property
    def seven_zip_path(self) -> str | None:
        return self._seven_zip_path

    @property
    def has_7z(self) -> bool:
        return self._seven_zip_path is not None

    @staticmethod
    def find_7z() -> str | None:
        """Try to locate 7z binary on the system."""
        candidates = [
            r"C:\Program Files\7-Zip\7z.exe",
            r"C:\Program Files (x86)\7-Zip\7z.exe",
            "/usr/bin/7z",
            "/bin/7z",
            "/usr/local/bin/7z",
            shutil.which("7z") or "",
        ]
        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                return candidate
        return None

    @staticmethod
    def is_archive(path: str) -> bool:
        """Return True if path is a file format we can handle as an archive."""
        low = path.lower()
        return any(low.endswith(ext) for ext in ARCHIVE_EXTENSIONS)

    @staticmethod
    def detect_format(path: str) -> str:
        """Detect archive format string from filename."""
        low = path.lower()
        for ext in (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz"):
            if low.endswith(ext):
                return {"tgz": "tar.gz", "tbz2": "tar.bz2", "txz": "tar.xz"}.get(
                    ext.lstrip("."), ext.lstrip(".")
                )
        for ext in (
            ".7z",
            ".rar",
            ".iso",
            ".cab",
            ".wim",
            ".arj",
            ".lzh",
            ".zst",
            ".xz",
            ".zip",
            ".tar",
            ".gz",
        ):
            if low.endswith(ext):
                return ext.lstrip(".")
        return "zip"

    def get_capabilities(self, path: str) -> ArchiveCapabilities:
        """Return capabilities for an archive path."""
        fmt = self.detect_format(path)
        caps = FORMAT_CAPS.get(fmt, (False, False, False, False, False))
        ep, cp, e7, c7, pw = caps
        return ArchiveCapabilities(
            fmt=fmt,
            can_extract=ep or (e7 and self.has_7z),
            can_create=cp or (c7 and self.has_7z),
            needs_7z=not ep and e7,
            supports_password=pw and self.has_7z,
            has_7z=self.has_7z,
        )

    def list_archive_contents(self, archive_path: str) -> list[str]:
        """Return a list of member names inside an archive (best-effort)."""
        fmt = self.detect_format(archive_path)
        try:
            if fmt == "zip":
                with zipfile.ZipFile(archive_path, "r") as zf:
                    return zf.namelist()
            if fmt.startswith("tar"):
                mode_map = {
                    "tar": "r:",
                    "tar.gz": "r:gz",
                    "tar.bz2": "r:bz2",
                    "tar.xz": "r:xz",
                }
                with tarfile.open(archive_path, mode_map.get(fmt, "r:*")) as tf:
                    return tf.getnames()
            if self._seven_zip_path:
                result = subprocess.run(
                    [self._seven_zip_path, "l", "-slt", archive_path],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                return re.findall(r"^Path = (.+)$", result.stdout, re.MULTILINE)[1:]
        except Exception:
            pass
        return []

    @staticmethod
    def _run_7z_with_progress(cmd: list[str], on_progress: ProgressCallback | None) -> str:
        """Run 7z command, parse `XX%` lines for progress. Returns stderr on failure."""
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        last_err = []
        for line in proc.stdout:
            last_err.append(line)
            match = re.search(r"\b(\d{1,3})%", line)
            if match and on_progress:
                on_progress(int(match.group(1)), 100)
        proc.wait()
        if proc.returncode != 0:
            return "".join(last_err[-10:]).strip() or "7z operation failed"
        return ""

    def extract_archive(
        self,
        archive_path: str,
        dest_dir: str,
        password: str = "",
        on_progress: ProgressCallback | None = None,
    ) -> list[str]:
        """Extract an archive. Returns list of errors (empty = success)."""
        errors: list[str] = []
        fmt = self.detect_format(archive_path)
        try:
            os.makedirs(dest_dir, exist_ok=True)
            use_7z = (not FORMAT_CAPS.get(fmt, (False,))[0]) or (fmt == "7z")
            if use_7z:
                if not self._seven_zip_path:
                    return [
                        f"7-Zip not found — cannot extract .{fmt} files. Install 7-Zip."
                    ]
                cmd = [self._seven_zip_path, "x", archive_path, f"-o{dest_dir}", "-y"]
                if password:
                    cmd.append(f"-p{password}")
                err = self._run_7z_with_progress(cmd, on_progress)
                if err:
                    errors.append(err)
            elif fmt.startswith("tar"):
                mode_map = {
                    "tar": "r:",
                    "tar.gz": "r:gz",
                    "tar.bz2": "r:bz2",
                    "tar.xz": "r:xz",
                }
                with tarfile.open(archive_path, mode_map.get(fmt, "r:*")) as tf:
                    members = tf.getmembers()
                    total = len(members)
                    for i, member in enumerate(members):
                        tf.extract(member, dest_dir, filter="data")
                        if on_progress:
                            on_progress(i + 1, total)
            elif fmt == "gz":
                base = os.path.basename(archive_path)
                out_name = base[:-3] if base.endswith(".gz") else base + ".out"
                out_path = os.path.join(dest_dir, out_name)
                with gzip.open(archive_path, "rb") as fin, open(out_path, "wb") as fout:
                    shutil.copyfileobj(fin, fout)
                if on_progress:
                    on_progress(1, 1)
            else:
                pwd_bytes = password.encode() if password else None
                with zipfile.ZipFile(archive_path, "r") as zf:
                    members = zf.infolist()
                    total = len(members)
                    for i, member in enumerate(members):
                        try:
                            zf.extract(member, dest_dir, pwd=pwd_bytes)
                        except RuntimeError as exc:
                            if "password" in str(exc).lower():
                                errors.append("Invalid or missing password")
                                break
                            raise
                        if on_progress:
                            on_progress(i + 1, total)
        except Exception as exc:
            errors.append(str(exc))
        return errors

    @staticmethod
    def _collect_zip_files(sources: list[str]) -> list[tuple[str, str]]:
        all_files = []
        for src in sources:
            if os.path.isdir(src):
                for root, _, files in os.walk(src):
                    for file_name in files:
                        fp = os.path.join(root, file_name)
                        arcname = os.path.join(
                            os.path.basename(src),
                            os.path.relpath(fp, src),
                        )
                        all_files.append((fp, arcname))
            else:
                all_files.append((src, os.path.basename(src)))
        return all_files

    def create_archive(
        self,
        sources: list[str],
        output_path: str,
        options: CreateOptions,
        on_progress: ProgressCallback | None = None,
    ) -> list[str]:
        """Create an archive from source files/dirs. Returns errors."""
        errors: list[str] = []
        try:
            use_7z = options.fmt == "7z" or (options.fmt == "zip" and options.password)
            if use_7z:
                if not self._seven_zip_path:
                    return [
                        "7-Zip not found — install it to create .7z or encrypted .zip."
                    ]
                cmd = [self._seven_zip_path, "a", output_path] + sources
                cmd.append(MX_MAP.get(options.level, "-mx5"))
                if options.fmt == "7z":
                    if options.level != "Store":
                        cmd.append(MD_MAP.get(options.dict_size, "-md16m"))
                    cmd.append(MT_MAP.get(options.threads, "-mmt"))
                    cmd.append("-ms=on" if options.solid else "-ms=off")
                if options.password:
                    cmd.append(f"-p{options.password}")
                    if options.fmt == "7z":
                        cmd.append("-mhe=on")
                err = self._run_7z_with_progress(cmd, on_progress)
                if err:
                    errors.append(err)
            elif options.fmt.startswith("tar"):
                mode_map = {
                    "tar": "w:",
                    "tar.gz": "w:gz",
                    "tar.bz2": "w:bz2",
                    "tar.xz": "w:xz",
                }
                with tarfile.open(output_path, mode_map.get(options.fmt, "w:")) as tf:
                    for i, src in enumerate(sources):
                        tf.add(src, arcname=os.path.basename(src))
                        if on_progress:
                            on_progress(i + 1, len(sources))
            elif options.fmt == "gz":
                if len(sources) != 1 or os.path.isdir(sources[0]):
                    return [
                        "gzip only supports single files — use tar.gz for multiple files."
                    ]
                with open(sources[0], "rb") as fin, gzip.open(output_path, "wb") as fout:
                    shutil.copyfileobj(fin, fout)
                if on_progress:
                    on_progress(1, 1)
            else:
                with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    all_files = self._collect_zip_files(sources)
                    total = len(all_files)
                    for i, (fp, arcname) in enumerate(all_files):
                        zf.write(fp, arcname)
                        if on_progress:
                            on_progress(i + 1, total)
        except Exception as exc:
            errors.append(str(exc))
        return errors


BACKEND = ArchiverBackend()
_7Z_PATH = BACKEND.seven_zip_path


def find_7z() -> str | None:
    return BACKEND.find_7z()


def is_archive(path: str) -> bool:
    return BACKEND.is_archive(path)


def detect_format(path: str) -> str:
    return BACKEND.detect_format(path)


def get_capabilities(path: str) -> dict:
    return BACKEND.get_capabilities(path).as_dict()


def list_archive_contents(archive_path: str) -> list[str]:
    return BACKEND.list_archive_contents(archive_path)


def extract_archive(
    archive_path: str,
    dest_dir: str,
    password: str = "",
    on_progress: ProgressCallback | None = None,
) -> list[str]:
    return BACKEND.extract_archive(archive_path, dest_dir, password, on_progress)


def create_archive(
    sources: list[str],
    output_path: str,
    fmt: str = "zip",
    password: str = "",
    level: str = "Normal",
    dict_size: str = "16 MB",
    threads: str = "Auto",
    solid: bool = True,
    on_progress: ProgressCallback | None = None,
) -> list[str]:
    options = CreateOptions(
        fmt=fmt,
        password=password,
        level=level,
        dict_size=dict_size,
        threads=threads,
        solid=solid,
    )
    return BACKEND.create_archive(sources, output_path, options, on_progress)
