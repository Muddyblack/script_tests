# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**fast-explorer** is a Windows-only PyQt6 application suite — a blazing-fast universal launcher and file indexer. It consists of multiple standalone tools that share common infrastructure.

## Commands

**Install (editable):**
```bash
pip install -e .
```

**Run tools:**
```bash
python -m src.nexus.app          # Nexus Search launcher (main entry point)
python -m src.xexplorer.xexplorer  # X-Explorer file manager
python -m src.regex_helper.regex_helper
python -m src.file_ops.file_ops
python -m src.archiver.archiver
python -m src.chronos.chronos
python -m src.color_picker.color_picker
python -m src.base64_tool.base64_tool
```

**Or via installed scripts:**
```bash
nexus          # Nexus Search
xexplorer      # X-Explorer
regex-helper
file-ops
archiver
```

**Lint:**
```bash
ruff check src/
ruff format src/
```

## Architecture

### Tool Structure
Each tool lives in its own `src/<toolname>/` package with a `__main__.py` and a main window class. Tools are launched as subprocesses from Nexus via `system_commands.py`.

### Shared Infrastructure (`src/common/`)
- **`config.py`** — All paths and constants: `APPDATA`-based DB/settings file paths, hotkey definitions, `ASSETS_DIR`, `PROJECT_ROOT`.
- **`theme.py`** — Singleton `ThemeManager` (PyQt6 `QObject`) loaded from `src/themes/<name>/theme.json`. Emits `theme_changed` signal when the file changes on disk. All tools should use `ThemeManager()` to access theme colors.
- **`theme_template.py`** — Shared `TOOL_SHEET` QSS template string with `{{variable}}` placeholders. Apply via `ThemeManager.apply_to_widget(widget, TOOL_SHEET)`.
- **`search_engine.py`** — `SearchEngine` queries one or more SQLite DBs (the file index) for filenames or file contents.

### Theme System
- Themes live in `src/themes/<theme-name>/theme.json` (e.g., `midnight-marina`, `light`).
- `theme.json` has `"name"`, `"dark": bool`, and `"colors": {...}` with named color keys.
- QSS templates use `{{color_key}}` placeholders; `ThemeManager.apply_to_widget()` substitutes them.
- `src/xexplorer/theme.py` is a legacy wrapper that delegates to `ThemeManager`.

### Nexus Search (`src/nexus/`)
- **`app.py`** — Entry point. Creates `NexusSearch`, registers global hotkeys via `_HotkeyWindow` (Win32 `RegisterHotKey`, survives sleep/lock), and a system tray.
- **`search.py`** — `NexusSearch` widget: all search UI, result lists, navigation, and launching logic. Uses `SearchEngine` for file search, and inline logic for apps/processes/web.
- **`system_commands.py`** — Windows-level commands: system toggles (dark mode, hidden files, mute), process management, power controls, and launching other tools as subprocesses.
- **`hotkeys.py`** — `_HotkeyWindow`: Win32 `RegisterHotKey`-based hotkey listener (not `WH_KEYBOARD_LL`).
- **`widgets.py`** — `NexusBridge`: thread-safe Qt signal bridge between hotkey thread and main thread.

### X-Explorer (`src/xexplorer/`)
- **`xexplorer.py`** — Main file manager window (`XExplorer`). Integrates file tree, search panel, archive viewer, and file ops.
- **`indexer.py`** — `IndexerWorker(QThread)`: walks the filesystem and batch-inserts into SQLite (`x_explorer_cache.db` in `APPDATA`).
- **`database.py`** — DB initialization (`files` table: `path, name, parent, is_dir, mtime`).
- **`watcher.py`** — Filesystem watcher using `watchdog` to keep the index current.
- **`delegates.py`** / **`icons.py`** — Custom item delegates and icon resolution.

### Data Storage
All persistent data is stored in `%APPDATA%`:
- `x_explorer_cache.db` — File index (SQLite)
- `context_switcher.db` — Nexus search DB
- `nexus_settings.json`, `nexus_usage.json`, `nexus_apps_cache.json`, `nexus_history.json`
- `theme_settings.json` — Current theme name
- `nexus_file_ops.json`, `nexus_archiver.json`
- `.chronos_app/chronos_data.db` — Chronos achievements DB

### Hotkeys (defaults)
- `Ctrl+Shift+Space` — Summon/hide Nexus
- `Ctrl+Shift+Q` — OCR snip-to-text

## Conventions
- Python 3.10+, line length 88, double quotes (enforced by `ruff.toml`).
- Imports order: stdlib → third-party → `src.*` → relative (enforced by `ruff` isort).
- Qt threading: use `QThread` subclasses or `QThreadPool`/`QRunnable`; never block the main thread. Cross-thread signals must go through a Qt signal bridge.
- The `KMP_DUPLICATE_LIB_OK=TRUE` env var must be set before importing torch/Qt together (see `app.py`).
