# Nexus Launcher

A small launcher and file indexer built with PyQt6, aimed at speeding up day-to-day workflows on sluggish Windows machines where a native Rust tool isn't an option/doable.

Summon the launcher with a hotkey, search your files instantly, and access a set of small productivity tools — all without touching the slow Windows Explorer.

## Tools

| Command | Description |
|---|---|
| `nexus` | Main launcher — hotkey-activated search & file indexer |
| `xexplorer` | Lightweight file explorer |
| `clipboard-manager` | Clipboard history manager |
| `ghost-typist` | Auto-type text via hotkey |
| `port-inspector` | View open ports and their processes |
| `hash-tool` | File hash checker |
| `regex-helper` | Interactive regex tester |
| `file-ops` | File operations & archiver |
| `text-summarizer` | Summarize text via GUI |

## Install

```bash
pip install -e .
```

Requires Python 3.9+ and PyQt6.

## Usage

```bash
nexus          # start the launcher (lives in system tray)
xexplorer      # open file explorer
clipboard-manager
```

The launcher stays in the system tray and pops up on a configurable hotkey.