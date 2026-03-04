"""
builder.py — Build Nexus / Fast Explorer into a distributable .exe

Usage
-----
  # One-file exe (default)
  python builder.py

  # One-dir folder + zip archive
  python builder.py --onedir

Notes
-----
* All Python code, HTML/CSS/JS assets, and icons are packed inside the exe /
  extracted bundle.
* The ``data/`` directory (settings, caches, databases) is intentionally left
  OUTSIDE so user data persists between upgrades.  It is auto-created next to
  the exe on first launch (see src/common/config.py frozen-mode handling).
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import os
import re
import shutil
import struct
import subprocess
import sys
import zipfile

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SRC = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(SRC, "dist")
BUILD_TEMP = os.path.join(SRC, "build_temp")

# ---------------------------------------------------------------------------
# App name + version from pyproject.toml
# ---------------------------------------------------------------------------
APP = "NexusSearch"
_pyproject = os.path.join(SRC, "pyproject.toml")
with contextlib.suppress(Exception), open(_pyproject, encoding="utf-8") as _f:
    if _v := re.search(r'^version\s*=\s*"([^"]+)"', _f.read(), re.MULTILINE):
        APP = f"{APP}-{_v.group(1)}"

# ---------------------------------------------------------------------------
# Static asset trees bundled INSIDE the exe (src= → dest= inside _MEIPASS)
# The ``data/`` directory is *not* listed here — it stays next to the exe.
# ---------------------------------------------------------------------------

def _discover_src_modules() -> list[tuple[str, str]]:
    """Auto-discover all subdirectories under src/ as data entries."""
    src_dir = os.path.join(SRC, "src")
    entries: list[tuple[str, str]] = []
    if not os.path.isdir(src_dir):
        return entries
    for name in sorted(os.listdir(src_dir)):
        full = os.path.join(src_dir, name)
        if os.path.isdir(full) and not name.startswith("__"):
            rel = os.path.join("src", name)
            entries.append((rel, rel))
    return entries


DATA: list[tuple[str, str]] = [
    # Top-level assets (icons, SVGs)
    ("assets", "assets"),
    # All src/ subdirectories (auto-discovered — no need to update this list
    # when adding new modules)
    *_discover_src_modules(),
]

# Modules that PyInstaller sometimes misses with PyQt6-WebEngine
HIDDEN_IMPORTS: list[str] = [
    "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebChannel",
    "PyQt6.QtPrintSupport",
    "watchdog.observers",
    "watchdog.observers.winapi",
    "watchdog.events",
    "pynput.keyboard._win32",
    "pynput.mouse._win32",
    "psutil",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_pyinstaller() -> None:
    if importlib.util.find_spec("PyInstaller") is None:
        print("PyInstaller not found — installing…")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def _make_ico_from_png(png_path: str, ico_path: str) -> str | None:
    """Embed a PNG into a minimal single-image .ico so Windows shows the icon."""
    if not os.path.exists(png_path):
        return None
    try:
        with open(png_path, "rb") as f:
            png_data = f.read()
        with open(ico_path, "wb") as f:
            # ICONDIR header (6 bytes) + one ICONDIRENTRY (16 bytes) + image data
            f.write(struct.pack("<HHH", 0, 1, 1))
            f.write(struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png_data), 22))
            f.write(png_data)
        return ico_path
    except Exception as exc:
        print(f"[warn] Could not create .ico: {exc}")
        return None


def _zip_dir(folder: str, zip_path: str) -> None:
    """Zip an entire directory tree."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(folder):
            for fname in files:
                abs_p = os.path.join(root, fname)
                zf.write(abs_p, os.path.relpath(abs_p, os.path.dirname(folder)))


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def build(onedir: bool = False) -> None:
    _ensure_pyinstaller()

    mode = "--onedir" if onedir else "--onefile"
    print(f"\n{'='*60}")
    print(f"  Building  {APP}  ({mode})")
    print(f"{'='*60}\n")

    # ── Icon ────────────────────────────────────────────────────────────────
    png_icon = os.path.join(SRC, "assets", "nexus_icon.png")
    ico_icon = os.path.join(SRC, "assets", "nexus_icon.ico")
    icon_arg = _make_ico_from_png(png_icon, ico_icon)

    # ── PyInstaller command ──────────────────────────────────────────────────
    sep = ";" if sys.platform == "win32" else ":"

    cmd: list[str] = [
        sys.executable, "-m", "PyInstaller",
        "--name",      APP,
        mode,
        "--windowed",
        "--noconfirm",
        "--clean",
        "--distpath",  DIST,
        "--workpath",  BUILD_TEMP,
        "--specpath",  BUILD_TEMP,
    ]

    if icon_arg:
        cmd += ["--icon", icon_arg]

    # Hidden imports
    for hi in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", hi]

    # Collect PyQt6 data (Qt plugins, translations, WebEngine resources)
    cmd += ["--collect-data", "PyQt6"]

    # Add static asset trees
    for src_rel, dst_rel in DATA:
        src_abs = os.path.join(SRC, src_rel)
        if os.path.exists(src_abs):
            cmd += ["--add-data", f"{src_abs}{sep}{dst_rel}"]
        else:
            print(f"[skip] {src_rel!r} not found, skipping")

    # Entry point
    cmd.append(os.path.join(SRC, "nexus_app.py"))

    # ── Run ─────────────────────────────────────────────────────────────────
    print("Running PyInstaller…\n")
    if subprocess.run(cmd, cwd=SRC).returncode != 0:
        print("\n[error] PyInstaller failed.")
        sys.exit(1)

    # ── Cleanup temp ────────────────────────────────────────────────────────
    if os.path.exists(BUILD_TEMP):
        shutil.rmtree(BUILD_TEMP)
        print(f"Removed build temp: {BUILD_TEMP}")

    # ── Report ──────────────────────────────────────────────────────────────
    if onedir:
        folder = os.path.join(DIST, APP)
        zip_path = os.path.join(DIST, f"{APP}.zip")
        print(f"\nCreating ZIP archive → {zip_path}")
        _zip_dir(folder, zip_path)
        print(f"\n✓ Build complete!  Folder : {folder}")
        print(f"                   Archive: {zip_path}")
    else:
        exe = os.path.join(DIST, f"{APP}.exe")
        print(f"\n✓ Build complete!  Exe: {exe}")
        print(
            "\n  Note: place a 'data/' folder next to the exe on first run, or\n"
            "  just launch it — Nexus will create it automatically."
        )


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Nexus Search into an .exe")
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="Build as a one-dir folder + zip instead of a single exe file.",
    )
    build(onedir=parser.parse_args().onedir)
