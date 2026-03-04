"""System-level command execution: toggles, process management, macros."""

import os
import sqlite3
import subprocess
import sys
import time
import webbrowser

from PyQt6.QtCore import QTimer

from .utils import parse_chronos_input


def _set_status(
    nexus, text: str, color: str = "#a855f7", *, bold: bool = True
) -> None:
    """Update Nexus status label text and style consistently."""
    weight = "bold" if bold else "normal"
    nexus.status_lbl.setText(text)
    nexus.status_lbl.setStyleSheet(f"color: {color}; font-weight: {weight};")


def _toggle_nexus_theme() -> bool:
    """Toggle Nexus theme and return True when dark mode is active after toggle."""
    from src.common.theme import ThemeManager

    manager = ThemeManager()
    if manager.is_dark:
        manager.load_theme("light")
    else:
        manager.load_theme("midnight-marina")
    manager.theme_changed.emit()
    return manager.is_dark


def _launch_python_module(
    nexus,
    status_text: str,
    module_name: str,
    *args: str,
    env: dict | None = None,
) -> None:
    """Launch a Python module as a subprocess and update status label."""
    _set_status(nexus, status_text)
    subprocess.Popen([sys.executable, "-m", module_name, *args], env=env)


def _taskkill(target_args: list[str]) -> None:
    """Run taskkill in a detached subprocess."""
    subprocess.Popen(["taskkill", "/F", *target_args], shell=True)


def execute_system_toggle(nexus, cmd: str) -> None:
    """Execute Windows system-level toggles and power commands.

    *nexus* is the NexusSearch instance (used for status label + theme sync).
    """
    try:
        if cmd == "toggle_dark_mode":
            # No registry — open Windows personalization settings for the user to toggle
            webbrowser.open("ms-settings:personalization-colors")
            # Also toggle the Nexus app theme to match intent
            _toggle_nexus_theme()
            _set_status(nexus, "🌓 Opened Color Settings — toggle system theme there")

        elif cmd == "toggle_nexus_theme":
            is_dark = _toggle_nexus_theme()
            state_name = "Dark" if is_dark else "Light"
            _set_status(nexus, f"🌓 Nexus Theme set to {state_name}")

        elif cmd == "toggle_hidden_files":
            # No registry — open Folder Options dialog where the user can toggle
            subprocess.Popen(["control", "folders"])
            _set_status(nexus, "👁️ Opened Folder Options — toggle hidden files there")

        elif cmd == "toggle_desktop_icons":
            # Use the shell's built-in toggle command — no registry needed
            import ctypes

            WM_COMMAND = 0x0111
            TOGGLE_DESKTOP_ICONS = 0x7402
            progman = ctypes.windll.user32.FindWindowW("Progman", None)
            ctypes.windll.user32.SendMessageW(progman, WM_COMMAND, TOGGLE_DESKTOP_ICONS, 0)
            _set_status(nexus, "🔳 Desktop Icons Toggled")

        elif cmd == "toggle_mute":
            subprocess.run(
                [
                    "powershell",
                    "-Command",
                    "(new-object -com wscript.shell).SendKeys([char]173)",
                ],
                shell=True,
            )
            _set_status(nexus, "🔇 Master Audio Toggled")

        elif cmd == "flush_dns":
            subprocess.run(["ipconfig", "/flushdns"], shell=True)
            _set_status(nexus, "🌐 DNS Cache Flushed")

        elif cmd == "restart_explorer":
            subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], shell=True)
            subprocess.Popen(["explorer.exe"])
            _set_status(nexus, "🔄 Windows Explorer Restarted")

        elif cmd == "toggle_desktop":
            subprocess.run(
                [
                    "powershell",
                    "-Command",
                    "(New-Object -ComObject shell.application).toggleDesktop()",
                ],
                shell=True,
            )
            _set_status(nexus, "🖥️ Desktop Toggled")

        # --- POWER CONTROLS ---
        elif cmd == "cmd_lock":
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
            _set_status(nexus, "🔒 Workstation Locked")

        elif cmd == "cmd_sleep":
            subprocess.run(
                [
                    "powershell",
                    "-Command",
                    "Add-Type -Assembly System.Windows.Forms; "
                    "[System.Windows.Forms.Application]::SetSuspendState("
                    "[System.Windows.Forms.PowerState]::Suspend, $false, $false)",
                ],
                shell=True,
            )
            _set_status(nexus, "💤 System Sleeping...")

        elif cmd == "cmd_restart":
            subprocess.run(["shutdown", "/r", "/t", "0"])

        elif cmd == "cmd_shutdown":
            subprocess.run(["shutdown", "/s", "/t", "0"])

        # --- SETTINGS LAUNCHERS ---
        elif cmd.startswith("ms-settings:"):
            webbrowser.open(cmd)
            setting_name = cmd.split(":")[-1].replace("-", " ").upper()
            _set_status(nexus, f"⚙️ Launched: {setting_name}")

    except Exception as e:
        _set_status(nexus, f"Error executing toggle: {e}", color="#ef4444")


def kill_process(nexus, pid: str, name: str) -> None:
    """Terminate a process by PID."""
    try:
        _taskkill(["/PID", pid])
        _set_status(nexus, f"💀 Terminated: {name} ({pid})", color="#ef4444")
        QTimer.singleShot(500, lambda: update_process_cache(nexus, force=True))
    except Exception as e:
        _set_status(nexus, f"Error killing {name}: {e}", color="#ef4444")


def kill_all_processes(nexus, name: str) -> None:
    """Terminate all processes with the given image name."""
    try:
        # name might not have .exe if it comes from Get-Process
        img_name = name if name.lower().endswith(".exe") else f"{name}.exe"
        _taskkill(["/IM", img_name])
        _set_status(nexus, f"💀 Killed all: {name}", color="#ef4444")
        QTimer.singleShot(500, lambda: update_process_cache(nexus, force=True))
    except Exception as e:
        _set_status(nexus, f"Error killing all {name}: {e}", color="#ef4444")


def update_process_cache(nexus, force: bool = False) -> None:
    """Fetch running processes using PowerShell (Name, ID, Path, Memory)."""
    now = time.time()
    if not force and now - nexus.last_proc_update < 5:
        return

    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process | Select-Object Name, Id, Path, WorkingSet, @{Name='Description';Expression={$_.Description}} | ConvertTo-Csv -NoTypeInformation",
        ]
        output = subprocess.check_output(cmd, shell=True).decode(
            "utf-8", errors="ignore"
        )
        lines = output.strip().split("\n")

        # Group by name to support "Kill All" and deduplicate in UI if desired
        raw_procs = []
        if len(lines) > 1:
            import csv
            from io import StringIO

            reader = csv.DictReader(StringIO(output))
            for row in reader:
                name = row.get("Name", "")
                pid = row.get("Id", "")
                path = row.get("Path", "")
                desc = row.get("Description", "")
                mem_raw = row.get("WorkingSet", "0")
                try:
                    mem_mb = int(mem_raw) // 1024 // 1024
                    mem_str = f"{mem_mb} MB"
                except Exception:
                    mem_str = "0 MB"

                raw_procs.append(
                    {
                        "name": name,
                        "pid": pid,
                        "path": path,
                        "desc": desc,
                        "mem": mem_str,
                        "mem_bytes": int(mem_raw) if mem_raw.isdigit() else 0,
                    }
                )

        nexus.process_cache = raw_procs
        nexus.last_proc_update = now
    except Exception as e:
        print(f"Error in update_process_cache: {e}")

def launch_xexplorer(nexus) -> None:
    """Launch the XExplorer HTML-based File Manager."""
    _launch_python_module(nexus, "🧭 Launching X-Explorer...", "src.xexplorer.xexplorer")


def launch_regex_helper(nexus) -> None:
    """Launch the Regex Helper tool."""
    _launch_python_module(
        nexus,
        "🔬 Launching Regex Helper...",
        "src.regex_helper.regex_helper",
    )


def launch_file_ops(nexus) -> None:
    """Launch the Nexus File Tools on the FILE OPS tab."""
    _launch_python_module(
        nexus,
        "📂 Launching File Tools...",
        "src.file_ops.file_ops",
        "--tab",
        "fileops",
    )


def launch_archiver(nexus) -> None:
    """Launch the Nexus File Tools on the ARCHIVER tab."""
    _launch_python_module(
        nexus,
        "📦 Launching Archiver...",
        "src.file_ops.file_ops",
        "--tab",
        "archiver",
    )


def launch_color_picker(nexus) -> None:
    """Launch the Nexus Color Picker tool."""
    _launch_python_module(
        nexus,
        "🎨 Launching Color Picker...",
        "src.color_picker.color_picker",
    )


def launch_chronos(nexus) -> None:
    """Launch the Chronos Hub."""
    _launch_python_module(nexus, "⏳ Launching Chronos Hub...", "src.chronos.chronos")


def launch_clipboard_manager(nexus) -> None:
    """Launch the Clipboard Manager."""
    _launch_python_module(
        nexus,
        "📋 Launching Clipboard Manager...",
        "src.clipboard_manager.clipboard_manager",
    )


def launch_port_inspector(nexus) -> None:
    """Launch the Port Inspector."""
    _launch_python_module(
        nexus,
        "🌐 Launching Port Inspector...",
        "src.port_inspector.port_inspector",
    )


def launch_hash_tool(nexus) -> None:
    """Launch the Hash Tool."""
    _launch_python_module(nexus, "🔑 Launching Hash Tool...", "src.hash_tool.hash_tool")


def launch_ghost_typist(nexus) -> None:
    """Launch Ghost Typist text-expander UI."""
    env = os.environ.copy()
    env["NEXUS_OWNS_WATCHER"] = "1"
    _launch_python_module(
        nexus,
        "⌨️ Launching Ghost Typist...",
        "src.ghost_typist",
        env=env,
    )

def log_to_chronos(nexus, text: str) -> None:
    """Inject an achievement into the Chronos Hub."""
    import datetime

    # Smart parse
    content, priority, tags, due_date = parse_chronos_input(text)
    tags_str = ",".join(tags)

    try:
        from src.common.config import CHRONOS_DB

        now = datetime.datetime.now()
        with sqlite3.connect(CHRONOS_DB) as conn:
            # Achievements go to tasks table with is_achievement = 1 and status = Completed
            conn.execute(
                "INSERT INTO tasks (content, priority, tags, due_date, is_achievement, status, completed_at) VALUES (?, ?, ?, ?, 1, 'Completed', ?)",
                (content, priority, tags_str, due_date, now.isoformat()),
            )
        _set_status(nexus, f"🏆 Achievement Logged: {content}", color="#fbbf24")
    except Exception as e:
        _set_status(nexus, f"Chronos Log Error: {e}", color="#ef4444")


def add_task_to_chronos(nexus, text: str) -> None:
    """Inject a new Mission/Task into the Chronos Hub."""
    # Smart parse
    content, priority, tags, due_date = parse_chronos_input(text)
    tags_str = ",".join(tags)

    try:
        from src.common.config import CHRONOS_DB

        with sqlite3.connect(CHRONOS_DB) as conn:
            # Tasks go to tasks table with is_achievement = 0 and status = Pending
            conn.execute(
                "INSERT INTO tasks (content, priority, tags, due_date, is_achievement, status) VALUES (?, ?, ?, ?, 0, 'Pending')",
                (content, priority, tags_str, due_date),
            )
        _set_status(nexus, f"📋 Task Added to Chronos: {content}", color="#3b82f6")
    except Exception as e:
        _set_status(nexus, f"Chronos Task Error: {e}", color="#ef4444")
